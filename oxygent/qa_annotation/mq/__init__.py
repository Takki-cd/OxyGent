# -*- encoding: utf-8 -*-
"""
QA标注平台 - 消息队列模块

提供可切换的消息队列抽象，支持:
- Redis Streams (默认，第一期实现)
- RabbitMQ (TODO: 第二期)
- Kafka (TODO: 第三期)
"""

from .base_mq import BaseMQ, MQMessage, MQTopic
from .redis_stream_mq import RedisStreamMQ

__all__ = [
    "BaseMQ",
    "MQMessage",
    "MQTopic",
    "RedisStreamMQ",
]

