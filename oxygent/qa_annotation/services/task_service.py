# -*- encoding: utf-8 -*-
"""
QA标注平台 - 任务管理服务

提供任务查询、统计、分配等功能
"""

import logging
from typing import Dict, Any, Optional, List

from oxygent.config import Config
from oxygent.utils.common_utils import generate_uuid

logger = logging.getLogger(__name__)


class TaskService:
    """
    任务管理服务
    
    核心功能：
    1. 任务查询：支持分页、筛选、搜索
    2. 任务统计：统计各状态任务数量
    3. 任务分配：分配任务给标注者
    4. 数据概览：统计待导入vs已导入数据
    """
    
    def __init__(self, es_client):
        self.es_client = es_client
        self.app_name = Config.get_app_name()
        
        # 索引名称
        self.index_name = f"{self.app_name}_qa_task"
        self.trace_index = f"{self.app_name}_trace"
        self.node_index = f"{self.app_name}_node"
    
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
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        include_children: bool = True,  # 改造：默认包含所有任务（不只查根任务）
    ) -> Dict[str, Any]:
        """
        查询任务列表

        改造说明：
        默认返回所有任务（E2E + 子节点），
        通过priority字段区分任务类型：
        - priority=0: E2E端到端任务
        - priority=1: User→Agent
        - priority=2: Agent→Agent
        - priority=3: Agent→Tool/LLM

        Args:
            page: 页码（从1开始）
            page_size: 每页大小
            status: 状态筛选
            priority: 优先级筛选
            source_type: 数据源类型筛选
            assigned_to: 分配给谁
            parent_task_id: 父任务ID（用于查看子任务）
            only_root: 只查询根任务（E2E任务，parent_task_id为空）- 保留兼容
            search_keyword: 搜索关键词
            batch_id: 批次ID筛选
            start_time: 创建时间筛选-开始时间
            end_time: 创建时间筛选-结束时间
            sort_by: 排序字段
            sort_order: 排序顺序
            include_children: 是否包含子任务（改造：默认True，查询所有任务）

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
        
        # 改造：默认查询所有任务，不再默认只查根任务
        # only_root参数保留用于兼容旧逻辑
        if only_root:
            must_conditions.append({"term": {"is_root": True}})
        
        # 时间范围筛选
        if start_time or end_time:
            time_range = {}
            if start_time:
                time_range["gte"] = start_time
            if end_time:
                time_range["lte"] = end_time
            must_conditions.append({"range": {"created_at": time_range}})
        
        # 关键词搜索
        if search_keyword:
            must_conditions.append({
                "bool": {
                    "should": [
                        {"match": {"question": search_keyword}},
                        {"match": {"answer": search_keyword}},
                        {"match": {"callee": search_keyword}},
                        {"match": {"caller": search_keyword}},
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
                "tasks": tasks
            }
        except Exception as e:
            logger.error(f"List tasks error: {e}")
            return {"total": 0, "page": page, "page_size": page_size, "tasks": []}
    
    async def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务详情"""
        try:
            # 使用 _id 查询
            query = {
                "query": {"term": {"_id": task_id}},
                "size": 1
            }
            result = await self.es_client.search(self.index_name, query)
            hits = result.get("hits", {}).get("hits", [])
            if hits:
                return hits[0]["_source"]
            return None
        except Exception as e:
            logger.error(f"Get task error: {e}")
            return None
    
    async def get_task_tree(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务的完整树形结构
        
        如果传入的是子任务，返回该子任务所在E2E任务的完整树
        如果传入的是E2E任务，返回该任务及其所有子任务
        """
        try:
            # 先获取当前任务
            current_task = await self.get_task(task_id)
            if not current_task:
                return {"root": None, "children": []}
            
            # 如果是子任务，找到根任务
            root_task = current_task
            if current_task.get("parent_task_id"):
                root_task = await self.get_task(current_task["parent_task_id"])
                if not root_task:
                    return {"root": None, "children": []}
            
            # 获取根任务的所有子任务
            children_result = await self.list_tasks(
                parent_task_id=root_task["task_id"],
                page=1,
                page_size=100
            )
            children = children_result.get("tasks", [])
            
            return {
                "root": root_task,
                "children": children
            }
        except Exception as e:
            logger.error(f"Get task tree error: {e}")
            return {"root": None, "children": []}
    
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
        查询根任务列表（带子任务树）
        
        返回E2E任务及其子任务的树形结构
        """
        try:
            # 查询根任务
            result = await self.list_tasks(
                page=page,
                page_size=page_size,
                status=status,
                priority=priority,
                batch_id=batch_id,
                search_keyword=search_keyword,
                only_root=True
            )
            
            # 为每个根任务获取子任务
            tasks_with_tree = []
            for task in result.get("tasks", []):
                task_id = task.get("task_id")
                children_result = await self.list_tasks(
                    parent_task_id=task_id,
                    page=1,
                    page_size=100
                )
                task["_children"] = children_result.get("tasks", [])
                tasks_with_tree.append(task)
            
            return {
                "total": result["total"],
                "page": result["page"],
                "page_size": result["page_size"],
                "tasks": tasks_with_tree
            }
        except Exception as e:
            logger.error(f"List root tasks with tree error: {e}")
            return {"total": 0, "page": page, "page_size": page_size, "tasks": []}
    
    async def assign_task(self, task_id: str, assigned_to: str) -> bool:
        """分配任务"""
        try:
            task = await self.get_task(task_id)
            if not task:
                return False
            
            from oxygent.qa_annotation.schemas import QATaskStatus
            from oxygent.utils.common_utils import get_format_time
            
            update_data = {
                "assigned_to": assigned_to,
                "assigned_at": get_format_time(),
                "status": QATaskStatus.ASSIGNED.value,
                "updated_at": get_format_time()
            }
            
            await self.es_client.update(
                self.index_name,
                doc_id=task_id,
                body=update_data
            )
            return True
        except Exception as e:
            logger.error(f"Assign task error: {e}")
            return False
    
    async def get_overview(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取数据概览
        
        统计所有已导入任务的状态：
        - 待导入：尚未被导入的trace数量
        - 已导入：所有已导入的任务数（E2E + 子任务）
        - 标注进度：所有任务的标注状态统计
        
        注意：统计口径改为所有任务，便于标注员查看实际工作量
        如果不传时间参数，则查询所有数据
        """
        try:
            # 1. 获取所有已导入任务的统计
            imported_query = {
                "query": {"match_all": {}},
                "size": 10000,  # 获取所有已导入的任务
                "_source": ["source_trace_id", "priority", "status"]
            }
            
            # 时间范围筛选已导入的任务
            if start_time or end_time:
                time_range = {}
                if start_time:
                    time_range["gte"] = start_time
                if end_time:
                    time_range["lte"] = end_time
                imported_query["query"] = {
                    "bool": {
                        "must": [{"range": {"created_at": time_range}}]
                    }
                }
            
            imported_result = await self.es_client.search(self.index_name, imported_query)
            imported_hits = imported_result.get("hits", {}).get("hits", [])
            
            # 收集已导入的E2E trace_id（用于计算待导入）
            imported_e2e_trace_ids = set()
            # 统计所有任务的状态
            all_status_counts = {}
            # E2E任务计数
            imported_e2e_count = 0
            
            for hit in imported_hits:
                source = hit.get("_source", {})
                trace_id = source.get("source_trace_id")
                priority = source.get("priority", -1)
                status = source.get("status", "pending")
                
                # 收集E2E任务的trace_id（用于计算待导入）
                if priority == 0 and trace_id:
                    imported_e2e_trace_ids.add(trace_id)
                    imported_e2e_count += 1
                
                # 统计所有任务的状态
                all_status_counts[status] = all_status_counts.get(status, 0) + 1
            
            # 2. 查询时间范围内的trace（待导入）
            trace_query = {"query": {"match_all": {}}, "size": 0}
            
            if start_time or end_time:
                time_range = {}
                if start_time:
                    time_range["gte"] = start_time
                if end_time:
                    time_range["lte"] = end_time
                trace_query["query"] = {"range": {"create_time": time_range}}
            
            logger.info(f"Query trace with time range: start={start_time}, end={end_time}")
            
            trace_result = await self.es_client.search(self.trace_index, trace_query)
            total_traces_in_range = trace_result.get("hits", {}).get("total", {}).get("value", 0)
            
            # 3. 计算待导入数量 = 时间范围内的trace总数 - 已导入的trace数
            pending_import = total_traces_in_range - len(imported_e2e_trace_ids)
            if pending_import < 0:
                pending_import = 0
            
            logger.info(
                f"Overview stats: total_traces={total_traces_in_range}, "
                f"imported_e2e={len(imported_e2e_trace_ids)}, pending_import={pending_import}"
            )
            
            # 4. 汇总统计（基于所有任务）
            total_imported = len(imported_hits)  # 所有已导入任务数
            pending_count = all_status_counts.get("pending", 0)
            annotated_count = all_status_counts.get("annotated", 0)
            approved_count = all_status_counts.get("approved", 0)
            rejected_count = all_status_counts.get("rejected", 0)
            
            total_annotated = annotated_count + approved_count + rejected_count
            
            return {
                # 待导入数据（基于E2E维度计算）
                "trace_count": total_traces_in_range,  # 时间范围内总trace数
                "total_pending_import": pending_import,  # 待导入数量
                "total_traces_in_range": total_traces_in_range,
                "already_imported": len(imported_e2e_trace_ids),  # 已导入的E2E数
                
                # 已导入数据（基于所有任务）
                "imported_count": total_imported,  # 所有已导入任务数
                "imported_e2e_count": imported_e2e_count,  # E2E任务数
                
                # 按状态统计（基于所有任务）
                "pending_count": pending_count,
                "annotated_count": annotated_count,
                "approved_count": approved_count,
                "rejected_count": rejected_count,
                "status_counts": all_status_counts,
                
                # 进度计算（基于所有任务）
                "total_tasks": total_imported,
                "annotation_progress": round(total_annotated / total_imported * 100, 1) if total_imported > 0 else 0,
                "approval_progress": round(approved_count / total_imported * 100, 1) if total_imported > 0 else 0,
            }
        except Exception as e:
            logger.error(f"Get overview error: {e}")
            return {
                "trace_count": 0,
                "total_pending_import": 0,
                "total_traces_in_range": 0,
                "already_imported": 0,
                "imported_count": 0,
                "imported_e2e_count": 0,
                "pending_count": 0,
                "annotated_count": 0,
                "approved_count": 0,
                "rejected_count": 0,
                "status_counts": {},
                "total_tasks": 0,
                "annotation_progress": 0,
                "approval_progress": 0,
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


# 服务单例
_service_instance = None

def get_task_service() -> TaskService:
    """获取任务服务单例"""
    global _service_instance
    if _service_instance is None:
        from oxygent.databases.db_es import get_es_client
        _service_instance = TaskService(get_es_client())
    return _service_instance
