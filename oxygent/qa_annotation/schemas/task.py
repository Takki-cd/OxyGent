# -*- encoding: utf-8 -*-
"""
QA标注平台 - 任务数据模型

定义QA任务的完整结构和ES映射
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional
from enum import Enum


class QATaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"           # 待分配
    ASSIGNED = "assigned"         # 已分配
    IN_PROGRESS = "in_progress"   # 标注中
    ANNOTATED = "annotated"       # 已标注
    REVIEWING = "reviewing"       # 审核中
    APPROVED = "approved"         # 已通过
    REJECTED = "rejected"         # 已拒绝
    EXPIRED = "expired"           # 已过期
    CANCELLED = "cancelled"       # 已取消


class QATaskStage(str, Enum):
    """任务所处阶段"""
    RAW = "raw"                   # 原始数据
    PROCESSED = "processed"       # LLM处理后
    PENDING = "pending"           # 待标注
    ANNOTATED = "annotated"       # 已标注
    REVIEWED = "reviewed"         # 已审核
    PUBLISHED = "published"       # 已发布


@dataclass
class QATask:
    """
    QA标注任务完整模型
    
    对应ES表: {app}_qa_task
    """
    # 任务标识
    task_id: str
    qa_id: str
    batch_id: str = ""
    
    # QA内容
    question: str = ""
    answer: str = ""
    qa_hash: str = ""
    
    # 来源追溯
    source_type: str = ""         # e2e/user_agent/agent_agent/agent_tool/agent_llm
    source_node_id: str = ""
    source_trace_id: str = ""
    source_group_id: str = ""
    call_chain: List[str] = field(default_factory=list)
    parent_task_id: str = ""      # 父任务ID（端到端任务）
    
    # 调用者与被调用者信息（新增）
    caller: str = ""              # 调用者名称
    callee: str = ""              # 被调用者名称
    caller_type: str = ""         # 调用者类型: user/agent/tool/llm
    callee_type: str = ""         # 被调用者类型: agent/tool/llm
    
    # 优先级与分类
    priority: int = 3
    category: str = ""
    tags: List[str] = field(default_factory=list)
    
    # LLM处理结果
    llm_summary: str = ""
    llm_quality_score: float = 0.0
    llm_suggested_category: str = ""
    llm_is_valid: bool = True
    
    # 状态管理
    status: str = QATaskStatus.PENDING.value
    stage: str = QATaskStage.RAW.value
    
    # 任务分配
    assigned_to: str = ""
    assigned_at: str = ""
    expire_at: str = ""
    
    # 时间戳
    created_at: str = ""
    updated_at: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "QATask":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ES表映射定义
QA_TASK_MAPPING = {
    "mappings": {
        "properties": {
            # 任务标识
            "task_id": {"type": "keyword"},
            "qa_id": {"type": "keyword"},
            "batch_id": {"type": "keyword"},
            
            # QA内容
            "question": {"type": "text", "analyzer": "ik_max_word"},
            "answer": {"type": "text", "analyzer": "ik_max_word"},
            "qa_hash": {"type": "keyword"},
            
            # 来源追溯
            "source_type": {"type": "keyword"},
            "source_node_id": {"type": "keyword"},
            "source_trace_id": {"type": "keyword"},
            "source_group_id": {"type": "keyword"},
            "call_chain": {"type": "keyword"},
            "parent_task_id": {"type": "keyword"},
            
            # 调用者与被调用者信息（新增）
            "caller": {"type": "keyword"},
            "callee": {"type": "keyword"},
            "caller_type": {"type": "keyword"},
            "callee_type": {"type": "keyword"},
            
            # 优先级与分类
            "priority": {"type": "integer"},
            "category": {"type": "keyword"},
            "tags": {"type": "keyword"},
            
            # LLM处理结果
            "llm_summary": {"type": "text"},
            "llm_quality_score": {"type": "float"},
            "llm_suggested_category": {"type": "keyword"},
            "llm_is_valid": {"type": "boolean"},
            
            # 状态管理
            "status": {"type": "keyword"},
            "stage": {"type": "keyword"},
            
            # 任务分配
            "assigned_to": {"type": "keyword"},
            "assigned_at": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss.SSSSSSSSS||yyyy-MM-dd HH:mm:ss||epoch_millis"},
            "expire_at": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss.SSSSSSSSS||yyyy-MM-dd HH:mm:ss||epoch_millis"},
            
            # 时间戳
            "created_at": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss.SSSSSSSSS||yyyy-MM-dd HH:mm:ss||epoch_millis"},
            "updated_at": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss.SSSSSSSSS||yyyy-MM-dd HH:mm:ss||epoch_millis"},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0
    }
}
