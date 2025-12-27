# -*- encoding: utf-8 -*-
"""
OxyGent QA标注平台模块

从OxyGent框架的对话记录中提取高质量QA数据用于训练语料标注。

MVP版本核心功能:
-----------------
1. QA提取：从ES的trace/node表批量提取QA对
2. 层级关系：端到端(E2E)任务与子任务的父子关系
3. 任务管理：树形结构展示、分配、状态流转
4. 标注审核：标注提交、审核通过/拒绝

可配置选项:
----------
- LLM预处理：默认跳过，可通过 llm_processor.enabled 开启
- 知识库发布：默认跳过，可通过 platform.enable_kb_export 开启
- 实时Hook：默认关闭，可通过 realtime_hook_enabled 开启

使用方法:
--------
1. 配置 config.json:
   {
     "qa_annotation": {
       "enabled": true,
       "llm_processor": {"enabled": false},
       "platform": {"enable_kb_export": false}
     }
   }

2. 注册API路由:
   from oxygent.qa_annotation import qa_router, set_qa_clients
   set_qa_clients(es_client)
   app.include_router(qa_router)

3. 初始化ES索引:
   调用 POST /api/qa/admin/init-indices
"""

# API路由
from .routes import qa_router, set_qa_clients

# 业务服务（单例模式）
from .services import (
    QAExtractionService,
    TaskService,
    AnnotationService,
    get_extraction_service,
    get_task_service,
    get_annotation_service,
)

# 数据模型
from .schemas import (
    QATask,
    QATaskStatus,
    QATaskStage,
    QAAnnotation,
    QualityLabel,
    ReviewStatus,
    QASourceType,
    QAPriority,
)

# 采集器（实时Hook，默认关闭）
from .collectors import QACollectorHook, publish_qa_to_mq

__all__ = [
    # API
    "qa_router",
    "set_qa_clients",
    
    # Services
    "QAExtractionService",
    "TaskService",
    "AnnotationService",
    "get_extraction_service",
    "get_task_service",
    "get_annotation_service",
    
    # Schemas - Task
    "QATask",
    "QATaskStatus",
    "QATaskStage",
    
    # Schemas - Annotation
    "QAAnnotation",
    "QualityLabel",
    "ReviewStatus",
    
    # Schemas - Types
    "QASourceType",
    "QAPriority",
    
    # Collectors
    "QACollectorHook",
    "publish_qa_to_mq",
]

__version__ = "0.1.0"
