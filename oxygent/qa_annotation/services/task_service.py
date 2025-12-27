# -*- encoding: utf-8 -*-
"""
QA标注平台 - 任务管理服务

提供任务的CRUD和查询功能
"""

import logging
from typing import Optional, List, Dict, Any

from oxygent.config import Config
from oxygent.utils.common_utils import get_format_time
from oxygent.qa_annotation.schemas import QATaskStatus, QATaskStage

logger = logging.getLogger(__name__)


class TaskService:
    """
    任务管理服务
    
    提供:
    - 任务列表查询（支持分页、筛选、排序）
    - 任务详情获取
    - 任务状态更新
    - 任务分配
    - 任务统计
    """
    
    def __init__(self, es_client):
        """
        初始化任务服务
        
        Args:
            es_client: ES客户端实例
        """
        self.es_client = es_client
        self.app_name = Config.get_app_name()
        self.index_name = f"{self.app_name}_qa_task"
        self.platform_config = Config.get_qa_platform_config()
    
    async def list_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        source_type: Optional[str] = None,
        assigned_to: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        search_keyword: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """
        查询任务列表
        
        Args:
            page: 页码（从1开始）
            page_size: 每页大小
            status: 状态筛选
            priority: 优先级筛选
            source_type: 数据源类型筛选
            assigned_to: 分配给谁
            parent_task_id: 父任务ID（用于查看归属关系）
            search_keyword: 搜索关键词（搜索question和answer）
            sort_by: 排序字段
            sort_order: 排序顺序（asc/desc）
            
        Returns:
            {
                "total": int,
                "page": int,
                "page_size": int,
                "tasks": List[dict]
            }
        """
        # 构建查询
        must_conditions = []
        
        if status:
            must_conditions.append({"term": {"status": status}})
        
        if priority is not None:
            must_conditions.append({"term": {"priority": priority}})
        
        if source_type:
            must_conditions.append({"term": {"source_type": source_type}})
        
        if assigned_to:
            must_conditions.append({"term": {"assigned_to": assigned_to}})
        
        if parent_task_id:
            must_conditions.append({"term": {"parent_task_id": parent_task_id}})
        
        # 关键词搜索
        if search_keyword:
            must_conditions.append({
                "bool": {
                    "should": [
                        {"match": {"question": search_keyword}},
                        {"match": {"answer": search_keyword}},
                    ]
                }
            })
        
        query = {
            "query": {
                "bool": {
                    "must": must_conditions if must_conditions else [{"match_all": {}}]
                }
            },
            "from": (page - 1) * page_size,
            "size": page_size,
            "sort": [{sort_by: {"order": sort_order}}],
        }
        
        try:
            result = await self.es_client.search(self.index_name, query)
            hits = result.get("hits", {})
            total = hits.get("total", {}).get("value", 0)
            tasks = [hit["_source"] for hit in hits.get("hits", [])]
            
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "tasks": tasks,
            }
        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return {
                "total": 0,
                "page": page,
                "page_size": page_size,
                "tasks": [],
                "error": str(e),
            }
    
    async def get_task(self, task_id: str) -> Optional[dict]:
        """
        获取任务详情
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务数据或None
        """
        try:
            result = await self.es_client.search(
                self.index_name,
                {"query": {"term": {"task_id": task_id}}, "size": 1}
            )
            hits = result.get("hits", {}).get("hits", [])
            if hits:
                return hits[0]["_source"]
            return None
        except Exception as e:
            logger.error(f"Failed to get task {task_id}: {e}")
            return None
    
    async def get_task_with_children(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务及其子任务（归属关系展示）
        
        Args:
            task_id: 父任务ID
            
        Returns:
            {
                "task": dict,
                "children": List[dict]
            }
        """
        task = await self.get_task(task_id)
        if not task:
            return {"task": None, "children": []}
        
        # 查询子任务（通过parent_task_id关联）
        children_result = await self.list_tasks(
            parent_task_id=task_id,
            page_size=100,
            sort_by="priority",
            sort_order="asc"
        )
        
        return {
            "task": task,
            "children": children_result.get("tasks", []),
        }
    
    async def update_task_status(
        self,
        task_id: str,
        status: str,
        assigned_to: Optional[str] = None,
    ) -> bool:
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            assigned_to: 分配给谁（可选）
            
        Returns:
            是否更新成功
        """
        update_data = {
            "status": status,
            "updated_at": get_format_time(),
        }
        
        if assigned_to is not None:
            update_data["assigned_to"] = assigned_to
            if status == QATaskStatus.ASSIGNED.value:
                update_data["assigned_at"] = get_format_time()
        
        try:
            await self.es_client.update(
                self.index_name,
                doc_id=task_id,
                body=update_data
            )
            logger.info(f"Updated task {task_id} status to {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to update task {task_id}: {e}")
            return False
    
    async def assign_task(
        self,
        task_id: str,
        assigned_to: str,
    ) -> bool:
        """
        分配任务给标注者
        
        Args:
            task_id: 任务ID
            assigned_to: 标注者ID
            
        Returns:
            是否分配成功
        """
        return await self.update_task_status(
            task_id=task_id,
            status=QATaskStatus.ASSIGNED.value,
            assigned_to=assigned_to
        )
    
    async def get_pending_tasks_for_annotator(
        self,
        annotator_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        """
        获取标注者的待标注任务
        
        Args:
            annotator_id: 标注者ID（None表示获取未分配的任务）
            page: 页码
            page_size: 每页大小
            
        Returns:
            任务列表
        """
        if annotator_id:
            # 获取分配给该标注者的任务
            return await self.list_tasks(
                page=page,
                page_size=page_size,
                status=QATaskStatus.ASSIGNED.value,
                assigned_to=annotator_id,
                sort_by="priority",
                sort_order="asc"
            )
        else:
            # 获取未分配的任务
            return await self.list_tasks(
                page=page,
                page_size=page_size,
                status=QATaskStatus.PENDING.value,
                sort_by="priority",
                sort_order="asc"
            )
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        获取任务统计信息
        
        Returns:
            {
                "total": int,
                "by_status": {status: count},
                "by_priority": {priority: count},
                "by_source_type": {source_type: count}
            }
        """
        try:
            # 使用聚合查询
            query = {
                "size": 0,
                "aggs": {
                    "by_status": {
                        "terms": {"field": "status"}
                    },
                    "by_priority": {
                        "terms": {"field": "priority"}
                    },
                    "by_source_type": {
                        "terms": {"field": "source_type"}
                    }
                }
            }
            
            result = await self.es_client.search(self.index_name, query)
            
            total = result.get("hits", {}).get("total", {}).get("value", 0)
            aggs = result.get("aggregations", {})
            
            return {
                "total": total,
                "by_status": {
                    bucket["key"]: bucket["doc_count"]
                    for bucket in aggs.get("by_status", {}).get("buckets", [])
                },
                "by_priority": {
                    bucket["key"]: bucket["doc_count"]
                    for bucket in aggs.get("by_priority", {}).get("buckets", [])
                },
                "by_source_type": {
                    bucket["key"]: bucket["doc_count"]
                    for bucket in aggs.get("by_source_type", {}).get("buckets", [])
                },
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {
                "total": 0,
                "by_status": {},
                "by_priority": {},
                "by_source_type": {},
                "error": str(e),
            }

