# -*- encoding: utf-8 -*-
"""
QA标注平台 - Redis Streams消息队列实现

基于Redis Streams实现的消息队列，作为默认的MQ实现
"""

import asyncio
import json
import logging
from typing import Callable, Any, Optional

from .base_mq import BaseMQ, MQMessage, MQTopic

logger = logging.getLogger(__name__)


class RedisStreamMQ(BaseMQ):
    """
    基于Redis Streams的消息队列实现
    
    Features:
    - 支持Consumer Group模式
    - 支持消息确认（ACK/NACK）
    - 支持消息重试
    - 支持优先级（通过多个stream实现）
    """
    
    def __init__(
        self,
        stream_prefix: str = "qa",
        max_len: int = 100000,
        block_timeout_ms: int = 5000,
        consumer_group: str = "qa_processor",
        redis_client = None,
        **kwargs
    ):
        """
        初始化Redis Streams MQ
        
        Args:
            stream_prefix: 队列名前缀
            max_len: 每个stream的最大长度（XADD时使用MAXLEN）
            block_timeout_ms: 默认阻塞等待时间
            consumer_group: 默认消费者组名称
            redis_client: 已存在的Redis客户端（可选）
            **kwargs: Redis连接参数
        """
        super().__init__(stream_prefix)
        self.max_len = max_len
        self.block_timeout_ms = block_timeout_ms
        self.consumer_group = consumer_group
        self._redis = redis_client
        self._redis_config = kwargs
        self._consumer_tasks = {}
    
    async def connect(self) -> None:
        """建立Redis连接"""
        if self._connected:
            return
            
        if self._redis is None:
            # 延迟导入，避免循环依赖
            try:
                import redis.asyncio as aioredis
            except ImportError:
                import aioredis
            
            # 从配置创建Redis连接
            if self._redis_config:
                self._redis = aioredis.Redis(**self._redis_config)
            else:
                # 使用默认连接
                self._redis = aioredis.Redis(host="localhost", port=6379, decode_responses=True)
        
        # 测试连接
        await self._redis.ping()
        self._connected = True
        logger.info(f"Redis Streams MQ connected with prefix: {self.stream_prefix}")
    
    async def disconnect(self) -> None:
        """断开Redis连接"""
        # 停止所有消费者任务
        for task in self._consumer_tasks.values():
            task.cancel()
        self._consumer_tasks.clear()
        
        if self._redis:
            await self._redis.close()
            self._redis = None
        self._connected = False
        logger.info("Redis Streams MQ disconnected")
    
    async def _ensure_consumer_group(self, stream_key: str, group: str) -> None:
        """确保消费者组存在"""
        try:
            # 尝试创建消费者组，如果stream不存在则创建
            await self._redis.xgroup_create(
                stream_key, 
                group, 
                id="0",
                mkstream=True
            )
            logger.debug(f"Created consumer group {group} for stream {stream_key}")
        except Exception as e:
            # 如果组已存在，忽略错误
            if "BUSYGROUP" not in str(e):
                raise
    
    async def publish(
        self,
        topic: str,
        data: dict,
        priority: int = 0,
        delay_seconds: int = 0
    ) -> str:
        """
        发布消息到Redis Stream
        
        Args:
            topic: 主题名称
            data: 消息数据
            priority: 优先级（当前版本暂不使用）
            delay_seconds: 延迟发送（当前版本暂不支持）
            
        Returns:
            Redis Stream消息ID
        """
        if not self._connected:
            raise RuntimeError("MQ not connected. Call connect() first.")
        
        stream_key = self._get_full_topic(topic)
        
        # 序列化数据
        message_data = {
            "data": json.dumps(data, ensure_ascii=False),
            "priority": str(priority),
        }
        
        # 使用XADD添加消息，带MAXLEN限制
        message_id = await self._redis.xadd(
            stream_key,
            message_data,
            maxlen=self.max_len,
        )
        
        # 如果返回的是bytes，转换为str
        if isinstance(message_id, bytes):
            message_id = message_id.decode()
            
        logger.debug(f"Published message to {stream_key}: {message_id}")
        return message_id
    
    async def consume_one(
        self,
        topic: str,
        group: str,
        consumer_name: str = "default",
        block_timeout_ms: int = None,
    ) -> Optional[MQMessage]:
        """
        消费单条消息
        
        Args:
            topic: 主题名称
            group: 消费者组名称
            consumer_name: 消费者名称
            block_timeout_ms: 阻塞等待超时时间
            
        Returns:
            消息对象或None（超时无消息时）
        """
        if not self._connected:
            raise RuntimeError("MQ not connected. Call connect() first.")
        
        stream_key = self._get_full_topic(topic)
        timeout = block_timeout_ms or self.block_timeout_ms
        
        # 确保消费者组存在
        await self._ensure_consumer_group(stream_key, group)
        
        # 使用XREADGROUP读取消息
        try:
            result = await self._redis.xreadgroup(
                groupname=group,
                consumername=consumer_name,
                streams={stream_key: ">"},  # > 表示只读取新消息
                count=1,
                block=timeout,
            )
            
            if not result:
                return None
            
            # 解析结果: [(stream_key, [(message_id, {field: value})])]
            stream_data = result[0]
            messages = stream_data[1]
            
            if not messages:
                return None
            
            msg_id, msg_data = messages[0]
            
            # 处理bytes类型
            if isinstance(msg_id, bytes):
                msg_id = msg_id.decode()
            
            # 解析消息数据
            data_str = msg_data.get("data") or msg_data.get(b"data", "{}")
            if isinstance(data_str, bytes):
                data_str = data_str.decode()
            
            priority_str = msg_data.get("priority") or msg_data.get(b"priority", "0")
            if isinstance(priority_str, bytes):
                priority_str = priority_str.decode()
            
            data = json.loads(data_str)
            
            return MQMessage(
                message_id=msg_id,
                topic=topic,
                data=data,
                priority=int(priority_str),
                _raw_message=msg_data,
            )
            
        except Exception as e:
            logger.error(f"Error consuming from {stream_key}: {e}")
            raise
    
    async def subscribe(
        self,
        topic: str,
        group: str,
        handler: Callable[[MQMessage], Any],
        batch_size: int = 10,
        block_timeout_ms: int = None,
    ) -> None:
        """
        订阅消息（启动后台消费任务）
        
        Args:
            topic: 主题名称
            group: 消费者组名称
            handler: 消息处理函数
            batch_size: 批量处理数量
            block_timeout_ms: 阻塞等待超时时间
        """
        task_key = f"{topic}:{group}"
        
        if task_key in self._consumer_tasks:
            logger.warning(f"Consumer for {task_key} already running")
            return
        
        async def consume_loop():
            consumer_name = f"consumer_{id(asyncio.current_task())}"
            
            while True:
                try:
                    message = await self.consume_one(
                        topic=topic,
                        group=group,
                        consumer_name=consumer_name,
                        block_timeout_ms=block_timeout_ms,
                    )
                    
                    if message:
                        try:
                            await handler(message)
                            await self.ack(topic, group, message.message_id)
                        except Exception as e:
                            logger.error(f"Handler error for message {message.message_id}: {e}")
                            # 处理失败，可以选择NACK或发送到死信队列
                            retry_count = message.data.get("_retry_count", 0)
                            if retry_count >= 3:
                                await self.publish_to_dead_letter(
                                    original_topic=topic,
                                    data=message.data,
                                    error=str(e),
                                    retry_count=retry_count
                                )
                                await self.ack(topic, group, message.message_id)
                            else:
                                # 重新发布带重试计数
                                message.data["_retry_count"] = retry_count + 1
                                await self.publish(topic, message.data, message.priority)
                                await self.ack(topic, group, message.message_id)
                                
                except asyncio.CancelledError:
                    logger.info(f"Consumer for {task_key} cancelled")
                    break
                except Exception as e:
                    logger.error(f"Consumer error for {task_key}: {e}")
                    await asyncio.sleep(1)  # 出错后等待1秒再重试
        
        task = asyncio.create_task(consume_loop())
        self._consumer_tasks[task_key] = task
        logger.info(f"Started consumer for {task_key}")
    
    async def ack(self, topic: str, group: str, message_id: str) -> None:
        """确认消息处理成功"""
        stream_key = self._get_full_topic(topic)
        await self._redis.xack(stream_key, group, message_id)
        logger.debug(f"ACK message {message_id} from {stream_key}")
    
    async def nack(
        self,
        topic: str,
        group: str,
        message_id: str,
        requeue: bool = True
    ) -> None:
        """
        消息处理失败
        
        注意：Redis Streams没有原生的NACK，这里通过重新发布实现
        """
        if requeue:
            # 读取原消息并重新发布
            stream_key = self._get_full_topic(topic)
            
            # 使用XRANGE读取指定消息
            messages = await self._redis.xrange(stream_key, message_id, message_id)
            
            if messages:
                msg_id, msg_data = messages[0]
                data_str = msg_data.get("data") or msg_data.get(b"data", "{}")
                if isinstance(data_str, bytes):
                    data_str = data_str.decode()
                    
                data = json.loads(data_str)
                await self.publish(topic, data, priority=0)
        
        # 确认原消息（从pending中移除）
        await self.ack(topic, group, message_id)
    
    async def get_pending_count(self, topic: str, group: str) -> int:
        """获取待处理消息数量（pending状态）"""
        stream_key = self._get_full_topic(topic)
        
        try:
            # 使用XPENDING获取pending信息
            pending_info = await self._redis.xpending(stream_key, group)
            if pending_info:
                return pending_info.get("pending", 0) if isinstance(pending_info, dict) else pending_info[0]
            return 0
        except Exception:
            return 0
    
    async def get_stream_length(self, topic: str) -> int:
        """获取队列消息总数"""
        stream_key = self._get_full_topic(topic)
        
        try:
            return await self._redis.xlen(stream_key)
        except Exception:
            return 0
    
    async def get_all_stats(self) -> dict:
        """获取所有队列的统计信息"""
        stats = {}
        
        for topic in MQTopic:
            stream_key = self._get_full_topic(topic.value)
            try:
                length = await self._redis.xlen(stream_key)
                stats[topic.value] = {
                    "length": length,
                    "stream_key": stream_key,
                }
            except Exception:
                stats[topic.value] = {"length": 0, "stream_key": stream_key}
        
        return stats

