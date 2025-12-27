# -*- encoding: utf-8 -*-
"""
QA标注平台 - MQ抽象基类

定义消息队列的通用接口，MVP版本提供内存实现
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List
from collections import deque

logger = logging.getLogger(__name__)


class BaseMQ(ABC):
    """消息队列抽象基类"""
    
    @abstractmethod
    async def publish(self, topic: str, data: dict, priority: int = 0) -> str:
        """发布消息到指定topic"""
        pass
    
    @abstractmethod
    async def consume(self, topic: str, count: int = 1) -> List[dict]:
        """从指定topic消费消息"""
        pass
    
    @abstractmethod
    async def ack(self, topic: str, message_id: str) -> bool:
        """确认消息已处理"""
        pass


class MemoryMQ(BaseMQ):
    """
    内存队列实现（MVP版本）
    
    用于开发和测试，不持久化消息
    """
    
    _instance: Optional["MemoryMQ"] = None
    
    def __init__(self):
        self._queues: Dict[str, deque] = {}
        self._message_id = 0
    
    @classmethod
    def get_instance(cls) -> "MemoryMQ":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def publish(self, topic: str, data: dict, priority: int = 0) -> str:
        if topic not in self._queues:
            self._queues[topic] = deque()
        
        self._message_id += 1
        message_id = f"msg_{self._message_id}"
        
        self._queues[topic].append({
            "id": message_id,
            "data": data,
            "priority": priority
        })
        
        logger.debug(f"Published message {message_id} to {topic}")
        return message_id
    
    async def consume(self, topic: str, count: int = 1) -> List[dict]:
        if topic not in self._queues or not self._queues[topic]:
            return []
        
        result = []
        for _ in range(min(count, len(self._queues[topic]))):
            msg = self._queues[topic].popleft()
            result.append(msg)
        
        return result
    
    async def ack(self, topic: str, message_id: str) -> bool:
        # 内存队列消费即确认
        return True
