"""
QA Annotation Platform - Data Model Definition

Simplified: Delete hierarchical relationships, aggregate by group_id/trace_id
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field
import uuid
import hashlib


class DataType(str, Enum):
    """Data Type (describes data source type)"""
    E2E = "e2e"              # End-to-End (User -> Agent)
    AGENT = "agent"          # Agent Call
    LLM = "llm"              # LLM Call
    TOOL = "tool"            # Tool Call
    CUSTOM = "custom"        # Custom


class Priority(int, Enum):
    """Priority Definition"""
    P0 = 0       # End-to-End (Highest Priority)
    P1 = 1       # Level 1 Child Node
    P2 = 2       # Level 2 Child Node
    P3 = 3       # Level 3 Child Node
    P4 = 4       # Other


class DataStatus(str, Enum):
    """Data Status"""
    PENDING = "pending"       # Pending Annotation
    ANNOTATED = "annotated"   # Annotated
    APPROVED = "approved"     # Approved
    REJECTED = "rejected"     # Rejected
    # Knowledge Base Ingestion Status
    KB_INGESTED = "kb_ingested"  # Successfully Ingested to Knowledge Base
    KB_FAILED = "kb_failed"   # Knowledge Base Ingestion Failed


# ==================== Request Models ====================

class DepositRequest(BaseModel):
    """
    Deposit Data Request
    
    Core Field Description:
    - source_trace_id: From Oxygent's current_trace_id (required)
    - source_request_id: From Oxygent's request_id (required)
    - source_group_id: From Oxygent's group_id (optional, for session aggregation)
    - question: Question/Input (required)
    - answer: Answer/Output (optional)
    - caller: Caller (required, e.g., user/agent name)
    - callee: Callee (required, e.g., agent/tool/llm name)
    - priority: Priority (optional, default 0, P0=End-to-End)
    - data_type: Data type (optional, used to distinguish source during annotation)
    """
    # Required: Source tracing information
    source_trace_id: str = Field(..., description="Original trace_id (from OxyRequest.current_trace_id)")
    source_request_id: str = Field(..., description="Original request_id (from OxyRequest.request_id)")
    source_group_id: Optional[str] = Field(None, description="group_id (from OxyRequest.group_id)")
    
    # Required: QA Content
    question: str = Field(..., description="Question/Input")
    answer: str = Field("", description="Answer/Output")
    
    # Required: Call Chain Information (caller/callee)
    caller: str = Field(..., description="Caller (user/agent name)")
    callee: str = Field(..., description="Callee (agent/tool/llm name)")
    
    # Optional: Call type (reserved, for future expansion)
    caller_type: Optional[str] = Field(None, description="Caller type (reserved)")
    callee_type: Optional[str] = Field(None, description="Callee type (reserved)")
    
    # Optional: Data type (used to distinguish source during annotation)
    data_type: Optional[str] = Field(None, description="Data type: e2e/agent/llm/tool/custom")
    
    # Optional: Priority (End-to-End must be P0=0, others as needed)
    priority: int = Field(0, ge=0, le=4, description="Priority 0-4, P0=End-to-End")
    
    # Optional: Category & Tags
    category: Optional[str] = Field(None, description="Category")
    tags: List[str] = Field(default_factory=list, description="Tags")
    
    # Optional: Extra Data
    extra: Dict[str, Any] = Field(default_factory=dict, description="Extra data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_trace_id": "abc123",
                "source_request_id": "req_001",
                "source_group_id": "session_001",
                "question": "User input",
                "answer": "Agent output",
                "caller": "user",
                "callee": "my_agent",
                "data_type": "e2e",
                "priority": 0  # End-to-End must be P0
            }
        }
    
    def compute_data_hash(self) -> str:
        """Compute data deduplication hash"""
        content = f"{self.source_trace_id}:{self.source_request_id}:{self.question}:{self.answer}"
        return hashlib.md5(content.encode()).hexdigest()


class BatchDepositRequest(BaseModel):
    """Batch Deposit Request"""
    items: List[DepositRequest]
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "source_trace_id": "abc123",
                        "source_request_id": "req_001",
                        "source_group_id": "session_001",
                        "question": "User input",
                        "answer": "Agent output",
                        "caller": "user",
                        "callee": "my_agent",
                        "priority": 0  # End-to-End
                    },
                    {
                        "source_trace_id": "abc123",
                        "source_request_id": "req_002",
                        "source_group_id": "session_001",
                        "question": "LLM call",
                        "answer": "LLM response",
                        "caller": "my_agent",
                        "callee": "gpt-4",
                        "priority": 2
                    }
                ]
            }
        }


# ==================== Storage Models ====================

class QAData(BaseModel):
    """
    QA Data (Storage Model)
    
    Simplified Design:
    - One unique ID (data_id) instead of qa_id and task_id
    - Aggregate by group_id/trace_id, no parent_qa_id
    - End-to-End identified by priority=0
    - Use caller/callee to describe call chain
    """
    # Unique ID (instead of qa_id and task_id)
    data_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # QA Content
    question: str
    answer: str = ""
    data_hash: str
    
    # Source Tracing
    source_trace_id: str
    source_request_id: str
    source_group_id: str = ""
    
    # Call Chain Information
    caller: str
    callee: str
    caller_type: str = ""  # Reserved: Caller type
    callee_type: str = ""  # Reserved: Callee type
    
    # Data Type (used to distinguish source during annotation)
    data_type: str = ""
    
    # Priority (End-to-End=0, Child nodes>0)
    priority: int = 4
    
    # Category & Tags
    category: str = ""
    tags: List[str] = Field(default_factory=list)
    
    # Status
    status: str = DataStatus.PENDING.value
    
    # Annotation Result
    annotation: Dict[str, Any] = Field(default_factory=dict)
    scores: Dict[str, Any] = Field(default_factory=dict)
    
    # Knowledge Base Ingestion Information
    kb_status: str = ""  # Knowledge base ingestion status
    kb_ingested_at: Optional[datetime] = None  # Ingestion timestamp
    kb_error_message: str = ""  # Error message if ingestion failed
    kb_extra: Dict[str, Any] = Field(default_factory=dict)  # Additional KB metadata
    
    # Batch Information
    batch_id: str = ""
    
    # Timestamp
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # Extra Data
    extra: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        from_attributes = True
    
    def to_es_doc(self) -> Dict[str, Any]:
        """Convert to ES document"""
        data = self.model_dump()
        # Convert datetime to string
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = self.created_at.strftime("%Y-%m-%d %H:%M:%S.%f")
        if isinstance(data.get("updated_at"), datetime):
            data["updated_at"] = self.updated_at.strftime("%Y-%m-%d %H:%M:%S.%f")
        if isinstance(data.get("kb_ingested_at"), datetime):
            data["kb_ingested_at"] = self.kb_ingested_at.strftime("%Y-%m-%d %H:%M:%S.%f")
        return data
    
    @classmethod
    def from_deposit_request(
        cls, 
        request: DepositRequest,
        batch_id: str = ""
    ) -> "QAData":
        """Create QAData from DepositRequest"""
        # Auto-infer data_type
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
        """Infer data type"""
        # P0 End-to-End
        if request.priority == 0:
            return "e2e"
        
        # Infer by callee
        callee_lower = request.callee.lower()
        if any(keyword in callee_lower for keyword in ["llm", "gpt", "model", "openai", "anthropic"]):
            return "llm"
        if any(keyword in callee_lower for keyword in ["tool", "api", "search", "fetch"]):
            return "tool"
        if any(keyword in callee_lower for keyword in ["agent"]):
            return "agent"
        
        return "custom"


# ==================== Response Models ====================

class DepositResponse(BaseModel):
    """Deposit Response"""
    success: bool
    data_id: str
    message: str


class BatchDepositResponse(BaseModel):
    """Batch Deposit Response"""
    success: bool
    total: int
    success_count: int
    skipped_count: int
    failed_count: int
    data_ids: List[str]
    message: str


class DataResponse(BaseModel):
    """Data Response (instead of TaskResponse)"""
    data_id: str
    question: str
    answer: str
    source_trace_id: str
    source_request_id: str
    source_group_id: str
    caller: str
    callee: str
    caller_type: str  # Reserved
    callee_type: str  # Reserved
    data_type: str
    priority: int
    status: str
    annotation: Dict[str, Any]
    scores: Dict[str, Any]
    reject_reason: str = ""  # Reject reason
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class DataFilter(BaseModel):
    """Data Filter Conditions"""
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
    request_id: Optional[str] = None  # Exact match by request_id
    show_p0_only: bool = False  # Only show P0


class StatsResponse(BaseModel):
    """Statistics Response"""
    total: int
    pending: int
    annotated: int
    approved: int
    rejected: int
    # Knowledge Base Statistics
    kb_ingested: int = 0  # Successfully ingested to KB
    kb_failed: int = 0  # KB ingestion failed
    by_priority: Dict[str, int]
    by_caller: Dict[str, int]
    by_callee: Dict[str, int]
    by_status: Dict[str, int]


class AnnotationUpdate(BaseModel):
    """Annotation Update Request"""
    status: Optional[str] = None
    annotation: Optional[Dict[str, Any]] = None
    scores: Optional[Dict[str, Any]] = None


class KBIngestionRequest(BaseModel):
    """Knowledge Base Ingestion Request - Request format for KB API"""
    question: str = Field(..., description="Question/Input")
    answer: str = Field(..., description="Answer/Output")
    score: Optional[float] = Field(None, description="Quality score (0-1)")
    caller: str = Field(..., description="Caller name")
    callee: str = Field(..., description="Callee name")
    remark: Optional[str] = Field(None, description="Additional remarks")
    
    # Optional metadata
    source_trace_id: Optional[str] = Field(None, description="Original trace_id")
    source_request_id: Optional[str] = Field(None, description="Original request_id")
    data_type: Optional[str] = Field(None, description="Data type")
    priority: Optional[int] = Field(None, description="Priority")
    category: Optional[str] = Field(None, description="Category")
    tags: List[str] = Field(default_factory=list, description="Tags")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What is the capital of France?",
                "answer": "Paris is the capital of France.",
                "score": 0.95,
                "caller": "user",
                "callee": "chat_agent",
                "remark": "High quality Q&A pair"
            }
        }


class KBIngestionResponse(BaseModel):
    """Knowledge Base Ingestion Response"""
    success: bool
    message: str
    kb_doc_id: Optional[str] = None  # Document ID returned by KB platform
