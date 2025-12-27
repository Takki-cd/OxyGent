# -*- encoding: utf-8 -*-
"""
QA标注平台 - API路由

提供标注平台的REST API接口
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from oxygent.config import Config
from oxygent.schemas import WebResponse

logger = logging.getLogger(__name__)

# 创建路由器
qa_router = APIRouter(prefix="/api/qa", tags=["QA Annotation"])


# =============================================================================
# 请求/响应模型
# =============================================================================

class ImportPreviewRequest(BaseModel):
    """导入预览请求"""
    start_time: str
    end_time: str
    include_trace: bool = True
    include_node_agent: bool = True
    include_node_tool: bool = False


class ImportExecuteRequest(BaseModel):
    """执行导入请求"""
    start_time: str
    end_time: str
    include_trace: bool = True
    include_node_agent: bool = True
    include_node_tool: bool = False
    include_sub_nodes: bool = True
    limit: int = 1000


class AnnotationSubmitRequest(BaseModel):
    """提交标注请求"""
    task_id: str
    annotator_id: str
    annotated_question: str
    annotated_answer: str
    quality_label: str = "acceptable"
    is_useful: bool = True
    correction_type: str = "none"
    domain: str = ""
    intent: str = ""
    complexity: str = ""
    should_add_to_kb: bool = False
    kb_category: str = ""
    annotation_notes: str = ""
    time_cost: int = 0


class ReviewRequest(BaseModel):
    """审核请求"""
    annotation_id: str
    reviewer_id: str
    review_status: str
    review_comment: str = ""


class TaskAssignRequest(BaseModel):
    """任务分配请求"""
    task_id: str
    assigned_to: str


# =============================================================================
# 全局ES客户端引用（由MAS初始化时设置）
# =============================================================================

_es_client = None
_mq_client = None


def set_qa_clients(es_client, mq_client=None):
    """设置QA模块使用的客户端"""
    global _es_client, _mq_client
    _es_client = es_client
    _mq_client = mq_client


def get_es_client():
    """获取ES客户端"""
    if _es_client is None:
        raise HTTPException(status_code=500, detail="ES client not initialized")
    return _es_client


# =============================================================================
# 导入相关API
# =============================================================================

@qa_router.post("/import/preview")
async def preview_import(request: ImportPreviewRequest):
    """
    预览导入数据量
    
    在执行导入前，先预览各数据源的数据量
    """
    if not Config.is_qa_annotation_enabled():
        return WebResponse(code=400, message="QA annotation is not enabled").to_dict()
    
    try:
        from .services import ImportService
        service = ImportService(get_es_client())
        
        result = await service.preview_import(
            start_time=request.start_time,
            end_time=request.end_time,
            include_trace=request.include_trace,
            include_node_agent=request.include_node_agent,
            include_node_tool=request.include_node_tool,
        )
        
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"Preview import failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.post("/import/execute")
async def execute_import(request: ImportExecuteRequest):
    """
    执行导入
    
    从ES历史数据中导入QA数据到标注平台
    """
    if not Config.is_qa_annotation_enabled():
        return WebResponse(code=400, message="QA annotation is not enabled").to_dict()
    
    try:
        from .services import ImportService
        service = ImportService(get_es_client())
        
        result = await service.execute_import(
            start_time=request.start_time,
            end_time=request.end_time,
            include_trace=request.include_trace,
            include_node_agent=request.include_node_agent,
            include_node_tool=request.include_node_tool,
            include_sub_nodes=request.include_sub_nodes,
            limit=request.limit,
        )
        
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"Execute import failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/import/date-range")
async def get_import_date_range():
    """获取可导入的数据日期范围"""
    if not Config.is_qa_annotation_enabled():
        return WebResponse(code=400, message="QA annotation is not enabled").to_dict()
    
    try:
        from .services import ImportService
        service = ImportService(get_es_client())
        result = await service.get_available_date_range()
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"Get date range failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


# =============================================================================
# 任务相关API
# =============================================================================

@qa_router.get("/tasks")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    priority: Optional[int] = None,
    source_type: Optional[str] = None,
    assigned_to: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    """
    查询任务列表
    
    支持分页、筛选、搜索和排序
    """
    try:
        from .services import TaskService
        service = TaskService(get_es_client())
        
        result = await service.list_tasks(
            page=page,
            page_size=page_size,
            status=status,
            priority=priority,
            source_type=source_type,
            assigned_to=assigned_to,
            search_keyword=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"List tasks failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    try:
        from .services import TaskService
        service = TaskService(get_es_client())
        
        task = await service.get_task(task_id)
        if not task:
            return WebResponse(code=404, message="Task not found").to_dict()
        
        return WebResponse(data=task).to_dict()
    except Exception as e:
        logger.error(f"Get task failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/tasks/{task_id}/with-children")
async def get_task_with_children(task_id: str):
    """获取任务及其子任务（展示归属关系）"""
    try:
        from .services import TaskService
        service = TaskService(get_es_client())
        
        result = await service.get_task_with_children(task_id)
        if not result.get("task"):
            return WebResponse(code=404, message="Task not found").to_dict()
        
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"Get task with children failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.post("/tasks/assign")
async def assign_task(request: TaskAssignRequest):
    """分配任务给标注者"""
    try:
        from .services import TaskService
        service = TaskService(get_es_client())
        
        success = await service.assign_task(request.task_id, request.assigned_to)
        if success:
            return WebResponse(data={"success": True}).to_dict()
        else:
            return WebResponse(code=400, message="Failed to assign task").to_dict()
    except Exception as e:
        logger.error(f"Assign task failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/tasks/pending/list")
async def get_pending_tasks(
    annotator_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """获取待标注任务列表"""
    try:
        from .services import TaskService
        service = TaskService(get_es_client())
        
        result = await service.get_pending_tasks_for_annotator(
            annotator_id=annotator_id,
            page=page,
            page_size=page_size,
        )
        
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"Get pending tasks failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/tasks/stats")
async def get_task_stats():
    """获取任务统计信息"""
    try:
        from .services import TaskService
        service = TaskService(get_es_client())
        
        result = await service.get_stats()
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"Get task stats failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


# =============================================================================
# 标注相关API
# =============================================================================

@qa_router.post("/annotations/submit")
async def submit_annotation(request: AnnotationSubmitRequest):
    """提交标注结果"""
    try:
        from .services import AnnotationService
        service = AnnotationService(get_es_client(), _mq_client)
        
        result = await service.submit_annotation(
            task_id=request.task_id,
            annotator_id=request.annotator_id,
            annotated_question=request.annotated_question,
            annotated_answer=request.annotated_answer,
            quality_label=request.quality_label,
            is_useful=request.is_useful,
            correction_type=request.correction_type,
            domain=request.domain,
            intent=request.intent,
            complexity=request.complexity,
            should_add_to_kb=request.should_add_to_kb,
            kb_category=request.kb_category,
            annotation_notes=request.annotation_notes,
            time_cost=request.time_cost,
        )
        
        if result.get("success"):
            return WebResponse(data=result).to_dict()
        else:
            return WebResponse(code=400, message=result.get("message")).to_dict()
    except Exception as e:
        logger.error(f"Submit annotation failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/annotations/{annotation_id}")
async def get_annotation(annotation_id: str):
    """获取标注详情"""
    try:
        from .services import AnnotationService
        service = AnnotationService(get_es_client())
        
        annotation = await service.get_annotation(annotation_id)
        if not annotation:
            return WebResponse(code=404, message="Annotation not found").to_dict()
        
        return WebResponse(data=annotation).to_dict()
    except Exception as e:
        logger.error(f"Get annotation failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/annotations/by-task/{task_id}")
async def get_annotation_by_task(task_id: str):
    """根据任务ID获取标注"""
    try:
        from .services import AnnotationService
        service = AnnotationService(get_es_client())
        
        annotation = await service.get_annotation_by_task(task_id)
        if not annotation:
            return WebResponse(code=404, message="Annotation not found").to_dict()
        
        return WebResponse(data=annotation).to_dict()
    except Exception as e:
        logger.error(f"Get annotation by task failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.post("/annotations/review")
async def review_annotation(request: ReviewRequest):
    """审核标注"""
    try:
        from .services import AnnotationService
        service = AnnotationService(get_es_client(), _mq_client)
        
        result = await service.review_annotation(
            annotation_id=request.annotation_id,
            reviewer_id=request.reviewer_id,
            review_status=request.review_status,
            review_comment=request.review_comment,
        )
        
        if result.get("success"):
            return WebResponse(data=result).to_dict()
        else:
            return WebResponse(code=400, message=result.get("message")).to_dict()
    except Exception as e:
        logger.error(f"Review annotation failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


# =============================================================================
# MQ状态相关API
# =============================================================================

@qa_router.get("/mq/stats")
async def get_mq_stats():
    """获取消息队列统计信息"""
    try:
        from .mq_factory import MQFactory
        
        mq = MQFactory().get_instance_sync()
        if not mq:
            return WebResponse(code=400, message="MQ not initialized").to_dict()
        
        stats = await mq.get_all_stats()
        return WebResponse(data=stats).to_dict()
    except Exception as e:
        logger.error(f"Get MQ stats failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/mq/health")
async def check_mq_health():
    """检查MQ健康状态"""
    try:
        from .mq_factory import MQFactory
        
        mq = MQFactory().get_instance_sync()
        if not mq:
            return WebResponse(data={"healthy": False, "message": "MQ not initialized"}).to_dict()
        
        healthy = await mq.health_check()
        return WebResponse(data={"healthy": healthy}).to_dict()
    except Exception as e:
        logger.error(f"MQ health check failed: {e}")
        return WebResponse(data={"healthy": False, "message": str(e)}).to_dict()


# =============================================================================
# 配置检查API
# =============================================================================

@qa_router.get("/config")
async def get_qa_config():
    """获取QA标注平台配置"""
    try:
        config = {
            "enabled": Config.is_qa_annotation_enabled(),
            "realtime_hook_enabled": Config.is_qa_realtime_hook_enabled(),
            "llm_processor_enabled": Config.is_qa_llm_processor_enabled(),
            "mq_type": Config.get_qa_mq_type(),
            "collector_config": Config.get_qa_collector_config(),
            "task_config": Config.get_qa_task_config(),
            "platform_config": Config.get_qa_platform_config(),
        }
        return WebResponse(data=config).to_dict()
    except Exception as e:
        logger.error(f"Get QA config failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()

