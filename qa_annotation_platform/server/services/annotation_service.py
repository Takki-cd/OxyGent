"""
标注服务层 - 业务逻辑

参照之前版本架构，实现核心功能
"""
import logging
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..models import (
    QATask, 
    QATaskStatus, 
    DepositRequest, 
    BatchDepositRequest,
    AnnotationUpdate,
    TaskFilter,
    StatsResponse
)
from .es_service import get_es_service, ESService


logger = logging.getLogger(__name__)


class QAContext:
    """
    QA上下文管理器 - 解决子流程串联问题
    
    核心机制：
    1. 根节点注册：create_root() 创建新的端到端QA，返回root_qa_id
    2. 子节点注册：create_child() 自动继承parent_qa_id，串联到根节点
    3. 串联查询：get_chain() 获取完整的调用链
    
    使用示例：
    ```python
    # 1. 在Agent入口注册根节点
    root_qa_id = QAContext.create_root(
        trace_id=trace_id,
        group_id=group_id,
        question=user_input,
        answer=agent_output
    )
    
    # 2. 在子流程中注册子节点（自动继承parent_qa_id）
    QAContext.create_child(
        parent_qa_id=root_qa_id,
        trace_id=trace_id,
        question=retrieval_query,
        answer=retrieved_docs
    )
    ```
    """
    
    _contexts: Dict[str, Dict[str, Any]] = {}
    _trace_root_map: Dict[str, str] = {}
    
    @classmethod
    def create_root(
        cls,
        trace_id: str,
        group_id: Optional[str],
        question: str,
        answer: str = "",
        caller: str = "user",
        callee: str = "",
        extra: Optional[Dict] = None
    ) -> str:
        """创建根节点（端到端QA）"""
        root_qa_id = str(uuid.uuid4())
        
        cls._contexts[root_qa_id] = {
            "qa_id": root_qa_id,
            "trace_id": trace_id,
            "group_id": group_id,
            "is_root": True,
            "parent_qa_id": "",
            "depth": 0,
            "question": question,
            "answer": answer,
            "caller": caller,
            "callee": callee,
            "extra": extra or {},
            "children": [],
            "created_at": datetime.now()
        }
        
        cls._trace_root_map[trace_id] = root_qa_id
        
        logger.info(f"QAContext: 创建根节点 root_qa_id={root_qa_id}, trace_id={trace_id}")
        return root_qa_id
    
    @classmethod
    def create_child(
        cls,
        parent_qa_id: str,
        trace_id: str,
        question: str,
        answer: str = "",
        node_type: str = "llm",
        node_id: Optional[str] = None,
        caller: str = "",
        callee: str = "",
        extra: Optional[Dict] = None
    ) -> Optional[str]:
        """创建子节点（自动串联到根节点）"""
        parent_ctx = cls._contexts.get(parent_qa_id)
        if not parent_ctx:
            logger.warning(f"QAContext: parent_qa_id不存在 parent_qa_id={parent_qa_id}")
            return None
        
        child_qa_id = str(uuid.uuid4())
        
        child_ctx = {
            "qa_id": child_qa_id,
            "trace_id": trace_id,
            "group_id": parent_ctx.get("group_id"),
            "is_root": False,
            "parent_qa_id": parent_qa_id,
            "depth": parent_ctx.get("depth", 0) + 1,
            "question": question,
            "answer": answer,
            "node_type": node_type,
            "node_id": node_id,
            "caller": caller,
            "callee": callee,
            "extra": extra or {},
            "children": [],
            "created_at": datetime.now()
        }
        
        cls._contexts[child_qa_id] = child_ctx
        parent_ctx["children"].append(child_qa_id)
        
        logger.info(f"QAContext: 创建子节点 child_qa_id={child_qa_id}, parent_qa_id={parent_qa_id}")
        return child_qa_id
    
    @classmethod
    def get_root_by_trace(cls, trace_id: str) -> Optional[str]:
        """根据trace_id获取根节点QA ID"""
        return cls._trace_root_map.get(trace_id)
    
    @classmethod
    def get_chain(cls, qa_id: str) -> List[Dict[str, Any]]:
        """获取完整调用链"""
        result = []
        
        def collect(id: str):
            ctx = cls._contexts.get(id)
            if ctx:
                result.append({
                    "qa_id": ctx["qa_id"],
                    "trace_id": ctx["trace_id"],
                    "is_root": ctx["is_root"],
                    "parent_qa_id": ctx["parent_qa_id"],
                    "depth": ctx["depth"],
                    "question": ctx["question"][:100] if ctx["question"] else "",
                    "node_type": ctx.get("node_type", ""),
                    "children_count": len(ctx["children"])
                })
                for child_id in ctx["children"]:
                    collect(child_id)
        
        collect(qa_id)
        return result
    
    @classmethod
    def clear_expired(cls, max_age_minutes: int = 60):
        """清理过期上下文"""
        now = datetime.now()
        expired = []
        
        for qa_id, ctx in cls._contexts.items():
            age = (now - ctx["created_at"]).total_seconds() / 60
            if age > max_age_minutes:
                expired.append(qa_id)
        
        for qa_id in expired:
            ctx = cls._contexts.pop(qa_id)
            if ctx["trace_id"] in cls._trace_root_map:
                del cls._trace_root_map[ctx["trace_id"]]
        
        if expired:
            logger.info(f"QAContext: 清理过期上下文 {len(expired)} 个")


