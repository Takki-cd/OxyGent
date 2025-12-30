"""
注入接口 - 核心API

提供RESTful接口供外部调用
"""
import logging
from typing import List
from fastapi import APIRouter, HTTPException

from ..models import (
    DepositRequest, 
    BatchDepositRequest,
    DepositResponse,
    BatchDepositResponse
)
from ..services.annotation_service import get_annotation_service


router = APIRouter(prefix="/api/v1", tags=["注入接口"])


@router.post("/deposit", response_model=DepositResponse)
async def deposit_qa(request: DepositRequest):
    """
    注入单条QA数据（核心接口）
    
    请求体：
    - source_trace_id: 来自OxyRequest.current_trace_id（必填）
    - source_group_id: 来自OxyRequest.group_id（可选）
    - source_node_id: 节点ID（可选）
    - question: 问题/输入（必填）
    - answer: 答案/输出（可选）
    - is_root: 是否为根节点（可选，默认False）
    - parent_qa_id: 父QA ID（可选，用于子节点串联）
    - source_type: 来源类型（可选，自动推断）
    - priority: 优先级0-4（可选，自动推断）
    - caller/callee: 调用链信息（可选）
    
    返回：
    - qa_id: 生成的唯一ID
    - task_id: 任务ID
    """
    service = get_annotation_service()
    
    try:
        result = await service.deposit(request)
        return DepositResponse(**result)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"注入QA失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deposit/batch", response_model=BatchDepositResponse)
async def batch_deposit_qa(request: BatchDepositRequest):
    """
    批量注入QA数据
    
    适用于一次调用需要注入多条QA的场景。
    支持链式关系：子节点可通过parent_qa_id指向父节点。
    """
    service = get_annotation_service()
    
    try:
        result = await service.batch_deposit(request)
        return BatchDepositResponse(**result)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"批量注入失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deposit/root")
async def deposit_root(request: DepositRequest):
    """
    注入根节点（端到端QA）
    
    快捷接口，等效于 is_root=True
    """
    request.is_root = True
    return await deposit_qa(request)


@router.post("/deposit/child/{parent_qa_id}")
async def deposit_child(
    parent_qa_id: str,
    request: DepositRequest
):
    """
    注入子节点（自动串联到父节点）
    
    路径参数：
    - parent_qa_id: 父QA ID
    
    请求体：同/deposit，但不包含parent_qa_id
    """
    service = get_annotation_service()
    
    # 验证父节点存在
    parent_task = await service.get_task_by_id(parent_qa_id)
    if not parent_task:
        raise HTTPException(status_code=404, detail="父节点不存在")
    
    # 设置parent_qa_id
    request.parent_qa_id = parent_qa_id
    
    # 尝试使用QAContext建立内存关联
    from ..services.annotation_service import QAContext
    qa_id = QAContext.create_child(
        parent_qa_id=parent_qa_id,
        trace_id=request.source_trace_id,
        question=request.question,
        answer=request.answer,
        node_type=request.source_type.value if hasattr(request.source_type, 'value') else str(request.source_type or ""),
        caller=request.caller,
        callee=request.callee
    )
    
    if qa_id:
        request.extra = request.extra or {}
        request.extra["context_qa_id"] = qa_id
    
    return await deposit_qa(request)
