"""
任务管理接口
"""
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query

from ..models import (
    QATaskStatus, 
    TaskFilter,
    TaskResponse,
    AnnotationUpdate
)
from ..services.annotation_service import get_annotation_service


router = APIRouter(prefix="/api/v1/tasks", tags=["任务管理"])


@router.get("")
async def get_tasks(
    qa_type: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    search: Optional[str] = None,
    group_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    show_children: bool = False,
    show_roots_only: bool = False,  # 修改默认值为 False，显示所有数据
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """
    获取任务列表（支持过滤和分页）
    
    查询参数：
    - qa_type: 来源类型过滤（e2e/agent/tool/llm）
    - status: 状态过滤（pending/annotated/approved/rejected）
    - priority: 优先级过滤（0-4）
    - start_time/end_time: 时间范围
    - search: 全文搜索（搜索question/answer）
    - group_id: 按会话组过滤
    - trace_id: 按trace_id过滤
    - show_children: 是否显示子节点
    - show_roots_only: 是否只显示根节点（默认false，显示所有数据）
    - page: 页码（从1开始）
    - page_size: 每页数量（最大100）
    """
    service = get_annotation_service()
    
    filter_params = TaskFilter(
        qa_type=qa_type,
        status=status,
        priority=priority,
        start_time=start_time,
        end_time=end_time,
        search_text=search,
        group_id=group_id,
        trace_id=trace_id,
        show_children=show_children,
        show_roots_only=show_roots_only
    )
    
    result = await service.get_tasks(filter_params, page, page_size)
    
    return {
        "items": [
            TaskResponse(**item).model_dump() 
            for item in result["items"]
        ],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"]
    }


@router.get("/{qa_id}")
async def get_task(qa_id: str):
    """
    获取任务详情
    """
    service = get_annotation_service()
    
    task = await service.get_task_by_id(qa_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return TaskResponse(**task)


@router.put("/{qa_id}/annotate")
async def update_annotation(
    qa_id: str,
    update: AnnotationUpdate
):
    """
    更新标注结果
    
    请求体：
    - status: 新状态（可选）
    - annotation: 标注结果（可选，任意KV结构）
    - scores: 评分（可选，用于判断是否需要展示子节点）
    """
    service = get_annotation_service()
    
    result = await service.update_annotation(qa_id, update)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result


@router.get("/{qa_id}/children")
async def get_task_children(qa_id: str):
    """
    获取指定任务的子节点
    
    用于深入分析低分根节点的调用链。
    """
    service = get_annotation_service()
    
    # 先获取当前任务
    task = await service.get_task_by_id(qa_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 获取子节点
    children = await service.get_children(qa_id)
    
    return {
        "parent": task,
        "children": children
    }


@router.post("/{qa_id}/approve")
async def approve_task(qa_id: str):
    """
    审核通过
    """
    service = get_annotation_service()
    result = await service.approve(qa_id)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result


@router.post("/{qa_id}/reject")
async def reject_task(qa_id: str):
    """
    审核拒绝
    """
    service = get_annotation_service()
    result = await service.reject(qa_id)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result
