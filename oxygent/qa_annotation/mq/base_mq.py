# -*- encoding: utf-8 -*-
"""
QA标注平台 - 消息队列抽象基类

定义MQ统一接口，支持多种MQ实现切换
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Any, Optional, List
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MQTopic(str, Enum):
    """消息队列Topic定义"""
    RAW = "raw"                   # 原始QA数据
    PROCESSED = "processed"       # LLM处理后的数据
    PENDING = "pending"           # 待标注任务
    REVIEW = "review"             # 待审核任务
    KNOWLEDGE = "knowledge"       # 待入知识库
    DEAD_LETTER = "dead_letter"   # 处理失败的消息


@dataclass
class MQMessage:
    """MQ消息封装"""
    message_id: str
    topic: str
    data: dict
    priority: int = 0
    retry_count: int = 0
    created_at: str = ""
    
    # 用于消费确认
    _raw_message: Any = field(default=None, repr=False)


class BaseMQ(ABC):
    """
    消息队列抽象基类
    
    支持多种MQ实现（Redis Streams/RabbitMQ/Kafka）
    所有实现必须继承此类并实现抽象方法
    """
    
    def __init__(self, stream_prefix: str = "qa"):
        """
        初始化MQ
        
        Args:
            stream_prefix: 队列名前缀，用于区分不同应用
        """
        self.stream_prefix = stream_prefix
        self._connected = False
    
    def _get_full_topic(self, topic: str) -> str:
        """获取完整的topic名称（带前缀）"""
        return f"{self.stream_prefix}:{topic}"
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected
    
    @abstractmethod
    async def connect(self) -> None:
        """建立连接"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接"""
        pass
    
    @abstractmethod
    async def publish(
        self,
        topic: str,
        data: dict,
        priority: int = 0,
        delay_seconds: int = 0
    ) -> str:
        """
        发布消息
        
        Args:
            topic: 主题名称（不含前缀）
            data: 消息数据
            priority: 优先级（0最高）
            delay_seconds: 延迟发送秒数（用于重试）
            
        Returns:
            消息ID
        """
        pass
    
    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        group: str,
        handler: Callable[[MQMessage], Any],
        batch_size: int = 10,
        block_timeout_ms: int = 5000,
    ) -> None:
        """
        订阅消息（Consumer Group模式）
        
        Args:
            topic: 主题名称
            group: 消费者组名称
            handler: 消息处理函数，接收MQMessage，返回处理结果
            batch_size: 批量处理数量
            block_timeout_ms: 阻塞等待超时时间(毫秒)
        """
        pass
    
    @abstractmethod
    async def consume_one(
        self,
        topic: str,
        group: str,
        consumer_name: str = "default",
        block_timeout_ms: int = 5000,
    ) -> Optional[MQMessage]:
        """
        消费单条消息
        
        Args:
            topic: 主题名称
            group: 消费者组名称
            consumer_name: 消费者名称
            block_timeout_ms: 阻塞等待超时时间
            
        Returns:
            消息对象或None
        """
        pass
    
    @abstractmethod
    async def ack(self, topic: str, group: str, message_id: str) -> None:
        """确认消息已成功处理"""
        pass
    
    @abstractmethod
    async def nack(
        self,
        topic: str,
        group: str,
        message_id: str,
        requeue: bool = True
    ) -> None:
        """
        消息处理失败
        
        Args:
            topic: 主题
            group: 消费者组
            message_id: 消息ID
            requeue: 是否重新入队
        """
        pass
    
    @abstractmethod
    async def get_pending_count(self, topic: str, group: str) -> int:
        """获取待处理消息数量"""
        pass
    
    @abstractmethod
    async def get_stream_length(self, topic: str) -> int:
        """获取队列消息总数"""
        pass
    
    async def get_dead_letter_count(self) -> int:
        """获取死信队列消息数量"""
        return await self.get_stream_length(MQTopic.DEAD_LETTER.value)
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if not self._connected:
                return False
            # 尝试获取一个队列的长度作为健康检查
            await self.get_stream_length(MQTopic.RAW.value)
            return True
        except Exception as e:
            logger.warning(f"MQ health check failed: {e}")
            return False
    
    async def publish_to_dead_letter(
        self,
        original_topic: str,
        data: dict,
        error: str,
        retry_count: int = 0
    ) -> str:
        """
        发布到死信队列
        
        Args:
            original_topic: 原始topic
            data: 原始数据
            error: 错误信息
            retry_count: 重试次数
            
        Returns:
            消息ID
        """
        from oxygent.utils.common_utils import get_format_time
        
        dead_letter_data = {
            "original_topic": original_topic,
            "original_data": data,
            "error": str(error),
            "retry_count": retry_count,
            "failed_at": get_format_time(),
        }
        return await self.publish(MQTopic.DEAD_LETTER.value, dead_letter_data)
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.disconnect()

