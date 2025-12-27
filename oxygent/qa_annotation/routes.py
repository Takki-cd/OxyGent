# -*- encoding: utf-8 -*-
"""
QA标注平台 - API路由

提供标注平台的REST API接口

MVP版本核心接口：
1. QA提取：从ES提取数据并建立层级关系
2. 任务管理：树形结构查询、任务分配
3. 标注操作：提交标注、审核
"""

import logging
from typing import Optional, List
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from oxygent.config import Config
from oxygent.schemas import WebResponse

logger = logging.getLogger(__name__)

# 创建路由器
qa_router = APIRouter(prefix="/api/qa", tags=["QA Annotation"])


# =============================================================================
# 时区配置（从config读取）
# =============================================================================

def get_default_time_range():
    """获取默认时间范围（从config读取，默认往前N小时）"""
    try:
        import pytz
        tz_name = Config.get_qa_timezone()
        tz = pytz.timezone(tz_name)
        now = datetime.now(tz)
        hours_before = Config.get_qa_default_hours_before()
        end_time = now.strftime("%Y-%m-%d %H:%M:%S")
        start_time = (now - timedelta(hours=hours_before)).strftime("%Y-%m-%d %H:%M:%S")
        return start_time, end_time
    except ImportError:
        # 如果没有 pytz，使用 UTC 时间
        now = datetime.now()
        hours_before = Config.get_qa_default_hours_before()
        end_time = now.strftime("%Y-%m-%d %H:%M:%S")
        start_time = (now - timedelta(hours=hours_before)).strftime("%Y-%m-%d %H:%M:%S")
        return start_time, end_time


# 预先计算默认时间（应用启动时）
_DEFAULT_START_TIME, _DEFAULT_END_TIME = get_default_time_range()


# =============================================================================
# 请求/响应模型
# =============================================================================

class ExtractionRequest(BaseModel):
    """QA提取请求（带默认时间范围）"""
    start_time: str = _DEFAULT_START_TIME
    end_time: str = _DEFAULT_END_TIME
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
    review_status: str  # approved / rejected / needs_revision
    review_comment: str = ""


class TaskAssignRequest(BaseModel):
    """任务分配请求"""
    task_id: str
    assigned_to: str


class TaskStatusUpdateRequest(BaseModel):
    """任务状态更新请求"""
    task_id: str
    status: str
    stage: Optional[str] = None


# =============================================================================
# Service单例管理
# =============================================================================

from .services import (
    set_service_clients,
    get_extraction_service,
    get_task_service,
    get_annotation_service,
)

_es_client = None
_mq_client = None


def set_qa_clients(es_client, mq_client=None):
    """设置QA模块使用的客户端"""
    global _es_client, _mq_client
    _es_client = es_client
    _mq_client = mq_client
    set_service_clients(es_client, mq_client)


def get_es_client():
    """获取ES客户端"""
    if _es_client is None:
        raise HTTPException(status_code=500, detail="ES client not initialized. Call set_qa_clients first.")
    return _es_client


# =============================================================================
# QA提取API（MVP核心）
# =============================================================================

@qa_router.post("/extract/preview")
async def preview_extraction(request: ExtractionRequest):
    """
    预览可提取的QA数据量
    
    用于在执行提取前预估数据量
    """
    try:
        service = get_extraction_service()
        
        result = await service.preview(
            start_time=request.start_time,
            end_time=request.end_time,
            include_sub_nodes=request.include_sub_nodes,
            limit=request.limit,
        )
        
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"Preview extraction failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.post("/extract/execute")
async def execute_extraction(request: ExtractionRequest):
    """
    执行QA提取
    
    从ES的trace/node表提取QA数据，建立层级关系，保存到qa_task表
    
    核心流程：
    1. 查询指定时间范围内的trace记录（E2E对话）
    2. 为每个trace创建E2E任务（P0优先级，parent_task_id为空）
    3. 查询该trace下的node记录（Agent/Tool调用）
    4. 为每个node创建子任务（P1-P3优先级，parent_task_id指向E2E任务）
    """
    try:
        service = get_extraction_service()
        
        result = await service.extract_and_save(
            start_time=request.start_time,
            end_time=request.end_time,
            include_sub_nodes=request.include_sub_nodes,
            limit=request.limit,
        )
        
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"Execute extraction failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


# =============================================================================
# 任务管理API
# =============================================================================

@qa_router.get("/tasks")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    priority: Optional[int] = None,
    source_type: Optional[str] = None,
    assigned_to: Optional[str] = None,
    batch_id: Optional[str] = None,
    only_root: bool = Query(False, description="只查询E2E根任务"),
    search: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    """
    查询任务列表
    
    支持筛选、分页、搜索
    - only_root=true: 只返回E2E任务（用于树形展示的顶层）
    """
    try:
        service = get_task_service()
        
        result = await service.list_tasks(
            page=page,
            page_size=page_size,
            status=status,
            priority=priority,
            source_type=source_type,
            assigned_to=assigned_to,
            batch_id=batch_id,
            only_root=only_root,
            search_keyword=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"List tasks failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/tasks/tree")
