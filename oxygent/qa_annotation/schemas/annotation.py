# -*- encoding: utf-8 -*-
"""
QA标注平台 - 标注结果数据模型

定义标注结果的完整结构和ES映射
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional
from enum import Enum


class QualityLabel(str, Enum):
    """质量标签"""
    EXCELLENT = "excellent"       # 优秀
    GOOD = "good"                 # 良好
    ACCEPTABLE = "acceptable"     # 可接受
    POOR = "poor"                 # 较差
    INVALID = "invalid"           # 无效


class ReviewStatus(str, Enum):
    """审核状态"""
    PENDING = "pending"           # 待审核
    APPROVED = "approved"         # 已通过
    REJECTED = "rejected"         # 已拒绝
    NEEDS_REVISION = "needs_revision"  # 需修改


@dataclass
class QAAnnotation:
    """
    QA标注结果模型
    
    对应ES表: {app}_qa_annotation
    """
    annotation_id: str
    task_id: str
    
    # 标注内容
    annotated_question: str = ""
    annotated_answer: str = ""
    quality_label: str = QualityLabel.ACCEPTABLE.value
    is_useful: bool = True
    correction_type: str = ""     # none/minor/major/rewrite
    
    # 分类标注
    domain: str = ""              # 领域
    intent: str = ""              # 意图
    complexity: str = ""          # simple/medium/complex
    
    # 知识库相关
    should_add_to_kb: bool = False
    kb_category: str = ""
    
    # 标注者信息
    annotator_id: str = ""
    annotation_time_cost: int = 0  # 标注耗时(秒)
    annotation_notes: str = ""     # 标注备注
    
    # 审核信息
    review_status: str = ReviewStatus.PENDING.value
    reviewer_id: str = ""
    review_comment: str = ""
    reviewed_at: str = ""
    
    # 时间戳
    created_at: str = ""
    updated_at: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "QAAnnotation":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ES表映射定义
QA_ANNOTATION_MAPPING = {
    "mappings": {
        "properties": {
            "annotation_id": {"type": "keyword"},
            "task_id": {"type": "keyword"},
            
            # 标注内容
            "annotated_question": {"type": "text", "analyzer": "ik_max_word"},
            "annotated_answer": {"type": "text", "analyzer": "ik_max_word"},
            "quality_label": {"type": "keyword"},
            "is_useful": {"type": "boolean"},
            "correction_type": {"type": "keyword"},
            
            # 分类标注
            "domain": {"type": "keyword"},
            "intent": {"type": "keyword"},
            "complexity": {"type": "keyword"},
            
            # 知识库
            "should_add_to_kb": {"type": "boolean"},
            "kb_category": {"type": "keyword"},
            
            # 标注者
            "annotator_id": {"type": "keyword"},
            "annotation_time_cost": {"type": "integer"},
            "annotation_notes": {"type": "text"},
            
            # 审核
            "review_status": {"type": "keyword"},
            "reviewer_id": {"type": "keyword"},
            "review_comment": {"type": "text"},
            "reviewed_at": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss.SSSSSSSSS||yyyy-MM-dd HH:mm:ss||epoch_millis"},
            
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

