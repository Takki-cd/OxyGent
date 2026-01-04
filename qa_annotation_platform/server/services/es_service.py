"""
ES Service Layer - Reuse Oxygent's ES Client

Simplified: Aggregate by group_id/trace_id, no hierarchical relationships
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..config import get_app_config, AppConfig
from ..models import QAData, DataFilter, DataStatus

# Reuse Oxygent's ES Client
from oxygent.db_factory import DBFactory
from oxygent.databases.db_es import LocalEs, JesEs


logger = logging.getLogger(__name__)


class ESService:
    """ES Service Class - Simplified
    
    Core Changes:
    - Delete parent_qa_id, depth, is_root fields
    - Restore caller/callee fields
    - Add source_request_id, data_type fields
    - Support aggregate query by group_id/trace_id
    """
    
    def __init__(self, config: AppConfig = None):
        self.config = config or get_app_config()
        self.index_prefix = self.config.es.index_prefix
        self.index_name = f"{self.index_prefix}_qa_data"  # Simplified to qa_data
        
        # Reuse Oxygent's ES Client
        self.es_client = self._get_es_client()
        
        # Cache
        self._hash_cache: set = set()
    
    def _get_es_client(self):
        """Get Oxygent's ES Client through db_factory (reuse)"""
        if self.config.es.user and self.config.es.password:
            return DBFactory().get_instance(
                JesEs,
                self.config.es.hosts,
                self.config.es.user,
                self.config.es.password
            )
        else:
            return DBFactory().get_instance(LocalEs)
    
    async def create_index(self):
        """Create index"""
        exists = await self.es_client.index_exists(self.index_name)
        if exists:
            logger.info(f"Index {self.index_name} already exists")
            return
        
        mapping = {
            "mappings": {
                "properties": {
                    # Unique ID
                    "data_id": {"type": "keyword"},
                    
                    # QA Content
                    "question": {"type": "text"},
                    "answer": {"type": "text"},
                    "data_hash": {"type": "keyword"},
                    
                    # Source Tracing (Three Core Fields)
                    "source_trace_id": {"type": "keyword"},
                    "source_request_id": {"type": "keyword"},
                    "source_group_id": {"type": "keyword"},
                    
                    # Call Chain Information (caller/callee)
                    "caller": {"type": "keyword"},
                    "callee": {"type": "keyword"},
                    "caller_type": {"type": "keyword"},  # Reserved: Caller type
                    "callee_type": {"type": "keyword"},  # Reserved: Callee type
                    
                    # Data Type
                    "data_type": {"type": "keyword"},
                    
                    # Priority (End-to-End=0, Child nodes>0)
                    "priority": {"type": "integer"},
                    
                    # Category & Tags
                    "category": {"type": "keyword"},
                    "tags": {"type": "keyword"},
                    
                    # Status
                    "status": {"type": "keyword"},
                    
                    # Reject Reason
                    "reject_reason": {"type": "text"},
                    
                    # Annotation Result
                    "annotation": {"type": "object", "enabled": True},
                    "scores": {"type": "object", "enabled": True},
                    
                    # Batch Information
                    "batch_id": {"type": "keyword"},
                    
                    # Timestamp
                    "created_at": {
                        "format": "yyyy-MM-dd HH:mm:ss.SSSSSSSSS",
                        "type": "date"
                    },
                    "updated_at": {
                        "format": "yyyy-MM-dd HH:mm:ss.SSSSSSSSS",
                        "type": "date"
                    },
                    
                    # Extra Data
                    "extra": {"type": "object", "enabled": True},
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            }
        }
        
        await self.es_client.create_index(self.index_name, mapping)
        logger.info(f"Index {self.index_name} created successfully")
    
    async def index_data(self, data: QAData) -> str:
        """Index single data"""
        doc = data.to_es_doc()
        await self.es_client.index(
            self.index_name,
            doc_id=data.data_id,
            body=doc
        )
        return data.data_id
    
    async def bulk_index_data(self, data_list: List[QAData]) -> tuple:
        """Bulk index"""
        if not data_list:
            return 0, []
        
        is_local_es = not hasattr(self.es_client, 'transport')
        
        if is_local_es:
            success_count = 0
            failed = []
            for data in data_list:
                try:
                    await self.index_data(data)
                    success_count += 1
                except Exception as e:
                    failed.append({"_id": data.data_id, "error": str(e)})
            logger.info(f"Bulk index success: {success_count}, failed: {len(failed)}")
            return success_count, failed
        else:
            actions = []
            for data in data_list:
                actions.append({
                    "_index": self.index_name,
                    "_id": data.data_id,
                    "_source": data.to_es_doc()
                })
            
            from elasticsearch.helpers import async_bulk
            success, failed = await async_bulk(
                self.es_client,
                actions,
                raise_on_error=False,
                raise_on_exception=False
            )
            
            logger.info(f"Bulk index success: {success}, failed: {len(failed) if isinstance(failed, list) else 0}")
            return success, failed or []
    
    async def get_data_by_id(self, data_id: str) -> Optional[Dict[str, Any]]:
        """Get data by ID"""
        try:
            search_body = {
                "query": {"term": {"_id": data_id}},
                "size": 1
            }
            result = await self.es_client.search(self.index_name, search_body)
            hits = result.get("hits", {}).get("hits", [])
            if hits:
                return hits[0].get("_source")
            return None
        except Exception as e:
            logger.error(f"Failed to get data: {e}")
            return None
    
    async def update_data(self, data_id: str, update_data: Dict[str, Any]) -> bool:
        """Update data"""
        try:
            update_data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            await self.es_client.update(
                self.index_name,
                doc_id=data_id,
                body=update_data
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update data: {e}")
            return False
    
    async def search_data(
        self,
        filter_params: DataFilter,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """Search data"""
        must_clauses = []
        filter_clauses = []

        # Filter by caller (use match query for fuzzy matching, LocalEs already supports)
        if filter_params.caller and filter_params.caller.strip():
            must_clauses.append({"match": {"caller": filter_params.caller.strip()}})

        # Filter by callee (use match query for fuzzy matching)
        if filter_params.callee and filter_params.callee.strip():
            must_clauses.append({"match": {"callee": filter_params.callee.strip()}})

        # Filter by data_type (exact match)
        if filter_params.data_type and filter_params.data_type.strip():
            must_clauses.append({"term": {"data_type": filter_params.data_type.strip()}})

        # Filter by status (exact match)
        if filter_params.status and filter_params.status.strip():
            must_clauses.append({"term": {"status": filter_params.status.strip()}})

        # Filter by priority (exact match)
        if filter_params.priority is not None:
            must_clauses.append({"term": {"priority": filter_params.priority}})

        # Filter by group_id (exact match)
        if filter_params.group_id and filter_params.group_id.strip():
            must_clauses.append({"term": {"source_group_id": filter_params.group_id.strip()}})

        # Filter by trace_id (exact match)
        if filter_params.trace_id and filter_params.trace_id.strip():
            must_clauses.append({"term": {"source_trace_id": filter_params.trace_id.strip()}})

        # Exact match by request_id
        if filter_params.request_id and filter_params.request_id.strip():
            must_clauses.append({"term": {"source_request_id": filter_params.request_id.strip()}})

        # Time range
        if filter_params.start_time or filter_params.end_time:
            time_range = {}
            if filter_params.start_time:
                time_range["gte"] = filter_params.start_time.strftime("%Y-%m-%d %H:%M:%S.%f")
            if filter_params.end_time:
                time_range["lte"] = filter_params.end_time.strftime("%Y-%m-%d %H:%M:%S.%f")
            filter_clauses.append({"range": {"created_at": time_range}})

        # Only show P0 (End-to-End)
        if filter_params.show_p0_only:
            must_clauses.append({"term": {"priority": 0}})

        # Full-text search (use match query, LocalEs supports)
        if filter_params.search_text and filter_params.search_text.strip():
            search_term = filter_params.search_text.strip()
            # Match question and answer separately, following the simple match query approach of caller/callee
            must_clauses.append({"match": {"question": search_term}})
            # must_clauses.append({"match": {"answer": search_term}})

        query = {
            "bool": {
                "must": must_clauses if must_clauses else [{"match_all": {}}],
                "filter": filter_clauses
            }
        }

        from_offset = (page - 1) * page_size

        search_body = {
            "query": query,
            "from": from_offset,
            "size": page_size,
            "sort": [{"priority": {"order": "asc"}}, {"created_at": {"order": "desc"}}]
        }

        result = await self.es_client.search(self.index_name, search_body)
        all_items = []
        for hit in result.get("hits", {}).get("hits", []):
            sample = hit["_source"]
            all_items.append({
                "data_id": sample.get("data_id"),
                "caller": sample.get("caller"),
                "callee": sample.get("callee"),
                "question": (sample.get("question") or "")[:30],
                "created_at": sample.get("created_at")
            })

        hits = result.get("hits", {}).get("hits", [])
        total = result.get("hits", {}).get("total", {}).get("value", 0)

        items = []
        for hit in hits:
            item = hit["_source"]
            item["data_id"] = hit["_id"]
            items.append(item)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    
    async def get_by_trace_id(self, trace_id: str) -> List[Dict[str, Any]]:
        """Get all related data by trace_id (aggregate by trace)"""
        try:
            search_body = {
                "query": {
                    "term": {"source_trace_id": trace_id}
                },
                "size": 1000,
                "sort": [{"priority": {"order": "asc"}}, {"created_at": {"order": "asc"}}]
            }
            result = await self.es_client.search(self.index_name, search_body)
            
            items = []
            for hit in result.get("hits", {}).get("hits", []):
                item = hit["_source"]
                item["data_id"] = hit["_id"]
                items.append(item)
            
            return items
        except Exception as e:
            logger.error(f"Failed to query trace data: {e}")
            return []
    
    async def get_by_group_id(self, group_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all related data by group_id (aggregate by group)"""
        try:
            search_body = {
                "query": {
                    "term": {"source_group_id": group_id}
                },
                "size": limit,
                "sort": [{"priority": {"order": "asc"}}, {"created_at": {"order": "asc"}}]
            }
            result = await self.es_client.search(self.index_name, search_body)
            
            items = []
            for hit in result.get("hits", {}).get("hits", []):
                item = hit["_source"]
                item["data_id"] = hit["_id"]
                items.append(item)
            
            return items
        except Exception as e:
            logger.error(f"Failed to query group data: {e}")
            return []
    
    async def get_grouped_summary(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """Get grouped summary (aggregate by group_id)"""
        try:
            search_body = {
                "query": {"match_all": {}},
                "size": 0,
                "aggs": {
                    "groups": {
                        "terms": {
                            "field": "source_group_id",
                            "size": page_size * 2,
                            "order": {"_count": "desc"}
                        },
                        "aggs": {
                            "p0_count": {
                                "filter": {"term": {"priority": 0}}
                            },
                            "p0_pending": {
                                "filter": {
                                    "bool": {
                                        "must": [
                                            {"term": {"priority": 0}},
                                            {"term": {"status": DataStatus.PENDING.value}}
                                        ]
                                    }
                                }
                            }
                        }
                    }
                }
            }
            
            result = await self.es_client.search(self.index_name, search_body)
            
            aggs = result.get("aggregations", {})
            buckets = aggs.get("groups", {}).get("buckets", [])
            
            offset = (page - 1) * page_size
            page_buckets = buckets[offset:offset + page_size]
            
            groups = []
            for bucket in page_buckets:
                groups.append({
                    "source_group_id": bucket["key"],
                    "trace_count": 0,
                    "data_count": bucket["doc_count"],
                    "p0_count": bucket["p0_count"]["doc_count"],
                    "p0_pending": bucket["p0_pending"]["doc_count"]
                })
            
            total = len(buckets)
            
            return {
                "groups": groups,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }
        except Exception as e:
            logger.error(f"Failed to get grouped summary: {e}")
            return {
                "groups": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0
            }
    
    async def get_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get statistics (support time filtering)"""
        try:
            # Build time range query
            must_clauses = []
            filter_clauses = []
            
            if start_time or end_time:
                time_range = {}
                if start_time:
                    time_range["gte"] = start_time.strftime("%Y-%m-%d %H:%M:%S.%f")
                if end_time:
                    time_range["lte"] = end_time.strftime("%Y-%m-%d %H:%M:%S.%f")
                filter_clauses.append({"range": {"created_at": time_range}})
            
            # Build query conditions
            if filter_clauses:
                query = {"bool": {"filter": filter_clauses}}
            else:
                query = {"match_all": {}}
            
            search_body = {
                "query": query,
                "size": 0,
                "aggs": {
                    "total": {"value_count": {"field": "data_id"}},
                    "by_status": {"terms": {"field": "status"}},
                    "by_priority": {"terms": {"field": "priority"}},
                    "by_caller": {"terms": {"field": "caller", "size": 50}},
                    "by_callee": {"terms": {"field": "callee", "size": 50}}
                }
            }
            result = await self.es_client.search(self.index_name, search_body)
            
            aggs = result.get("aggregations", {})
            
            by_status = {bucket["key"]: bucket["doc_count"] for bucket in aggs.get("by_status", {}).get("buckets", [])}
            by_priority = {str(bucket["key"]): bucket["doc_count"] for bucket in aggs.get("by_priority", {}).get("buckets", [])}
            by_caller = {bucket["key"]: bucket["doc_count"] for bucket in aggs.get("by_caller", {}).get("buckets", [])}
            by_callee = {bucket["key"]: bucket["doc_count"] for bucket in aggs.get("by_callee", {}).get("buckets", [])}
            
            return {
                "total": aggs.get("total", {}).get("value", 0),
                "by_status": by_status,
                "by_priority": by_priority,
                "by_caller": by_caller,
                "by_callee": by_callee,
                "pending": by_status.get(DataStatus.PENDING.value, 0),
                "annotated": by_status.get(DataStatus.ANNOTATED.value, 0),
                "approved": by_status.get(DataStatus.APPROVED.value, 0),
                "rejected": by_status.get(DataStatus.REJECTED.value, 0)
            }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {
                "total": 0,
                "by_status": {},
                "by_priority": {},
                "by_caller": {},
                "by_callee": {},
                "pending": 0,
                "annotated": 0,
                "approved": 0,
                "rejected": 0
            }
    
    # ========== Deduplication Related ==========
    
    def _is_duplicate_in_memory(self, data_hash: str) -> bool:
        """Memory cache deduplication"""
        if data_hash in self._hash_cache:
            return True
        self._hash_cache.add(data_hash)
        if len(self._hash_cache) > 100000:
            self._hash_cache = set(list(self._hash_cache)[50000:])
        return False
    
    async def _check_hash_exists_in_es(self, data_hash: str) -> bool:
        """Deduplication check in ES"""
        try:
            search_body = {
                "query": {"term": {"data_hash": data_hash}},
                "size": 0
            }
            result = await self.es_client.search(self.index_name, search_body)
            return result.get("hits", {}).get("total", {}).get("value", 0) > 0
        except Exception:
            return False
    
    async def is_duplicate(self, data_hash: str) -> bool:
        """Complete deduplication check: Memory + ES"""
        if self._is_duplicate_in_memory(data_hash):
            return True
        if await self._check_hash_exists_in_es(data_hash):
            self._hash_cache.add(data_hash)
            return True
        return False


# Global ES Service Instance
_es_service: Optional[ESService] = None


def get_es_service() -> ESService:
    """Get ES service (singleton)"""
    global _es_service
    if _es_service is None:
        config = get_app_config()
        _es_service = ESService(config)
    return _es_service


async def init_es_service() -> ESService:
    """Initialize ES service"""
    service = get_es_service()
    await service.create_index()
    return service


def reset_es_service():
    """Reset ES service (for testing)"""
    global _es_service
    _es_service = None
