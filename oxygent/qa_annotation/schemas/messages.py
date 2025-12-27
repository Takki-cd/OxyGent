# -*- encoding: utf-8 -*-
"""
QA标注平台 - MQ消息数据模型

定义在消息队列中流转的各类消息结构
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional
from enum import Enum
import json


class QASourceType(str, Enum):
    """QA数据源类型"""
    E2E = "e2e"              # 端到端对话 (P0)
    USER_AGENT = "user_agent"  # 用户→Agent (P1)
    AGENT_AGENT = "agent_agent"  # Agent→Agent (P2)
    AGENT_TOOL = "agent_tool"   # Agent→Tool (P3)


class QAPriority(int, Enum):
    """QA优先级 (数值越小优先级越高)"""
    P0_E2E = 0           # 端到端对话
    P1_USER_AGENT = 1    # 用户直接调用Agent
    P2_AGENT_AGENT = 2   # Agent调用Agent
    P3_AGENT_TOOL = 3    # Agent调用Tool


@dataclass
class RawQAMessage:
    """
    原始QA数据消息
    
    在qa:raw队列中流转，由采集器(Hook/Importer)生产，LLM处理器消费
    """
    # 标识
    qa_id: str                    # QA唯一标识
    batch_id: str = ""            # 批次ID（导入时生成）
    
    # QA内容
    question: str = ""            # 问题
    answer: str = ""              # 答案
    qa_hash: str = ""             # QA内容的MD5（用于去重）
    
    # 来源追溯
    source_type: str = ""         # e2e/user_agent/agent_agent/agent_tool
    source_trace_id: str = ""     # 原始trace_id
    source_node_id: str = ""      # 原始node_id（可选）
    source_group_id: str = ""     # 原始group_id
    
    # 调用信息
    caller: str = ""              # 调用者
    callee: str = ""              # 被调用者
    caller_category: str = ""     # 调用者类别 (user/agent)
    callee_category: str = ""     # 被调用者类别 (agent/tool)
    call_chain: List[str] = field(default_factory=list)  # 完整调用链
    
    # 归属关系
    parent_qa_id: str = ""        # 父QA的ID（端到端QA的ID）
    
    # 优先级
    priority: int = 3             # 0-3，数值越小优先级越高
    
    # 时间
    created_at: str = ""          # 创建时间
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: dict) -> "RawQAMessage":
        """从字典创建实例"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ProcessedQAMessage(RawQAMessage):
    """
    LLM处理后的QA消息
    
    在qa:processed队列中流转，由LLM处理器生产，任务分配器消费
    继承RawQAMessage的所有字段
    """
    # LLM处理结果
    llm_summary: str = ""              # LLM生成的摘要
    llm_quality_score: float = 0.0     # 质量评分 0.0-1.0
    llm_suggested_category: str = ""   # 建议的分类
    llm_is_valid: bool = True          # 是否为有效QA
    llm_issues: List[str] = field(default_factory=list)  # 发现的问题列表
    
    # 处理状态
    processed_at: str = ""             # 处理时间
    retry_count: int = 0               # 重试次数


@dataclass
class TaskMessage:
    """
    标注任务消息
    
    在qa:pending队列中流转，由任务分配器生产，前端/WebSocket消费
    """
    task_id: str                  # 任务ID
    qa_id: str                    # 关联的QA ID
    
    # 任务内容（复制自ProcessedQAMessage）
    question: str = ""
    answer: str = ""
    llm_summary: str = ""
    llm_quality_score: float = 0.0
    
    # 来源信息
    source_type: str = ""
    source_trace_id: str = ""
    call_chain: List[str] = field(default_factory=list)
    
    # 归属关系
    parent_task_id: str = ""          # 父任务ID（对应端到端QA）
    
    # 分配信息
    assigned_to: str = ""             # 分配给谁
    assigned_at: str = ""             # 分配时间
    expire_at: str = ""               # 过期时间
    
    # 状态
    status: str = "pending"           # pending/assigned/annotated/expired
    priority: int = 3
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "TaskMessage":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ReviewMessage:
    """
    审核消息
    
    在qa:review队列中流转，由标注提交生产，审核处理器消费
    """
    review_id: str                # 审核ID
    task_id: str                  # 关联的任务ID
    annotation_id: str            # 关联的标注结果ID
    
    # 标注结果摘要
    annotated_question: str = ""
    annotated_answer: str = ""
    quality_label: str = ""       # good/acceptable/poor/invalid
    
    # 知识库相关
    should_add_to_kb: bool = False
    kb_category: str = ""
    
    # 提交信息
    submitted_by: str = ""
    submitted_at: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass 
class KnowledgeMessage:
    """
    知识库消息
    
    在qa:knowledge队列中流转，由审核处理器生产，知识库发布器消费
    """
    kb_id: str                    # 知识库条目ID
    task_id: str                  # 来源任务ID
    annotation_id: str            # 来源标注ID
    
    # 最终QA内容
    question: str = ""
    answer: str = ""
    
    # 分类信息
    category: str = ""
    domain: str = ""
    intent: str = ""
    tags: List[str] = field(default_factory=list)
    
    # 审核信息
    reviewed_by: str = ""
    reviewed_at: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)

