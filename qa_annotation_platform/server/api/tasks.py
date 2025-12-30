"""
数据管理接口（简化版）

替代原来的tasks接口，简化设计：
- 按group_id/trace_id聚合，不再有层级关系
- 先关注P0，再显示关联子对
- 简化ID设计（统一用data_id）
- 使用caller/callee描述调用链
"""
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..models import (
    DataFilter,
    DataResponse,
    AnnotationUpdate
)
from ..services.annotation_service import get_annotation_service


router = APIRouter(prefix="/api/v1/data", tags=["数据管理"])


# 拒绝请求体模型
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
    获取数据列表（支持过滤和分页）

    查询参数：
    - caller: 调用者过滤
    - callee: 被调用者过滤
    - data_type: 数据类型过滤（e2e/agent/llm/tool/custom）
    - status: 状态过滤（pending/annotated/approved/rejected）
    - priority: 优先级过滤（0-4，P0=端到端）
    - start_time/end_time: 时间范围
    - search: 全文搜索（搜索question/answer/caller/callee）
    - group_id: 按会话组过滤
    - trace_id: 按trace_id过滤
    - request_id: 按request_id精确匹配
    - show_p0_only: 是否只显示P0（端到端）
    - page: 页码（从1开始）
    - page_size: 每页数量（最大100）
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
    获取数据详情
    """
    service = get_annotation_service()
    
    data = await service.get_data_by_id(data_id)
    
    if not data:
        raise HTTPException(status_code=404, detail="数据不存在")
    
    return DataResponse(**data)


@router.put("/{data_id}/annotate")
async def update_annotation(
    data_id: str,
    update: AnnotationUpdate
):
    """
    更新标注结果
    
    请求体：
    - status: 新状态（可选）
    - annotation: 标注结果（可选，任意KV结构）
    - scores: 评分（可选）
    """
    service = get_annotation_service()
    
    result = await service.update_annotation(data_id, update)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result


@router.get("/trace/{trace_id}")
async def get_data_by_trace(trace_id: str):
    """
    根据trace_id获取所有关联数据
    
    返回该trace_id下所有优先级的数据（按优先级排序）。
    先显示P0（端到端），再显示子节点。
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
    根据group_id获取所有关联数据
    
    返回该group_id下所有trace的数据（用于会话聚合查看）。
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
    获取分组汇总（按group_id聚合）
    
    返回各group的统计信息，用于标注平台的分组视图。
    """
    service = get_annotation_service()
    
    result = await service.get_grouped_summary(page, page_size)
    
    return result


@router.post("/{data_id}/approve")
async def approve_data(data_id: str):
    """
    审核通过
    """
    service = get_annotation_service()
    result = await service.approve(data_id)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result


@router.post("/{data_id}/reject")
async def reject_data(data_id: str, request: RejectRequest):
    """
    审核拒绝
    """
    service = get_annotation_service()
    result = await service.reject(data_id, request.reject_reason)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result
