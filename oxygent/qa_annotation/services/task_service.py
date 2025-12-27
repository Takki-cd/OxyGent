# -*- encoding: utf-8 -*-
"""
QA标注平台 - 任务管理服务

提供任务的CRUD和查询功能，特别支持层级树形结构查询
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
    - **树形层级结构查询**（核心功能）
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
        only_root: bool = False,
        search_keyword: Optional[str] = None,
        batch_id: Optional[str] = None,
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
            parent_task_id: 父任务ID（用于查看子任务）
            only_root: 只查询根任务（E2E任务，parent_task_id为空）
            search_keyword: 搜索关键词
            batch_id: 批次ID筛选
            sort_by: 排序字段
            sort_order: 排序顺序
            
        Returns:
            {
                "total": int,
                "page": int,
                "page_size": int,
                "tasks": List[dict]
            }
        """
        must_conditions = []
        must_not_conditions = []
        
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
        
        if batch_id:
            must_conditions.append({"term": {"batch_id": batch_id}})
        
        # 只查询根任务（E2E）
        if only_root:
            must_conditions.append({"term": {"parent_task_id": ""}})
        
        # 关键词搜索
        if search_keyword:
            must_conditions.append({
                "bool": {
                    "should": [
                        {"match": {"question": search_keyword}},
                        {"match": {"answer": search_keyword}},
                    ],
                    "minimum_should_match": 1
                }
            })
        
        query = {
            "query": {
                "bool": {
                    "must": must_conditions if must_conditions else [{"match_all": {}}],
                    "must_not": must_not_conditions if must_not_conditions else []
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
    
    async def list_root_tasks_with_tree(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        batch_id: Optional[str] = None,
        search_keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        查询根任务列表，并附带子任务树
        
        这是前端展示层级结构的核心接口
        
        返回格式：
        {
            "total": 10,
            "tasks": [
                {
                    "task_id": "xxx",
                    "question": "用户问题",
                    "answer": "最终回答",
                    "source_type": "e2e",
                    "priority": 0,
                    "status": "pending",
                    "children_count": 3,
                    "children": [
                        {
                            "task_id": "yyy",
                            "source_type": "agent_agent",
                            "priority": 2,
                            ...
                        }
                    ]
                }
            ]
        }
        """
        # 1. 查询根任务
        root_result = await self.list_tasks(
            page=page,
            page_size=page_size,
            status=status,
            priority=priority,
            batch_id=batch_id,
            search_keyword=search_keyword,
            only_root=True,
            sort_by="created_at",
            sort_order="desc"
        )
        
        root_tasks = root_result.get("tasks", [])
        
        # 2. 为每个根任务查询子任务
        for task in root_tasks:
            task_id = task.get("task_id")
            children = await self._get_children_tasks(task_id)
            task["children"] = children
            task["children_count"] = len(children)
        
        return {
            "total": root_result.get("total", 0),
            "page": page,
            "page_size": page_size,
            "tasks": root_tasks,
        }
    
    async def _get_children_tasks(self, parent_task_id: str) -> List[dict]:
        """获取指定任务的所有子任务"""
        result = await self.list_tasks(
            page=1,
            page_size=100,
            parent_task_id=parent_task_id,
            sort_by="priority",
            sort_order="asc"
        )
        return result.get("tasks", [])
    
    async def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务详情"""
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
    
    async def get_task_tree(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务的完整树形结构
        
        如果task_id是根任务，返回它和所有子任务
        如果task_id是子任务，先找到根任务，再返回完整树
        
        Args:
            task_id: 任务ID
            
        Returns:
            {
                "root": {...},  # 根任务
                "children": [...],  # 子任务列表
                "current_task_id": "xxx"  # 当前查询的任务ID
            }
        """
        task = await self.get_task(task_id)
        if not task:
            return {"root": None, "children": [], "current_task_id": task_id}
        
        # 判断是否是根任务
        parent_task_id = task.get("parent_task_id", "")
        
        if parent_task_id:
            # 是子任务，找到根任务
            root_task = await self.get_task(parent_task_id)
            if root_task:
                children = await self._get_children_tasks(parent_task_id)
                return {
                    "root": root_task,
                    "children": children,
                    "current_task_id": task_id
                }
            else:
                # 找不到根任务，返回当前任务
                return {
                    "root": task,
                    "children": [],
                    "current_task_id": task_id
                }
        else:
            # 是根任务
            children = await self._get_children_tasks(task_id)
            return {
                "root": task,
                "children": children,
                "current_task_id": task_id
            }
    
    async def get_task_with_children(self, task_id: str) -> Dict[str, Any]:
        """获取任务及其子任务（兼容旧接口）"""
        tree = await self.get_task_tree(task_id)
        return {
            "task": tree.get("root"),
            "children": tree.get("children", []),
        }
    
    async def update_task_status(
        self,
        task_id: str,
        status: str,
        assigned_to: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> bool:
        """更新任务状态"""
        update_data = {
            "status": status,
            "updated_at": get_format_time(),
        }
        
        if assigned_to is not None:
            update_data["assigned_to"] = assigned_to
            if status == QATaskStatus.ASSIGNED.value:
                update_data["assigned_at"] = get_format_time()
        
        if stage is not None:
            update_data["stage"] = stage
        
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
    
    async def assign_task(self, task_id: str, assigned_to: str) -> bool:
        """分配任务给标注者"""
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
        """获取标注者的待标注任务"""
        if annotator_id:
            return await self.list_tasks(
                page=page,
                page_size=page_size,
                status=QATaskStatus.ASSIGNED.value,
                assigned_to=annotator_id,
                sort_by="priority",
                sort_order="asc"
            )
        else:
            return await self.list_tasks(
                page=page,
                page_size=page_size,
                status=QATaskStatus.PENDING.value,
                sort_by="priority",
                sort_order="asc"
            )
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取任务统计信息"""
        try:
            query = {
                "size": 0,
                "aggs": {
                    "by_status": {"terms": {"field": "status"}},
                    "by_priority": {"terms": {"field": "priority"}},
                    "by_source_type": {"terms": {"field": "source_type"}},
                    "root_count": {
                        "filter": {"term": {"parent_task_id": ""}}
                    }
                }
            }
            
            result = await self.es_client.search(self.index_name, query)
            
            total = result.get("hits", {}).get("total", {}).get("value", 0)
            aggs = result.get("aggregations", {})
            
            return {
                "total": total,
                "root_count": aggs.get("root_count", {}).get("doc_count", 0),
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
                "root_count": 0,
                "by_status": {},
                "by_priority": {},
                "by_source_type": {},
                "error": str(e),
            }
    
    async def get_batch_list(self) -> List[Dict[str, Any]]:
        """获取所有批次列表"""
        try:
            query = {
                "size": 0,
                "aggs": {
                    "batches": {
                        "terms": {
                            "field": "batch_id",
                            "size": 100
                        },
                        "aggs": {
                            "latest": {
                                "top_hits": {
                                    "size": 1,
                                    "sort": [{"created_at": {"order": "desc"}}],
                                    "_source": ["batch_id", "created_at"]
                                }
                            }
                        }
                    }
                }
            }
            
            result = await self.es_client.search(self.index_name, query)
            buckets = result.get("aggregations", {}).get("batches", {}).get("buckets", [])
            
            batches = []
            for bucket in buckets:
                batch_id = bucket["key"]
                if not batch_id:
                    continue
                hits = bucket.get("latest", {}).get("hits", {}).get("hits", [])
                created_at = hits[0]["_source"]["created_at"] if hits else ""
                batches.append({
                    "batch_id": batch_id,
                    "count": bucket["doc_count"],
                    "created_at": created_at
                })
            
            return sorted(batches, key=lambda x: x.get("created_at", ""), reverse=True)
        except Exception as e:
            logger.error(f"Failed to get batch list: {e}")
            return []