async def list_tasks_tree(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    status: Optional[str] = None,
    priority: Optional[int] = None,
    batch_id: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    查询任务树形列表
    
    返回E2E根任务及其子任务的树形结构，用于前端层级展示
    
    返回格式：
    {
        "tasks": [
            {
                "task_id": "xxx",
                "question": "用户问题",
                "source_type": "e2e",
                "priority": 0,
                "children_count": 3,
                "children": [
                    {"task_id": "yyy", "source_type": "agent_agent", ...}
                ]
            }
        ]
    }
    """
    try:
        service = get_task_service()
        
        result = await service.list_root_tasks_with_tree(
            page=page,
            page_size=page_size,
            status=status,
            priority=priority,
            batch_id=batch_id,
            search_keyword=search,
        )
        
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"List tasks tree failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    try:
        service = get_task_service()
        
        task = await service.get_task(task_id)
        if not task:
            return WebResponse(code=404, message="Task not found").to_dict()
        
        return WebResponse(data=task).to_dict()
    except Exception as e:
        logger.error(f"Get task failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/tasks/{task_id}/tree")
async def get_task_tree(task_id: str):
    """
    获取任务的完整树形结构
    
    无论传入的是E2E任务还是子任务，都返回完整的树形结构
    """
    try:
        service = get_task_service()
        
        result = await service.get_task_tree(task_id)
        if not result.get("root"):
            return WebResponse(code=404, message="Task not found").to_dict()
        
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"Get task tree failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.post("/tasks/assign")
async def assign_task(request: TaskAssignRequest):
    """分配任务给标注者"""
    try:
        service = get_task_service()
        
        success = await service.assign_task(request.task_id, request.assigned_to)
        if success:
            return WebResponse(data={"success": True, "message": "Task assigned"}).to_dict()
        else:
            return WebResponse(code=400, message="Failed to assign task").to_dict()
    except Exception as e:
        logger.error(f"Assign task failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.post("/tasks/status")
async def update_task_status(request: TaskStatusUpdateRequest):
    """更新任务状态"""
    try:
        service = get_task_service()
        
        success = await service.update_task_status(
            task_id=request.task_id,
            status=request.status,
            stage=request.stage
        )
        if success:
            return WebResponse(data={"success": True}).to_dict()
        else:
            return WebResponse(code=400, message="Failed to update task status").to_dict()
    except Exception as e:
        logger.error(f"Update task status failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/tasks/pending/list")
async def get_pending_tasks(
    annotator_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """获取待标注任务列表"""
    try:
        service = get_task_service()
        
        result = await service.get_pending_tasks_for_annotator(
            annotator_id=annotator_id,
            page=page,
            page_size=page_size,
        )
        
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"Get pending tasks failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/stats")
async def get_stats():
    """获取任务统计信息"""
    try:
        service = get_task_service()
        
        result = await service.get_stats()
        return WebResponse(data=result).to_dict()
    except Exception as e:
        logger.error(f"Get stats failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.get("/batches")
async def get_batch_list():
    """获取批次列表"""
    try:
        service = get_task_service()
        
        result = await service.get_batch_list()
        return WebResponse(data={"batches": result}).to_dict()
    except Exception as e:
        logger.error(f"Get batch list failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


# =============================================================================
# 标注API
# =============================================================================

@qa_router.post("/annotations/submit")
async def submit_annotation(request: AnnotationSubmitRequest):
    """
    提交标注结果
    
    标注者完成标注后调用此接口，会：
    1. 创建annotation记录
    2. 更新task状态为annotated
    """
    try:
        service = get_annotation_service()
        
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
        service = get_annotation_service()
        
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
        service = get_annotation_service()
        
        annotation = await service.get_annotation_by_task(task_id)
        if not annotation:
            return WebResponse(code=404, message="Annotation not found").to_dict()
        
        return WebResponse(data=annotation).to_dict()
    except Exception as e:
        logger.error(f"Get annotation by task failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()


@qa_router.post("/annotations/review")
async def review_annotation(request: ReviewRequest):
    """
    审核标注
    
    审核者审核标注结果：
    - approved: 通过
    - rejected: 拒绝（任务回到待标注）
    - needs_revision: 需要修改
    """
    try:
        service = get_annotation_service()
        
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
# 系统配置API
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


@qa_router.get("/health")
async def health_check():
    """健康检查"""
    try:
        es_ok = _es_client is not None
        return WebResponse(data={
            "status": "ok" if es_ok else "degraded",
            "es_client": "connected" if es_ok else "not initialized",
        }).to_dict()
    except Exception as e:
        return WebResponse(code=500, message=str(e)).to_dict()


# =============================================================================
# ES索引管理API
# =============================================================================

@qa_router.post("/admin/init-indices")
async def init_indices():
    """
    初始化ES索引
    
    创建qa_task和qa_annotation索引（如果不存在）
    """
    try:
        from .schemas.task import QA_TASK_MAPPING
        from .schemas.annotation import QA_ANNOTATION_MAPPING
        
        es = get_es_client()
        app_name = Config.get_app_name()
        
        results = {}
        
        # 创建qa_task索引
        task_index = f"{app_name}_qa_task"
        try:
            exists = await es.index_exists(task_index)
            if not exists:
                await es.create_index(task_index, QA_TASK_MAPPING)
                results[task_index] = "created"
            else:
                results[task_index] = "already exists"
        except Exception as e:
            results[task_index] = f"error: {e}"
        
        # 创建qa_annotation索引
        annotation_index = f"{app_name}_qa_annotation"
        try:
            exists = await es.index_exists(annotation_index)
            if not exists:
                await es.create_index(annotation_index, QA_ANNOTATION_MAPPING)
                results[annotation_index] = "created"
            else:
                results[annotation_index] = "already exists"
        except Exception as e:
            results[annotation_index] = f"error: {e}"
        
        return WebResponse(data=results).to_dict()
    except Exception as e:
        logger.error(f"Init indices failed: {e}")
        return WebResponse(code=500, message=str(e)).to_dict()
