"""
Deposit API - Core API (Simplified)

Simplified Design:
- Delete parent_qa_id related logic
- Keep caller/callee
- Add source_request_id, data_type fields
- Keep group_id for aggregation
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


router = APIRouter(prefix="/api/v1", tags=["Deposit API"])


@router.post("/deposit", response_model=DepositResponse)
async def deposit_data(request: DepositRequest):
    """
    Deposit single data (Core API)
    
    Request Body:
    - source_trace_id: From OxyRequest.current_trace_id (required)
    - source_request_id: From OxyRequest.request_id (required)
    - source_group_id: From OxyRequest.group_id (optional, for aggregation)
    - question: Question/Input (required)
    - answer: Answer/Output (optional)
    - caller: Caller (required, e.g., user/agent name)
    - callee: Callee (required, e.g., agent/tool/llm name)
    - data_type: Data type (optional, used to distinguish source during annotation)
    - priority: Priority (optional, default 0, P0=End-to-End)
    
    Returns:
    - data_id: Generated unique ID
    """
    service = get_annotation_service()
    
    try:
        result = await service.deposit(request)
        return DepositResponse(**result)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to deposit data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deposit/batch", response_model=BatchDepositResponse)
async def batch_deposit_data(request: BatchDepositRequest):
    """
    Batch deposit data
    
    Suitable for scenarios where multiple data need to be deposited in one call.
    Data under the same trace_id will automatically aggregate through group_id.
    """
    service = get_annotation_service()
    
    try:
        result = await service.batch_deposit(request)
        return BatchDepositResponse(**result)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Batch deposit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
