"""
注入接口 - 核心API（简化版）

简化设计：
- 删除parent_qa_id相关逻辑
- 保留caller/callee
- 新增source_request_id、data_type字段
- 保留group_id用于聚合
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
async def deposit_data(request: DepositRequest):
    """
    注入单条数据（核心接口）
    
    请求体：
    - source_trace_id: 来自OxyRequest.current_trace_id（必填）
    - source_request_id: 来自OxyRequest.request_id（必填）
    - source_group_id: 来自OxyRequest.group_id（可选，用于聚合）
    - question: 问题/输入（必填）
    - answer: 答案/输出（可选）
    - caller: 调用者（必填，如user/agent名称）
    - callee: 被调用者（必填，如agent/tool/llm名称）
    - data_type: 数据类型（可选，用于标注时区分来源）
    - priority: 优先级（可选，默认0，P0=端到端）
    
    返回：
    - data_id: 生成的唯一ID
    """
    service = get_annotation_service()
    
    try:
        result = await service.deposit(request)
        return DepositResponse(**result)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"注入数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deposit/batch", response_model=BatchDepositResponse)
async def batch_deposit_data(request: BatchDepositRequest):
    """
    批量注入数据
    
    适用于一次调用需要注入多条数据的场景。
    同一trace_id下的数据会自动通过group_id聚合。
    """
    service = get_annotation_service()
    
    try:
        result = await service.batch_deposit(request)
        return BatchDepositResponse(**result)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"批量注入失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
