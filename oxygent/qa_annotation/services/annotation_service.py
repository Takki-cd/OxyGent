# -*- encoding: utf-8 -*-
"""
QA标注平台 - 标注服务

处理标注提交和审核逻辑
"""

import logging
from typing import Optional, Dict, Any

from oxygent.config import Config
from oxygent.utils.common_utils import generate_uuid, get_format_time
from oxygent.qa_annotation.schemas import (
    QATaskStatus,
    QATaskStage,
    ReviewStatus,
)

logger = logging.getLogger(__name__)


class AnnotationService:
    """
    标注服务
    
    提供:
    - 提交标注结果
    - 获取标注详情
    - 审核标注
    - 修改标注
    """
    
    def __init__(self, es_client, mq_client=None):
        """
        初始化标注服务
        
        Args:
            es_client: ES客户端
            mq_client: MQ客户端（用于发送审核消息）
        """
        self.es_client = es_client
        self.mq = mq_client
        self.app_name = Config.get_app_name()
        self.task_index = f"{self.app_name}_qa_task"
        self.annotation_index = f"{self.app_name}_qa_annotation"
    
    async def submit_annotation(
        self,
        task_id: str,
        annotator_id: str,
        annotated_question: str,
        annotated_answer: str,
        quality_label: str = "acceptable",
        is_useful: bool = True,
        correction_type: str = "none",
        domain: str = "",
        intent: str = "",
        complexity: str = "",
        should_add_to_kb: bool = False,
        kb_category: str = "",
        annotation_notes: str = "",
        time_cost: int = 0,
    ) -> Dict[str, Any]:
        """
        提交标注结果
        
        Args:
            task_id: 任务ID
            annotator_id: 标注者ID
            annotated_question: 标注后的问题
            annotated_answer: 标注后的答案
            quality_label: 质量标签 (excellent/good/acceptable/poor/invalid)
            is_useful: 是否有用
            correction_type: 修正类型 (none/minor/major/rewrite)
            domain: 领域
            intent: 意图
            complexity: 复杂度
            should_add_to_kb: 是否加入知识库
            kb_category: 知识库分类
            annotation_notes: 标注备注
            time_cost: 标注耗时（秒）
            
        Returns:
            {"success": bool, "annotation_id": str, "message": str}
        """
        # 1. 检查任务是否存在
        task = await self._get_task(task_id)
        if not task:
            return {"success": False, "message": "Task not found"}
        
        # 2. 检查任务状态
        current_status = task.get("status")
        if current_status in [QATaskStatus.APPROVED.value, QATaskStatus.CANCELLED.value]:
            return {"success": False, "message": f"Task status is {current_status}, cannot annotate"}
        
        # 3. 创建标注记录
        annotation_id = generate_uuid()
        annotation_data = {
            "annotation_id": annotation_id,
            "task_id": task_id,
            "annotated_question": annotated_question,
            "annotated_answer": annotated_answer,
            "quality_label": quality_label,
            "is_useful": is_useful,
            "correction_type": correction_type,
            "domain": domain,
            "intent": intent,
            "complexity": complexity,
            "should_add_to_kb": should_add_to_kb,
            "kb_category": kb_category,
            "annotator_id": annotator_id,
            "annotation_time_cost": time_cost,
            "annotation_notes": annotation_notes,
            "review_status": ReviewStatus.PENDING.value,
            "reviewer_id": "",
            "review_comment": "",
            "reviewed_at": "",
            "created_at": get_format_time(),
            "updated_at": get_format_time(),
        }
        
        try:
            # 保存标注记录
            await self.es_client.index(
                self.annotation_index,
                doc_id=annotation_id,
                body=annotation_data
            )
            
            # 更新任务状态
            await self.es_client.update(
                self.task_index,
                doc_id=task_id,
                body={
                    "status": QATaskStatus.ANNOTATED.value,
                    "stage": QATaskStage.ANNOTATED.value,
                    "updated_at": get_format_time(),
                }
            )
            
            # TODO: 发送到审核队列
            # if self.mq:
            #     await self.mq.publish("review", {...})
            
            logger.info(f"Annotation submitted: {annotation_id} for task {task_id}")
            return {
                "success": True,
                "annotation_id": annotation_id,
                "message": "Annotation submitted successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to submit annotation: {e}")
            return {"success": False, "message": str(e)}
    
    async def get_annotation(self, annotation_id: str) -> Optional[dict]:
        """
        获取标注详情
        
        Args:
            annotation_id: 标注ID
            
        Returns:
            标注数据或None
        """
        try:
            result = await self.es_client.search(
                self.annotation_index,
                {"query": {"term": {"annotation_id": annotation_id}}, "size": 1}
            )
            hits = result.get("hits", {}).get("hits", [])
            if hits:
                return hits[0]["_source"]
            return None
        except Exception as e:
            logger.error(f"Failed to get annotation {annotation_id}: {e}")
            return None
    
    async def get_annotation_by_task(self, task_id: str) -> Optional[dict]:
        """
        根据任务ID获取标注
        
        Args:
            task_id: 任务ID
            
        Returns:
            最新的标注数据或None
        """
        try:
            result = await self.es_client.search(
                self.annotation_index,
                {
                    "query": {"term": {"task_id": task_id}},
                    "size": 1,
                    "sort": [{"created_at": {"order": "desc"}}]
                }
            )
            hits = result.get("hits", {}).get("hits", [])
            if hits:
                return hits[0]["_source"]
            return None
        except Exception as e:
            logger.error(f"Failed to get annotation for task {task_id}: {e}")
            return None
    
    async def review_annotation(
        self,
        annotation_id: str,
        reviewer_id: str,
        review_status: str,
        review_comment: str = "",
    ) -> Dict[str, Any]:
        """
        审核标注
        
        Args:
            annotation_id: 标注ID
            reviewer_id: 审核者ID
            review_status: 审核状态 (approved/rejected/needs_revision)
            review_comment: 审核评语
            
        Returns:
            {"success": bool, "message": str}
        """
        # 1. 获取标注
        annotation = await self.get_annotation(annotation_id)
        if not annotation:
            return {"success": False, "message": "Annotation not found"}
        
        task_id = annotation.get("task_id")
        
        try:
            # 2. 更新标注审核状态
            await self.es_client.update(
                self.annotation_index,
                doc_id=annotation_id,
                body={
                    "review_status": review_status,
                    "reviewer_id": reviewer_id,
                    "review_comment": review_comment,
                    "reviewed_at": get_format_time(),
                    "updated_at": get_format_time(),
                }
            )
            
            # 3. 更新任务状态
            if review_status == ReviewStatus.APPROVED.value:
                task_status = QATaskStatus.APPROVED.value
                task_stage = QATaskStage.REVIEWED.value
            elif review_status == ReviewStatus.REJECTED.value:
                task_status = QATaskStatus.REJECTED.value
                task_stage = QATaskStage.PENDING.value
            else:  # needs_revision
                task_status = QATaskStatus.ASSIGNED.value
                task_stage = QATaskStage.PENDING.value
            
            await self.es_client.update(
                self.task_index,
                doc_id=task_id,
                body={
                    "status": task_status,
                    "stage": task_stage,
                    "updated_at": get_format_time(),
                }
            )
            
            # 知识库发布（可配置跳过）
            if review_status == ReviewStatus.APPROVED.value and annotation.get("should_add_to_kb"):
                await self._publish_to_knowledge_base(annotation, task_id)
            
            logger.info(f"Annotation {annotation_id} reviewed: {review_status}")
            return {
                "success": True,
                "message": f"Review {review_status} completed"
            }
            
        except Exception as e:
            logger.error(f"Failed to review annotation: {e}")
            return {"success": False, "message": str(e)}
    
    async def update_annotation(
        self,
        annotation_id: str,
        annotator_id: str,
        **update_fields
    ) -> Dict[str, Any]:
        """
        更新标注（用于修改后重新提交）
        
        Args:
            annotation_id: 标注ID
            annotator_id: 操作者ID
            **update_fields: 要更新的字段
            
        Returns:
            {"success": bool, "message": str}
        """
        # 检查权限
        annotation = await self.get_annotation(annotation_id)
        if not annotation:
            return {"success": False, "message": "Annotation not found"}
        
        if annotation.get("annotator_id") != annotator_id:
            return {"success": False, "message": "Permission denied"}
        
        # 准备更新数据
        update_data = {k: v for k, v in update_fields.items() if v is not None}
        update_data["updated_at"] = get_format_time()
        update_data["review_status"] = ReviewStatus.PENDING.value  # 重置审核状态
        
        try:
            await self.es_client.update(
                self.annotation_index,
                doc_id=annotation_id,
                body=update_data
            )
            
            logger.info(f"Annotation {annotation_id} updated")
            return {"success": True, "message": "Annotation updated"}
            
        except Exception as e:
            logger.error(f"Failed to update annotation: {e}")
            return {"success": False, "message": str(e)}
    
    async def _get_task(self, task_id: str) -> Optional[dict]:
        """获取任务"""
        try:
            result = await self.es_client.search(
                self.task_index,
                {"query": {"term": {"task_id": task_id}}, "size": 1}
            )
            hits = result.get("hits", {}).get("hits", [])
            if hits:
                return hits[0]["_source"]
            return None
        except Exception:
            return None
    
    async def _publish_to_knowledge_base(self, annotation: dict, task_id: str):
        """
        发布到知识库（可配置跳过）
        
        通过配置 qa_annotation.platform.enable_kb_export 控制是否启用
        """
        platform_config = Config.get_qa_platform_config()
        if not platform_config.get("enable_kb_export", False):
            logger.debug(f"KB export disabled, skipping for annotation of task {task_id}")
            return
        
        # 获取任务详情
        task = await self._get_task(task_id)
        if not task:
            return
        
        kb_data = {
            "task_id": task_id,
            "annotation_id": annotation.get("annotation_id"),
            "question": annotation.get("annotated_question"),
            "answer": annotation.get("annotated_answer"),
            "domain": annotation.get("domain", ""),
            "intent": annotation.get("intent", ""),
            "kb_category": annotation.get("kb_category", ""),
            "source_trace_id": task.get("source_trace_id", ""),
            "published_at": get_format_time(),
        }
        
        # MVP版本：记录日志，后续扩展可发布到MQ或直接写入知识库
        logger.info(f"KB publish: {kb_data}")
        
        # 更新任务阶段为已发布
        try:
            await self.es_client.update(
                self.task_index,
                doc_id=task_id,
                body={
                    "stage": QATaskStage.PUBLISHED.value,
                    "updated_at": get_format_time(),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to update task stage to published: {e}")

