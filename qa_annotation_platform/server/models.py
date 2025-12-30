"""
QA标注平台 - 数据模型定义

参照之前版本架构，标准化数据模型
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field, computed_field
import uuid
import hashlib


class QATaskStatus(str, Enum):
    """QA任务状态"""
    PENDING = "pending"       # 待标注
    ANNOTATED = "annotated"   # 已标注
    APPROVED = "approved"     # 已通过
    REJECTED = "rejected"     # 已拒绝


class QATaskStage(str, Enum):
    """QA任务阶段"""
    PENDING = "pending"       # 待处理
    EXTRACTING = "extracting"  # 提取中
    REVIEWING = "reviewing"    # 审核中
    COMPLETED = "completed"    # 完成


class SourceType(str, Enum):
    """数据来源类型"""
    E2E = "e2e"              # 端到端（用户->Agent）
    USER_AGENT = "user_agent"  # 用户直接调用Agent
    AGENT_AGENT = "agent_agent"  # Agent调用子Agent
    AGENT_LLM = "agent_llm"   # Agent调用LLM
    AGENT_TOOL = "agent_tool" # Agent调用Tool
    AGENT_OTHER = "agent_other"  # 其他


class Priority(int, Enum):
    """优先级定义"""
    P0_E2E = 0       # 端到端
    P1_AGENT = 1     # 子Agent
    P2_LLM = 2       # LLM调用
    P3_TOOL = 3      # Tool调用
    P4_OTHER = 4     # 其他


# ==================== 请求模型 ====================

class DepositRequest(BaseModel):
    """
    注入QA数据请求
    
    支持两种模式：
    1. 根节点模式（is_root=True）：创建新的端到端QA
    2. 子节点模式（parent_qa_id指定）：串联到已有QA
    """
    # 必填：来源追溯信息
    source_trace_id: str = Field(..., description="原始trace_id（来自OxyRequest.current_trace_id）")
    source_group_id: Optional[str] = Field(None, description="group_id（来自OxyRequest.group_id）")
    source_node_id: Optional[str] = Field(None, description="节点ID（可选）")
    
    # 必填：QA内容
    question: str = Field(..., description="问题/输入")
    answer: str = Field("", description="答案/输出")
    
    # 可选：层级关系（关键字段）
    parent_qa_id: Optional[str] = Field(None, description="父QA ID（子流程指向根QA）")
    is_root: bool = Field(False, description="是否为根节点（端到端QA）")
    
    # 可选：来源类型（自动推断）
    source_type: Optional[SourceType] = Field(None, description="来源类型（可选，自动推断）")
    
    # 可选：优先级（自动推断）
    priority: Optional[int] = Field(None, ge=0, le=4, description="优先级0-4（可选，自动推断）")
    
    # 可选：调用链信息
    caller: Optional[str] = Field(None, description="调用者")
    callee: Optional[str] = Field(None, description="被调用者")
    
    # 可选：附加信息
    category: Optional[str] = Field(None, description="分类")
    tags: List[str] = Field(default_factory=list, description="标签")
    extra: Dict[str, Any] = Field(default_factory=dict, description="额外数据")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_trace_id": "abc123",
                "source_group_id": "session_001",
                "question": "用户输入",
                "answer": "Agent输出",
                "is_root": True,
                "source_type": "e2e",
                "priority": 0,
                "caller": "user",
                "callee": "my_agent"
            }
        }
    
    @computed_field
    @property
    def qa_hash(self) -> str:
        """计算QA去重hash"""
        content = f"{self.question}:{self.answer}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def compute_qa_hash(self) -> str:
        """兼容旧代码的别名"""
        return self.qa_hash


class BatchDepositRequest(BaseModel):
    """批量注入请求"""
    items: List[DepositRequest]
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "source_trace_id": "abc123",
                        "question": "...",
                        "answer": "...",
                        "is_root": True
                    },
                    {
                        "source_trace_id": "abc123",
                        "question": "检索上下文",
                        "answer": "...",
                        "parent_qa_id": "qa_xxx"  # 指向根节点
                    }
                ]
            }
        }


# ==================== 存储模型 ====================

class QATask(BaseModel):
    """
    QA任务（存储模型）
    
    参照之前版本架构，完整定义所有字段
    """
    # 核心ID
    qa_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # QA内容
    question: str
    answer: str = ""
    qa_hash: str
    
    # 来源追溯
    source_type: str  # e2e/agent/tool/llm
    source_trace_id: str
    source_node_id: str = ""
    source_group_id: str = ""
    
    # 层级关系
    is_root: bool = False
    parent_qa_id: str = ""  # 指向根任务
    depth: int = 0  # 0=端到端, 1+=子节点
    
    # 调用链信息
    caller: str = ""
    callee: str = ""
    caller_type: str = ""
    callee_type: str = ""
    
    # 分类与标签
    category: str = ""
    tags: List[str] = Field(default_factory=list)
    
    # 优先级
    priority: int = 4
    
    # 状态
    status: str = QATaskStatus.PENDING.value
    stage: str = QATaskStage.PENDING.value
    
    # 标注结果
    annotation: Dict[str, Any] = Field(default_factory=dict)
    scores: Dict[str, Any] = Field(default_factory=dict)
    
    # 分配信息
    assigned_to: str = ""
    assigned_at: str = ""
    expire_at: str = ""
    
    # 批次信息
    batch_id: str = ""
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # 额外数据
    extra: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        from_attributes = True
    
    def to_es_doc(self) -> Dict[str, Any]:
        """转换为ES文档"""
        data = self.model_dump()
        # 转换datetime为字符串
        data["created_at"] = self.created_at.strftime("%Y-%m-%d %H:%M:%S.%f")
        data["updated_at"] = self.updated_at.strftime("%Y-%m-%d %H:%M:%S.%f")
        return data
    
    @classmethod
    def from_deposit_request(
        cls, 
        request: DepositRequest,
        batch_id: str = ""
    ) -> "QATask":
        """从DepositRequest创建QATask"""
        # 自动推断source_type和priority
        source_type = request.source_type
        priority = request.priority
        
        if source_type is None:
            source_type = cls._infer_source_type(
                is_root=request.is_root,
                caller=request.caller,
                callee=request.callee
            )
        
        if priority is None:
            priority = cls._infer_priority(source_type)
        
        # 确定层级关系
        is_root = request.is_root
        depth = 0 if is_root else 1
        parent_qa_id = request.parent_qa_id or ""
        
        # 如果是子节点但没有指定parent_qa_id，抛出警告（但允许创建）
        if not is_root and not parent_qa_id:
            # 后续可以通过串联机制补充
            pass
        
        return cls(
            question=request.question,
            answer=request.answer,
            qa_hash=request.compute_qa_hash(),
            source_type=source_type.value if isinstance(source_type, SourceType) else source_type,
            source_trace_id=request.source_trace_id,
            source_node_id=request.source_node_id or "",
            source_group_id=request.source_group_id or "",
            is_root=is_root,
            parent_qa_id=parent_qa_id,
            depth=depth,
            caller=request.caller or "",
            callee=request.callee or "",
            priority=priority,
            category=request.category or "",
            tags=request.tags,
            extra=request.extra,
            batch_id=batch_id
        )
    
    @staticmethod
    def _infer_source_type(
        is_root: bool,
        caller: Optional[str],
        callee: Optional[str]
    ) -> SourceType:
        """推断来源类型"""
        if is_root:
            return SourceType.E2E
        if caller == "user":
            return SourceType.USER_AGENT
        # 尝试根据callee推断
        if callee:
            callee_lower = callee.lower()
            if "llm" in callee_lower or "gpt" in callee_lower or "model" in callee_lower:
                return SourceType.AGENT_LLM
            if "tool" in callee_lower:
                return SourceType.AGENT_TOOL
            # 默认作为agent
            return SourceType.AGENT_AGENT
        return SourceType.AGENT_OTHER
    
    @staticmethod
    def _infer_priority(source_type: SourceType | str) -> int:
        """推断优先级"""
        if isinstance(source_type, str):
            try:
                source_type = SourceType(source_type)
            except ValueError:
                return Priority.P4_OTHER.value
        
        priority_map = {
            SourceType.E2E: Priority.P0_E2E.value,
            SourceType.USER_AGENT: Priority.P1_AGENT.value,
            SourceType.AGENT_AGENT: Priority.P1_AGENT.value,
            SourceType.AGENT_LLM: Priority.P2_LLM.value,
            SourceType.AGENT_TOOL: Priority.P3_TOOL.value,
            SourceType.AGENT_OTHER: Priority.P4_OTHER.value,
        }
        return priority_map.get(source_type, Priority.P4_OTHER.value)


# ==================== 响应模型 ====================

class DepositResponse(BaseModel):
    """注入响应"""
    success: bool
    qa_id: str
    task_id: str
    message: str


class BatchDepositResponse(BaseModel):
    """批量注入响应"""
    success: bool
    total: int
    success_count: int
    failed_count: int
    qa_ids: List[str]
    message: str


class TaskResponse(BaseModel):
    """任务响应"""
    qa_id: str
    task_id: str
    question: str
    answer: str
    source_type: str
    source_trace_id: str
    source_node_id: str
    source_group_id: str
    is_root: bool
    parent_qa_id: str
    depth: int
    priority: int
    status: str
    annotation: Dict[str, Any]
    scores: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class StatsResponse(BaseModel):
    """统计响应"""
    total: int
    pending: int
    annotated: int
    approved: int
    rejected: int
    by_priority: Dict[str, int]
    by_type: Dict[str, int]
    by_status: Dict[str, int]


# ==================== 过滤模型 ====================

class TaskFilter(BaseModel):
    """任务过滤条件"""
    qa_type: Optional[str] = None  # source_type
    status: Optional[str] = None
    priority: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    search_text: Optional[str] = None
    group_id: Optional[str] = None  # source_group_id
    trace_id: Optional[str] = None  # source_trace_id
    show_children: bool = False
    show_roots_only: bool = False  # 默认显示所有数据（根节点+子节点）


class AnnotationUpdate(BaseModel):
    """标注更新请求"""
    status: Optional[str] = None
    annotation: Optional[Dict[str, Any]] = None
    scores: Optional[Dict[str, Any]] = None
