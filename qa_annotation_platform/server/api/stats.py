"""
统计接口（支持时间过滤）
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from ..models import StatsResponse
from ..services.annotation_service import get_annotation_service


router = APIRouter(prefix="/api/v1/stats", tags=["统计接口"])


@router.get("")
async def get_stats(
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间")
) -> StatsResponse:
    """
    获取标注统计信息（支持时间过滤）
    
    查询参数：
    - start_time: 开始时间
    - end_time: 结束时间
    
    返回：
    - total: 总数
    - pending: 待标注数量
    - annotated: 已标注数量
    - approved: 已通过数量
    - rejected: 已拒绝数量
    - by_priority: 按优先级分布
    - by_oxy_type: 按组件类型分布
    - by_status: 按状态分布
    """
    service = get_annotation_service()
    return await service.get_stats(start_time=start_time, end_time=end_time)


@router.get("/pending-p0")
async def get_pending_p0():
    """
    获取待标注的P0数据（优先处理的任务）
    
    返回所有待标注的端到端数据。
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
        "description": "待标注的端到端数据（P0优先级）",
        "count": result["total"],
        "items": result["items"]
    }


@router.get("/by-oxy-type")
async def get_stats_by_oxy_type():
    """
    按组件类型获取统计
    """
    service = get_annotation_service()
    stats = await service.get_stats()
    
    return {
        "by_oxy_type": stats.by_oxy_type,
        "total": stats.total
    }
