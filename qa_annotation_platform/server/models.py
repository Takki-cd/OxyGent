"""
QA标注平台 - 数据模型定义

简化版：删除层级关系，按group_id/trace_id聚合
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field
import uuid
import hashlib


class DataType(str, Enum):
    """数据类型（描述数据来源类型）"""
    E2E = "e2e"              # 端到端（用户->Agent）
    AGENT = "agent"          # Agent调用
    LLM = "llm"              # LLM调用
    TOOL = "tool"            # Tool调用
    CUSTOM = "custom"        # 自定义


class Priority(int, Enum):
    """优先级定义"""
    P0 = 0       # 端到端（最高优先级）
    P1 = 1       # 一级子节点
    P2 = 2       # 二级子节点
    P3 = 3       # 三级子节点
    P4 = 4       # 其他


class DataStatus(str, Enum):
    """数据状态"""
    PENDING = "pending"       # 待标注
    ANNOTATED = "annotated"   # 已标注
    APPROVED = "approved"     # 已通过
    REJECTED = "rejected"     # 已拒绝


# ==================== 请求模型 ====================

class DepositRequest(BaseModel):
    """
    注入数据请求
    
    核心字段说明：
    - source_trace_id: 来自Oxygent的current_trace_id（必填）
    - source_request_id: 来自Oxygent的request_id（必填）
    - source_group_id: 来自Oxygent的group_id（可选，用于会话聚合）
    - question: 问题/输入（必填）
    - answer: 答案/输出（可选）
    - caller: 调用者（必填，如user/agent名称）
    - callee: 被调用者（必填，如agent/tool/llm名称）
    - priority: 优先级（可选，默认0，P0=端到端）
    - data_type: 数据类型（可选，用于标注时区分来源）
    """
    # 必填：来源追溯信息
    source_trace_id: str = Field(..., description="原始trace_id（来自OxyRequest.current_trace_id）")
    source_request_id: str = Field(..., description="原始request_id（来自OxyRequest.request_id）")
    source_group_id: Optional[str] = Field(None, description="group_id（来自OxyRequest.group_id）")
    
    # 必填：QA内容
    question: str = Field(..., description="问题/输入")
    answer: str = Field("", description="答案/输出")
    
    # 必填：调用链信息（caller/callee）
    caller: str = Field(..., description="调用者（user/agent名称）")
    callee: str = Field(..., description="被调用者（agent/tool/llm名称）")
    
    # 可选：调用类型（预占，用于未来扩展）
    caller_type: Optional[str] = Field(None, description="调用者类型（预占）")
    callee_type: Optional[str] = Field(None, description="被调用者类型（预占）")
    
    # 可选：数据类型（用于标注时区分来源）
    data_type: Optional[str] = Field(None, description="数据类型：e2e/agent/llm/tool/custom")
    
    # 可选：优先级（端到端必须为P0=0，其他按需设置）
    priority: int = Field(0, ge=0, le=4, description="优先级0-4，P0=端到端")
    
    # 可选：分类与标签
    category: Optional[str] = Field(None, description="分类")
    tags: List[str] = Field(default_factory=list, description="标签")
    
    # 可选：额外数据
    extra: Dict[str, Any] = Field(default_factory=dict, description="额外数据")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_trace_id": "abc123",
                "source_request_id": "req_001",
                "source_group_id": "session_001",
                "question": "用户输入",
                "answer": "Agent输出",
                "caller": "user",
                "callee": "my_agent",
                "data_type": "e2e",
                "priority": 0  # 端到端必须是P0
            }
        }
    
    def compute_data_hash(self) -> str:
        """计算数据去重hash"""
        content = f"{self.source_trace_id}:{self.source_request_id}:{self.question}:{self.answer}"
        return hashlib.md5(content.encode()).hexdigest()


class BatchDepositRequest(BaseModel):
    """批量注入请求"""
    items: List[DepositRequest]
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "source_trace_id": "abc123",
                        "source_request_id": "req_001",
                        "source_group_id": "session_001",
                        "question": "用户输入",
                        "answer": "Agent输出",
                        "caller": "user",
                        "callee": "my_agent",
                        "priority": 0  # 端到端
                    },
                    {
                        "source_trace_id": "abc123",
                        "source_request_id": "req_002",
                        "source_group_id": "session_001",
                        "question": "LLM调用",
                        "answer": "LLM回答",
                        "caller": "my_agent",
                        "callee": "gpt-4",
                        "priority": 2
                    }
                ]
            }
        }


# ==================== 存储模型 ====================

class QAData(BaseModel):
    """
    QA数据（存储模型）
    
    简化设计：
    - 一个唯一ID（data_id）替代qa_id和task_id
    - 按group_id/trace_id聚合，不再有parent_qa_id
    - 端到端通过priority=0标识
    - 使用caller/callee描述调用链
    """
    # 唯一ID（替代qa_id和task_id）
    data_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # QA内容
    question: str
    answer: str = ""
    data_hash: str
    
    # 来源追溯
    source_trace_id: str
    source_request_id: str
    source_group_id: str = ""
    
    # 调用链信息
    caller: str
    callee: str
    caller_type: str = ""  # 预占：调用者类型
    callee_type: str = ""  # 预占：被调用者类型
    
    # 数据类型（用于标注时区分来源）
    data_type: str = ""
    
    # 优先级（端到端=0，子节点>0）
    priority: int = 4
    
    # 分类与标签
    category: str = ""
    tags: List[str] = Field(default_factory=list)
    
    # 状态
    status: str = DataStatus.PENDING.value
    
    # 标注结果
    annotation: Dict[str, Any] = Field(default_factory=dict)
    scores: Dict[str, Any] = Field(default_factory=dict)
    
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
    ) -> "QAData":
        """从DepositRequest创建QAData"""
        # 自动推断data_type
        data_type = request.data_type
        if data_type is None:
            data_type = cls._infer_data_type(request)
        
        return cls(
            question=request.question,
            answer=request.answer,
            data_hash=request.compute_data_hash(),
            source_trace_id=request.source_trace_id,
            source_request_id=request.source_request_id,
            source_group_id=request.source_group_id or "",
            caller=request.caller,
            callee=request.callee,
            caller_type=request.caller_type or "",
            callee_type=request.callee_type or "",
            data_type=data_type,
            priority=request.priority,
            category=request.category or "",
            tags=request.tags,
            extra=request.extra,
            batch_id=batch_id
        )
    
    @staticmethod
    def _infer_data_type(request: DepositRequest) -> str:
        """推断数据类型"""
        # P0端到端
        if request.priority == 0:
            return "e2e"
        
        # 根据callee推断
        callee_lower = request.callee.lower()
        if any(keyword in callee_lower for keyword in ["llm", "gpt", "model", "openai", "anthropic"]):
            return "llm"
        if any(keyword in callee_lower for keyword in ["tool", "api", "search", "fetch"]):
            return "tool"
        if any(keyword in callee_lower for keyword in ["agent"]):
            return "agent"
        
        return "custom"


# ==================== 响应模型 ====================

class DepositResponse(BaseModel):
    """注入响应"""
    success: bool
    data_id: str
    message: str


class BatchDepositResponse(BaseModel):
    """批量注入响应"""
    success: bool
    total: int
    success_count: int
    skipped_count: int
    failed_count: int
    data_ids: List[str]
    message: str


class DataResponse(BaseModel):
    """数据响应（替代TaskResponse）"""
    data_id: str
    question: str
    answer: str
    source_trace_id: str
    source_request_id: str
    source_group_id: str
    caller: str
    callee: str
    caller_type: str  # 预占
    callee_type: str  # 预占
    data_type: str
    priority: int
    status: str
    annotation: Dict[str, Any]
    scores: Dict[str, Any]
    reject_reason: str = ""  # 拒绝原因
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class DataFilter(BaseModel):
    """数据过滤条件"""
    caller: Optional[str] = None
    callee: Optional[str] = None
    data_type: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    search_text: Optional[str] = None
    group_id: Optional[str] = None
    trace_id: Optional[str] = None
    request_id: Optional[str] = None  # 按request_id精确匹配
    show_p0_only: bool = False  # 只显示P0


class StatsResponse(BaseModel):
    """统计响应"""
    total: int
    pending: int
    annotated: int
    approved: int
    rejected: int
    by_priority: Dict[str, int]
    by_caller: Dict[str, int]
    by_callee: Dict[str, int]
    by_status: Dict[str, int]


class AnnotationUpdate(BaseModel):
    """标注更新请求"""
    status: Optional[str] = None
    annotation: Optional[Dict[str, Any]] = None
    scores: Optional[Dict[str, Any]] = None
