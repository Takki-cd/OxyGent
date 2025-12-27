# -*- encoding: utf-8 -*-
"""
QA标注平台 - MQ模块

MVP版本：提供MQ接口定义，默认使用内存队列
后续可扩展为Redis Stream / RabbitMQ / Kafka
"""

from .base_mq import BaseMQ

__all__ = ["BaseMQ"]
