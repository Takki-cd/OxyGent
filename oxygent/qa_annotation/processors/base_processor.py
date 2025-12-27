# -*- encoding: utf-8 -*-
"""
QA标注平台 - 处理器抽象基类

定义Pipeline处理器的统一接口
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable, Any

from oxygent.qa_annotation.mq.base_mq import BaseMQ, MQMessage

logger = logging.getLogger(__name__)


class BaseProcessor(ABC):
    """
    Pipeline处理器抽象基类
    
    所有处理器需要继承此类并实现process方法
    
    处理器职责:
    1. 从输入队列消费消息
    2. 处理消息
    3. 发布到输出队列或死信队列
    """
    
    def __init__(
        self,
        mq: BaseMQ,
        input_topic: str,
        output_topic: str,
        consumer_group: str = "qa_processor",
        batch_size: int = 10,
        max_retries: int = 3,
    ):
        """
        初始化处理器
        
        Args:
            mq: MQ客户端实例
            input_topic: 输入队列名
            output_topic: 输出队列名
            consumer_group: 消费者组名
            batch_size: 批处理大小
            max_retries: 最大重试次数
        """
        self.mq = mq
        self.input_topic = input_topic
        self.output_topic = output_topic
        self.consumer_group = consumer_group
        self.batch_size = batch_size
        self.max_retries = max_retries
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._processed_count = 0
        self._error_count = 0
    
    @property
    def is_running(self) -> bool:
        """检查处理器是否在运行"""
        return self._running
    
    @property
    def stats(self) -> dict:
        """获取处理统计信息"""
        return {
            "processed_count": self._processed_count,
            "error_count": self._error_count,
            "running": self._running,
        }
    
    @abstractmethod
    async def process(self, message: MQMessage) -> Optional[dict]:
        """
        处理单条消息
        
        Args:
            message: 输入消息
            
        Returns:
            处理结果（字典），如果返回None则不发布到输出队列
            
        Raises:
            Exception: 处理失败时抛出异常
        """
        pass
    
    async def on_before_process(self, message: MQMessage) -> bool:
        """
        处理前的钩子
        
        可以在这里做验证、去重等
        
        Args:
            message: 输入消息
            
        Returns:
            True表示继续处理，False表示跳过
        """
        return True
    
    async def on_after_process(self, message: MQMessage, result: Optional[dict]):
        """
        处理后的钩子
        
        Args:
            message: 输入消息
            result: 处理结果
        """
        pass
    
    async def on_error(self, message: MQMessage, error: Exception):
        """
        错误处理钩子
        
        Args:
            message: 输入消息
            error: 错误对象
        """
        logger.error(f"Process error for message {message.message_id}: {error}")
    
    async def _handle_message(self, message: MQMessage):
        """处理单条消息的完整流程"""
        try:
            # 前置检查
            should_process = await self.on_before_process(message)
            if not should_process:
                logger.debug(f"Skipping message {message.message_id}")
                await self.mq.ack(self.input_topic, self.consumer_group, message.message_id)
                return
            
            # 处理消息
            result = await self.process(message)
            
            # 发布到输出队列
            if result is not None:
                await self.mq.publish(self.output_topic, result)
            
            # 确认消息
            await self.mq.ack(self.input_topic, self.consumer_group, message.message_id)
            
            # 后置处理
            await self.on_after_process(message, result)
            
            self._processed_count += 1
            
        except Exception as e:
            self._error_count += 1
            await self.on_error(message, e)
            
            # 检查重试次数
            retry_count = message.data.get("_retry_count", 0)
            if retry_count >= self.max_retries:
                # 发送到死信队列
                await self.mq.publish_to_dead_letter(
                    original_topic=self.input_topic,
                    data=message.data,
                    error=str(e),
                    retry_count=retry_count
                )
                await self.mq.ack(self.input_topic, self.consumer_group, message.message_id)
            else:
                # 重新发布带重试计数
                message.data["_retry_count"] = retry_count + 1
                await self.mq.publish(self.input_topic, message.data, message.priority)
                await self.mq.ack(self.input_topic, self.consumer_group, message.message_id)
    
    async def start(self):
        """启动处理器"""
        if self._running:
            logger.warning(f"{self.__class__.__name__} already running")
            return
        
        self._running = True
        logger.info(f"Starting {self.__class__.__name__} ({self.input_topic} -> {self.output_topic})")
        
        async def run_loop():
            consumer_name = f"{self.__class__.__name__}_{id(asyncio.current_task())}"
            
            while self._running:
                try:
                    message = await self.mq.consume_one(
                        topic=self.input_topic,
                        group=self.consumer_group,
                        consumer_name=consumer_name,
                    )
                    
                    if message:
                        await self._handle_message(message)
                        
                except asyncio.CancelledError:
                    logger.info(f"{self.__class__.__name__} cancelled")
                    break
                except Exception as e:
                    logger.error(f"{self.__class__.__name__} error: {e}")
                    await asyncio.sleep(1)  # 出错后等待1秒
        
        self._task = asyncio.create_task(run_loop())
    
    async def stop(self):
        """停止处理器"""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        logger.info(f"{self.__class__.__name__} stopped")
    
    async def process_batch(self, messages: list) -> list:
        """
        批量处理消息（可选实现）
        
        子类可以重写此方法实现批量处理优化
        
        Args:
            messages: 消息列表
            
        Returns:
            处理结果列表
        """
        results = []
        for message in messages:
            try:
                result = await self.process(message)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch process error: {e}")
                results.append(None)
        return results