class AnnotationService:
    """标注服务类"""
    
    def __init__(self, es_service: ESService, config: Dict[str, Any] = None):
        self.es_service = es_service
        self.config = config or {}
        self.batch_id = ""
    
    def _new_batch_id(self) -> str:
        """生成批次ID"""
        import hashlib
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return hashlib.md5(timestamp.encode()).hexdigest()[:16]
    
    async def deposit(self, request: DepositRequest) -> Dict[str, Any]:
        """注入单条QA数据"""
        is_dup = await self.es_service.is_duplicate(request.qa_hash)
        if is_dup:
            existing = await self._get_existing_by_hash(request.qa_hash)
            if existing:
                logger.info(f"QA重复，跳过: hash={request.qa_hash[:16]}...")
                return {
                    "success": True,
                    "qa_id": existing["qa_id"],
                    "task_id": existing["task_id"],
                    "message": "QA已存在"
                }
        
        if not self.batch_id:
            self.batch_id = self._new_batch_id()
        
        task = QATask.from_deposit_request(request, self.batch_id)
        
        if request.parent_qa_id:
            parent_task = await self.es_service.get_task_by_id(request.parent_qa_id)
            if parent_task:
                task.parent_qa_id = request.parent_qa_id
                task.depth = parent_task.get("depth", 0) + 1
        
        await self.es_service.index_task(task)
        
        logger.info(f"QA注入成功: qa_id={task.qa_id}, trace_id={task.source_trace_id}")
        
        return {
            "success": True,
            "qa_id": task.qa_id,
            "task_id": task.task_id,
            "message": "注入成功"
        }
    
    async def _get_existing_by_hash(self, qa_hash: str) -> Optional[Dict]:
        """根据hash获取已存在的任务"""
        try:
            # 统一使用 es_service 的 search 方法
            search_body = {
                "query": {"term": {"qa_hash": qa_hash}},
                "size": 1
            }
            result = await self.es_service.es_client.search(
                self.es_service.index_name,
                search_body
            )
            hits = result.get("hits", {}).get("hits", [])
            if hits:
                return hits[0]["_source"]
            return None
        except Exception:
            return None
    
    async def batch_deposit(self, request: BatchDepositRequest) -> Dict[str, Any]:
        """批量注入QA数据"""
        if not self.batch_id:
            self.batch_id = self._new_batch_id()
        
        tasks = []
        skipped = []
        
        for item in request.items:
            is_dup = await self.es_service.is_duplicate(item.qa_hash)
            if is_dup:
                skipped.append(item)
                continue
            
            task = QATask.from_deposit_request(item, self.batch_id)
            
            if item.parent_qa_id:
                parent_task = await self.es_service.get_task_by_id(item.parent_qa_id)
                if parent_task:
                    task.parent_qa_id = item.parent_qa_id
                    task.depth = parent_task.get("depth", 0) + 1
            
            tasks.append(task)
        
        if tasks:
            success_count, failed = await self.es_service.bulk_index_tasks(tasks)
        else:
            success_count, failed = 0, []
        
        return {
            "success": True,
            "total": len(request.items),
            "success_count": success_count,
            "failed_count": len(failed) + len(skipped),
            "qa_ids": [t.qa_id for t in tasks],
            "message": f"批量注入: 成功{success_count}条, 跳过{len(skipped)}条, 失败{len(failed)}条"
        }
    
    async def get_tasks(
        self,
        filter_params: TaskFilter,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """获取任务列表"""
        return await self.es_service.search_tasks(filter_params, page, page_size)
    
    async def get_task_by_id(self, qa_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取任务详情"""
        return await self.es_service.get_task_by_id(qa_id)
    
    async def update_annotation(
        self, 
        qa_id: str, 
        update: AnnotationUpdate
    ) -> Dict[str, Any]:
        """更新标注"""
        update_data = {}
        
        if update.status:
            update_data["status"] = update.status
        
        if update.annotation:
            update_data["annotation"] = update.annotation
        
        if update.scores:
            update_data["scores"] = update.scores
        
        if not update_data:
            return {"success": False, "message": "没有需要更新的内容"}
        
        success = await self.es_service.update_task(qa_id, update_data)
        
        if success:
            return {"success": True, "message": "更新成功"}
        else:
            return {"success": False, "message": "更新失败"}
    
    async def get_stats(self) -> StatsResponse:
        """获取统计信息"""
        stats = await self.es_service.get_stats()
        return StatsResponse(**stats)
    
    async def get_children(self, qa_id: str) -> List[Dict[str, Any]]:
        """获取指定任务的子节点"""
        return await self.es_service.get_children_by_parent_id(qa_id)
    
    async def approve(self, qa_id: str) -> Dict[str, Any]:
        """审核通过"""
        success = await self.es_service.update_task(
            qa_id, 
            {"status": QATaskStatus.APPROVED.value}
        )
        return {"success": success, "message": "已通过" if success else "失败"}
    
    async def reject(self, qa_id: str) -> Dict[str, Any]:
        """审核拒绝"""
        success = await self.es_service.update_task(
            qa_id, 
            {"status": QATaskStatus.REJECTED.value}
        )
        return {"success": success, "message": "已拒绝" if success else "失败"}


# 全局服务实例
_annotation_service: Optional[AnnotationService] = None


def get_annotation_service() -> AnnotationService:
    """获取标注服务（单例）"""
    global _annotation_service
    if _annotation_service is None:
        es_service = get_es_service()
        _annotation_service = AnnotationService(es_service)
    return _annotation_service


def reset_annotation_service():
    """重置标注服务（用于测试）"""
    global _annotation_service
    _annotation_service = None
    QAContext.clear_expired(0)
