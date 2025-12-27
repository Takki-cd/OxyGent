# -*- encoding: utf-8 -*-
"""
QA标注平台 - MQ工厂

MVP版本：返回内存队列实现
后续可根据配置返回Redis/RabbitMQ/Kafka
"""

import logging
from typing import Optional

from oxygent.config import Config
from .mq.base_mq import BaseMQ, MemoryMQ

logger = logging.getLogger(__name__)


class MQFactory:
    """MQ客户端工厂"""
    
    _instance: Optional[BaseMQ] = None
    
    async def get_instance(self) -> BaseMQ:
        """获取MQ客户端实例（单例）"""
        if MQFactory._instance is not None:
            return MQFactory._instance
        
        mq_type = Config.get_qa_mq_type()
        
        if mq_type == "redis_stream":
            # TODO: 后续实现Redis Stream MQ
            logger.warning("Redis Stream MQ not implemented in MVP, using MemoryMQ")
            MQFactory._instance = MemoryMQ.get_instance()
        else:
            MQFactory._instance = MemoryMQ.get_instance()
        
        logger.info(f"MQ client initialized: {type(MQFactory._instance).__name__}")
        return MQFactory._instance
    
    @classmethod
    def reset(cls):
        """重置实例（用于测试）"""
        cls._instance = None
