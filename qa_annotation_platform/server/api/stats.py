"""
Statistics API (support time filtering)
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from ..models import StatsResponse
from ..services.annotation_service import get_annotation_service


router = APIRouter(prefix="/api/v1/stats", tags=["Statistics"])


@router.get("")
async def get_stats(
    start_time: Optional[datetime] = Query(None, description="Start time"),
    end_time: Optional[datetime] = Query(None, description="End time")
) -> StatsResponse:
    """
    Get annotation statistics (support time filtering)
    
    Query parameters:
    - start_time: Start time
    - end_time: End time
    
    Returns:
    - total: Total count
    - pending: Pending count
    - annotated: Annotated count
    - approved: Approved count
    - rejected: Rejected count
    - by_priority: Distribution by priority
    - by_oxy_type: Distribution by component type
    - by_status: Distribution by status
    """
    service = get_annotation_service()
    return await service.get_stats(start_time=start_time, end_time=end_time)


@router.get("/pending-p0")
async def get_pending_p0():
    """
    Get pending P0 data (priority tasks)
    
    Return all pending End-to-End data.
    """
    from ..models import DataFilter
    
    service = get_annotation_service()
    
    filter_params = DataFilter(
        status="pending",
        show_p0_only=True
    )
    
    result = await service.get_data_list(filter_params, page=1, page_size=100)
    
    return {
        "type": "pending_p0",
        "description": "Pending End-to-End data (P0 priority)",
        "count": result["total"],
        "items": result["items"]
    }


@router.get("/by-oxy-type")
async def get_stats_by_oxy_type():
    """
    Get statistics by component type
    """
    service = get_annotation_service()
    stats = await service.get_stats()
    
    return {
        "by_oxy_type": stats.by_oxy_type,
        "total": stats.total
    }
