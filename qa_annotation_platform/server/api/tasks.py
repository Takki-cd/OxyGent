"""
Data Management API (Simplified)

Replace original tasks API, simplified design:
- Aggregate by group_id/trace_id, no hierarchical relationships
- Focus on P0 first, then show related child pairs
- Simplified ID design (unified use data_id)
- Use caller/callee to describe call chain
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..models import (
    DataFilter,
    DataResponse,
    AnnotationUpdate
)
from ..services.annotation_service import get_annotation_service


router = APIRouter(prefix="/api/v1/data", tags=["Data Management"])


# Reject Request Body Model
class RejectRequest(BaseModel):
    reject_reason: str = ""


@router.get("")
async def get_data_list(
    caller: Optional[str] = None,
    callee: Optional[str] = None,
    data_type: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    search: Optional[str] = None,
    group_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    show_p0_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """
    Get data list (support filtering and pagination)

    Query parameters:
    - caller: Caller filter
    - callee: Callee filter
    - data_type: Data type filter (e2e/agent/llm/tool/custom)
    - status: Status filter (pending/annotated/approved/rejected)
    - priority: Priority filter (0-4, P0=End-to-End)
    - start_time/end_time: Time range
    - search: Full-text search (search question/answer/caller/callee)
    - group_id: Filter by session group
    - trace_id: Filter by trace_id
    - request_id: Exact match by request_id
    - show_p0_only: Only show P0 (End-to-End)
    - page: Page number (starting from 1)
    - page_size: Items per page (max 100)
    """
    service = get_annotation_service()

    filter_params = DataFilter(
        caller=caller,
        callee=callee,
        data_type=data_type,
        status=status,
        priority=priority,
        start_time=start_time,
        end_time=end_time,
        search_text=search,
        group_id=group_id,
        trace_id=trace_id,
        request_id=request_id,
        show_p0_only=show_p0_only
    )

    result = await service.get_data_list(filter_params, page, page_size)

    return {
        "items": [
            DataResponse(**item).model_dump()
            for item in result["items"]
        ],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"]
    }


@router.get("/{data_id}")
async def get_data(data_id: str):
    """
    Get data details
    """
    service = get_annotation_service()
    
    data = await service.get_data_by_id(data_id)
    
    if not data:
        raise HTTPException(status_code=404, detail="Data not found")
    
    return DataResponse(**data)


@router.put("/{data_id}/annotate")
async def update_annotation(
    data_id: str,
    update: AnnotationUpdate
):
    """
    Update annotation result
    
    Request body:
    - status: New status (optional)
    - annotation: Annotation result (optional, any KV structure)
    - scores: Scores (optional)
    """
    service = get_annotation_service()
    
    result = await service.update_annotation(data_id, update)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result


@router.get("/trace/{trace_id}")
async def get_data_by_trace(trace_id: str):
    """
    Get all related data by trace_id
    
    Return all data under this trace_id (sorted by priority).
    Show P0 (End-to-End) first, then child nodes.
    """
    service = get_annotation_service()
    
    data_list = await service.get_by_trace_id(trace_id)
    
    return {
        "source_trace_id": trace_id,
        "total": len(data_list),
        "items": data_list
    }


@router.get("/group/{group_id}")
async def get_data_by_group(group_id: str, limit: int = Query(100, ge=1, le=1000)):
    """
    Get all related data by group_id
    
    Return all trace data under this group_id (for session aggregation view).
    """
    service = get_annotation_service()
    
    data_list = await service.get_by_group_id(group_id, limit)
    
    return {
        "source_group_id": group_id,
        "total": len(data_list),
        "items": data_list
    }


@router.get("/groups/summary")
async def get_groups_summary(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """
    Get grouped summary (aggregate by group_id)
    
    Return statistics for each group, used for annotation platform's group view.
    """
    service = get_annotation_service()
    
    result = await service.get_grouped_summary(page, page_size)
    
    return result


@router.post("/{data_id}/approve")
async def approve_data(data_id: str):
    """
    Approve review
    """
    service = get_annotation_service()
    result = await service.approve(data_id)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result


@router.post("/{data_id}/reject")
async def reject_data(data_id: str, request: RejectRequest):
    """
    Reject review
    """
    service = get_annotation_service()
    result = await service.reject(data_id, request.reject_reason)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result


# ==================== Knowledge Base Ingestion Endpoints ====================

class IngestKBRequest(BaseModel):
    """Knowledge Base Ingestion Request"""
    remark: Optional[str] = None


@router.post("/{data_id}/ingest-kb")
async def ingest_to_kb(data_id: str, request: IngestKBRequest = None):
    """
    Ingest data to Knowledge Base
    
    Trigger KB ingestion for a single approved data item.
    """
    service = get_annotation_service()
    result = await service.ingest_to_kb(data_id, request.remark if request else None)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result


# ==================== Knowledge Base Status Endpoints ====================

@router.get("/kb/status")
async def get_kb_status():
    """
    Get Knowledge Base ingestion status and statistics
    """
    from ..config import get_app_config
    from ..models import DataStatus
    
    config = get_app_config()
    
    # Check if KB is configured
    kb_enabled = (
        config.kb.enabled and 
        bool(config.kb.endpoint) and 
        bool(config.kb.kb_id)
    )
    
    service = get_annotation_service()
    stats = await service.get_stats()
    
    return {
        "enabled": kb_enabled,
        "config": {
            "endpoint": config.kb.endpoint,
            "kb_id": config.kb.kb_id,
            "auto_ingest": config.kb.auto_ingest
        },
        "statistics": {
            "kb_ingested": stats.kb_ingested,
            "kb_failed": stats.kb_failed
        }
    }
