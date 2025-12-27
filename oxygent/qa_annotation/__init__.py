# -*- encoding: utf-8 -*-
"""
OxyGent QA标注平台模块

本模块提供基于消息队列的QA数据标注Pipeline，从OxyGent框架的对话记录中提取高质量训练语料。

核心组件:
---------
- schemas: 数据模型定义（消息、任务、标注结果）
- mq: 消息队列抽象（支持Redis Streams/RabbitMQ/Kafka）
- collectors: 数据采集器（实时Hook、历史导入）
- processors: Pipeline处理器（任务分配、LLM处理、审核）
- services: 业务服务层（任务管理、标注、导入）
- routes: API路由

使用方法:
--------
1. 在config.json中启用qa_annotation:
   {
     "default": {
       "qa_annotation": {
         "enabled": true,
         "realtime_hook_enabled": false,
         "mq": {
           "type": "redis",
           "redis": {
             "stream_prefix": "qa",
             "consumer_group": "qa_processor"
           }
         },
         "collector": {
           "exclude_callees": ["retrieve_tools", "default_llm"],
           "exclude_callee_types": ["llm"],
           "min_question_length": 2,
           "min_answer_length": 10
         }
       }
     }
   }

2. 注册API路由:
   from oxygent.qa_annotation import qa_router
   app.include_router(qa_router)

3. 设置客户端:
   from oxygent.qa_annotation import set_qa_clients
   set_qa_clients(es_client, mq_client)

Pipeline流程:
-----------
1. 数据采集 -> qa:raw队列
2. LLM处理(可选) -> qa:processed队列  
3. 任务分配 -> qa:pending队列 + ES持久化
4. 人工标注 -> qa:review队列
5. 审核通过 -> qa:knowledge队列(可选)
"""

# 路由
from .routes import qa_router, set_qa_clients

# MQ
from .mq import BaseMQ, MQMessage, MQTopic, RedisStreamMQ
from .mq_factory import MQFactory, get_mq_client

# Schemas
from .schemas import (
    RawQAMessage,
    ProcessedQAMessage,
    TaskMessage,
    ReviewMessage,
    KnowledgeMessage,
    QASourceType,
    QAPriority,
    QATask,
    QATaskStatus,
    QATaskStage,
    QAAnnotation,
    QualityLabel,
    ReviewStatus,
)

# Collectors
from .collectors import QACollectorHook, QAHistoryImporter

# Processors
from .processors import BaseProcessor, TaskDispatcher

# Services
from .services import TaskService, AnnotationService, ImportService

__all__ = [
    # Routes
    "qa_router",
    "set_qa_clients",
    
    # MQ
    "BaseMQ",
    "MQMessage",
    "MQTopic",
    "RedisStreamMQ",
    "MQFactory",
    "get_mq_client",
    
    # Schemas - Messages
    "RawQAMessage",
    "ProcessedQAMessage",
    "TaskMessage",
    "ReviewMessage",
    "KnowledgeMessage",
    "QASourceType",
    "QAPriority",
    
    # Schemas - Task
    "QATask",
    "QATaskStatus",
    "QATaskStage",
    
    # Schemas - Annotation
    "QAAnnotation",
    "QualityLabel",
    "ReviewStatus",
    
    # Collectors
    "QACollectorHook",
    "QAHistoryImporter",
    
    # Processors
    "BaseProcessor",
    "TaskDispatcher",
    
    # Services
    "TaskService",
    "AnnotationService",
    "ImportService",
]


__version__ = "0.1.0"

