"""
ES服务层 - 复用Oxygent的ES客户端

配置独立，ES客户端复用
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..config import get_app_config, AppConfig
from ..models import QATask, TaskFilter, QATaskStatus

# 复用Oxygent的ES客户端
from oxygent.db_factory import DBFactory
from oxygent.databases.db_es import LocalEs, JesEs


logger = logging.getLogger(__name__)


class ESService:
    """ES服务类 - 复用Oxygent的ES客户端
    
    适配层：统一 LocalEs 和 JesEs 的接口差异
    """
    
    def __init__(self, config: AppConfig = None):
        self.config = config or get_app_config()
        self.index_prefix = self.config.es.index_prefix
        self.index_name = f"{self.index_prefix}_qa_task"
        
        # 复用Oxygent的ES客户端
        self.es_client = self._get_es_client()
        
        # 缓存
        self._hash_cache: set = set()
    
    def _get_es_client(self):
        """通过db_factory获取Oxygent的ES客户端（复用）
        
        LocalEs: 不需要参数，直接实例化
        JesEs: 需要 hosts, user, password
        """
        if self.config.es.user and self.config.es.password:
            # 使用远程ES
            return DBFactory().get_instance(
                JesEs,
                self.config.es.hosts,
                self.config.es.user,
                self.config.es.password
            )
        else:
            # 使用本地ES（LocalEs不需要参数）
            return DBFactory().get_instance(LocalEs)
    
    async def create_index(self):
        """创建索引"""
        exists = await self.es_client.index_exists(self.index_name)
        if exists:
            logger.info(f"索引 {self.index_name} 已存在")
            return
        
        mapping = {
            "mappings": {
                "properties": {
                    "qa_id": {"type": "keyword"},
                    "task_id": {"type": "keyword"},
                    
                    # QA内容
                    "question": {"type": "text"},
                    "answer": {"type": "text"},
                    "qa_hash": {"type": "keyword"},
                    
                    # 来源追溯
                    "source_type": {"type": "keyword"},
                    "source_trace_id": {"type": "keyword"},
                    "source_node_id": {"type": "keyword"},
                    "source_group_id": {"type": "keyword"},
                    
                    # 层级关系
                    "is_root": {"type": "boolean"},
                    "parent_qa_id": {"type": "keyword"},
                    "depth": {"type": "integer"},
                    
                    # 调用链信息
                    "caller": {"type": "keyword"},
                    "callee": {"type": "keyword"},
                    "caller_type": {"type": "keyword"},
                    "callee_type": {"type": "keyword"},
                    
                    # 分类与标签
                    "category": {"type": "keyword"},
                    "tags": {"type": "keyword"},
                    
                    # 优先级
                    "priority": {"type": "integer"},
                    
                    # 状态
                    "status": {"type": "keyword"},
                    "stage": {"type": "keyword"},
                    
                    # 标注结果
                    "annotation": {"type": "object", "enabled": True},
                    "scores": {"type": "object", "enabled": True},
                    
                    # 分配信息
                    "assigned_to": {"type": "keyword"},
                    "assigned_at": {"type": "keyword"},
                    "expire_at": {"type": "keyword"},
                    
                    # 批次信息
                    "batch_id": {"type": "keyword"},
                    
                    # 时间戳
                    "created_at": {
                        "format": "yyyy-MM-dd HH:mm:ss.SSSSSSSSS",
                        "type": "date"
                    },
                    "updated_at": {
                        "format": "yyyy-MM-dd HH:mm:ss.SSSSSSSSS",
                        "type": "date"
                    },
                    
                    # 额外数据
                    "extra": {"type": "object", "enabled": True},
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            }
        }
        
        await self.es_client.create_index(self.index_name, mapping)
        logger.info(f"索引 {self.index_name} 创建成功")
    
    async def index_task(self, task: QATask) -> str:
        """索引单条任务"""
        doc = task.to_es_doc()
        await self.es_client.index(
            self.index_name,
            doc_id=task.qa_id,
            body=doc
        )
        return task.qa_id
    
    async def bulk_index_tasks(self, tasks: List[QATask]) -> tuple:
        """批量索引"""
        if not tasks:
            return 0, []
        
        # 检查是否是 LocalEs（没有 transport 属性）
        is_local_es = not hasattr(self.es_client, 'transport')
        
        if is_local_es:
            # LocalEs 的简化批量索引
            success_count = 0
            failed = []
            for task in tasks:
                try:
                    await self.index_task(task)
                    success_count += 1
                except Exception as e:
                    failed.append({"_id": task.qa_id, "error": str(e)})
            logger.info(f"批量索引成功: {success_count}, 失败: {len(failed)}")
            return success_count, failed
        else:
            # 标准 ES 客户端的批量索引
            actions = []
            for task in tasks:
                actions.append({
                    "_index": self.index_name,
                    "_id": task.qa_id,
                    "_source": task.to_es_doc()
                })
            
            from elasticsearch.helpers import async_bulk
            success, failed = await async_bulk(
                self.es_client,
                actions,
                raise_on_error=False,
                raise_on_exception=False
            )
            
            logger.info(f"批量索引成功: {success}, 失败: {len(failed) if isinstance(failed, list) else 0}")
            return success, failed or []
    
    async def get_task_by_id(self, qa_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取任务"""
        try:
            # LocalEs 没有 get 方法，使用 search 替代
            search_body = {
                "query": {"term": {"_id": qa_id}},
                "size": 1
            }
            result = await self.es_client.search(self.index_name, search_body)
            hits = result.get("hits", {}).get("hits", [])
            if hits:
                return hits[0].get("_source")
            return None
        except Exception as e:
            logger.error(f"获取任务失败: {e}")
            return None
    
    async def update_task(self, qa_id: str, update_data: Dict[str, Any]) -> bool:
        """更新任务"""
        try:
            update_data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            await self.es_client.update(
                self.index_name,
                doc_id=qa_id,
                body=update_data
            )
            return True
        except Exception as e:
            logger.error(f"更新任务失败: {e}")
            return False
    
    async def search_tasks(
        self,
        filter_params: TaskFilter,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """搜索任务"""
        must_clauses = []
        filter_clauses = []
        
        if filter_params.qa_type:
            must_clauses.append({"term": {"source_type": filter_params.qa_type}})
        
        if filter_params.status:
            must_clauses.append({"term": {"status": filter_params.status}})
        
        if filter_params.priority is not None:
            must_clauses.append({"term": {"priority": filter_params.priority}})
        
        if filter_params.group_id:
            must_clauses.append({"term": {"source_group_id": filter_params.group_id}})
        
        if filter_params.trace_id:
            must_clauses.append({"term": {"source_trace_id": filter_params.trace_id}})
        
        # 时间范围
        if filter_params.start_time or filter_params.end_time:
            time_range = {}
            if filter_params.start_time:
                time_range["gte"] = filter_params.start_time.strftime("%Y-%m-%d %H:%M:%S.%f")
            if filter_params.end_time:
                time_range["lte"] = filter_params.end_time.strftime("%Y-%m-%d %H:%M:%S.%f")
            filter_clauses.append({"range": {"created_at": time_range}})
        
        # 只显示根节点
        if filter_params.show_roots_only:
            must_clauses.append({"term": {"is_root": True}})
        
        # 显示子节点
        if filter_params.show_children and not filter_params.trace_id:
            low_score_roots = await self._get_low_score_root_qa_ids()
            if low_score_roots:
                filter_clauses.append({"terms": {"parent_qa_id": low_score_roots}})
        
        # 全文搜索
        if filter_params.search_text:
            must_clauses.append({
                "multi_match": {
                    "query": filter_params.search_text,
                    "fields": ["question", "answer", "category"],
                    "type": "best_fields"
                }
            })
        
        query = {
            "bool": {
                "must": must_clauses if must_clauses else [{"match_all": {}}],
                "filter": filter_clauses
            }
        }
        
        from_offset = (page - 1) * page_size
        
        # 构造 search body（统一接口）
        search_body = {
            "query": query,
            "from": from_offset,
            "size": page_size,
            "sort": [{"created_at": {"order": "desc"}}]
        }
        
        result = await self.es_client.search(self.index_name, search_body)
        
        hits = result.get("hits", {}).get("hits", [])
        total = result.get("hits", {}).get("total", {}).get("value", 0)
        
        items = []
        for hit in hits:
            item = hit["_source"]
            item["qa_id"] = hit["_id"]
            items.append(item)
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    
    async def _get_low_score_root_qa_ids(self, threshold: float = 0.6) -> List[str]:
        """获取低分根节点QA ID列表"""
        try:
            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"is_root": True}},
                            {"term": {"status": QATaskStatus.ANNOTATED.value}},
                        ],
                        "filter": [
                            {"range": {"scores.overall_score": {"lt": threshold}}}
                        ]
                    }
                },
                "size": 1000,
                "_source": ["qa_id"]
            }
            result = await self.es_client.search(self.index_name, search_body)
            
            return [hit["_source"]["qa_id"] for hit in result.get("hits", {}).get("hits", [])]
        except Exception as e:
            logger.error(f"查询低分根节点失败: {e}")
            return []
    
    async def get_children_by_parent_id(self, parent_qa_id: str) -> List[Dict[str, Any]]:
        """根据父QA ID获取子节点"""
        try:
            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"parent_qa_id": parent_qa_id}},
                            {"term": {"is_root": False}}
                        ]
                    }
                },
                "size": 100,
                "sort": [{"priority": {"order": "asc"}}]
            }
            result = await self.es_client.search(self.index_name, search_body)
            
            items = []
            for hit in result.get("hits", {}).get("hits", []):
                item = hit["_source"]
                item["qa_id"] = hit["_id"]
                items.append(item)
            
            return items
        except Exception as e:
            logger.error(f"查询子节点失败: {e}")
            return []
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            search_body = {
                "query": {"match_all": {}},
                "size": 0,
                "aggs": {
                    "total": {"value_count": {"field": "qa_id"}},
                    "by_status": {"terms": {"field": "status"}},
                    "by_priority": {"terms": {"field": "priority"}},
                    "by_type": {"terms": {"field": "source_type", "size": 20}}
                }
            }
            result = await self.es_client.search(self.index_name, search_body)
            
            aggs = result.get("aggregations", {})
            
            by_status = {bucket["key"]: bucket["doc_count"] for bucket in aggs.get("by_status", {}).get("buckets", [])}
            by_priority = {str(bucket["key"]): bucket["doc_count"] for bucket in aggs.get("by_priority", {}).get("buckets", [])}
            by_type = {bucket["key"]: bucket["doc_count"] for bucket in aggs.get("by_type", {}).get("buckets", [])}
            
            return {
                "total": aggs.get("total", {}).get("value", 0),
                "by_status": by_status,
                "by_priority": by_priority,
                "by_type": by_type,
                "pending": by_status.get(QATaskStatus.PENDING.value, 0),
                "annotated": by_status.get(QATaskStatus.ANNOTATED.value, 0),
                "approved": by_status.get(QATaskStatus.APPROVED.value, 0),
                "rejected": by_status.get(QATaskStatus.REJECTED.value, 0)
            }
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return {
                "total": 0,
                "by_status": {},
                "by_priority": {},
                "by_type": {},
                "pending": 0,
                "annotated": 0,
                "approved": 0,
                "rejected": 0
            }
    
    # ========== 去重相关 ==========
    
    def _is_duplicate_in_memory(self, qa_hash: str) -> bool:
        """内存缓存去重"""
        if qa_hash in self._hash_cache:
            return True
        self._hash_cache.add(qa_hash)
        if len(self._hash_cache) > 100000:
            self._hash_cache = set(list(self._hash_cache)[50000:])
        return False
    
    async def _check_hash_exists_in_es(self, qa_hash: str) -> bool:
        """ES中去重检查"""
        try:
            search_body = {
                "query": {"term": {"qa_hash": qa_hash}},
                "size": 0
            }
            result = await self.es_client.search(self.index_name, search_body)
            return result.get("hits", {}).get("total", {}).get("value", 0) > 0
        except Exception:
            return False
    
    async def is_duplicate(self, qa_hash: str) -> bool:
        """完整去重检查：内存 + ES"""
        if self._is_duplicate_in_memory(qa_hash):
            return True
        if await self._check_hash_exists_in_es(qa_hash):
            self._hash_cache.add(qa_hash)
            return True
        return False


# 全局ES服务实例
_es_service: Optional[ESService] = None


def get_es_service() -> ESService:
    """获取ES服务（单例）"""
    global _es_service
    if _es_service is None:
        config = get_app_config()
        _es_service = ESService(config)
    return _es_service


async def init_es_service() -> ESService:
    """初始化ES服务"""
    service = get_es_service()
    await service.create_index()
    return service


def reset_es_service():
    """重置ES服务（用于测试）"""
    global _es_service
    _es_service = None
