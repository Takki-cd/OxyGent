"""
统计接口
"""
from fastapi import APIRouter

from ..models import StatsResponse
from ..services.annotation_service import get_annotation_service


router = APIRouter(prefix="/api/v1/stats", tags=["统计接口"])


@router.get("")
async def get_stats() -> StatsResponse:
    """
    获取标注统计信息
    
    返回：
    - total: 总数
    - pending: 待标注数量
    - annotated: 已标注数量
    - approved: 已通过数量
    - rejected: 已拒绝数量
    - by_priority: 按优先级分布
    - by_type: 按类型分布
    - by_status: 按状态分布
    """
    service = get_annotation_service()
    return await service.get_stats()


@router.get("/low-score")
async def get_low_score_tasks(threshold: float = 0.6):
    """
    获取低分任务（需要关注的任务）
    
    查询参数：
    - threshold: 分数阈值（默认0.6）
    
    返回评分较低的根节点，这些节点可能需要查看子节点进行深入分析。
    """
    service = get_annotation_service()
    
    low_score_roots = await service.es_service._get_low_score_root_qa_ids(threshold)
    
    return {
        "threshold": threshold,
        "count": len(low_score_roots),
        "qa_ids": low_score_roots
    }
