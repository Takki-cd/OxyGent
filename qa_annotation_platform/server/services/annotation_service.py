"""
Annotation Service Layer - Business Logic

Aggregate by group_id/trace_id
"""
import logging
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..models import (
    QAData, 
    DataStatus, 
    DepositRequest, 
    BatchDepositRequest,
    AnnotationUpdate,
    DataFilter,
    StatsResponse
)
from .es_service import get_es_service, ESService
from .kb_service import get_kb_service, KBService


logger = logging.getLogger(__name__)


class AnnotationService:
    """Annotation Service Class - Simplified
    
    Core Changes:
    - Delete QAContext, no longer maintain hierarchical relationships in memory
    - Directly aggregate query by group_id/trace_id
    - Simplify deduplication logic (based on data_hash)
    """
    
    def __init__(self, es_service: ESService, config: Dict[str, Any] = None):
        self.es_service = es_service
        self.config = config or {}
        self.batch_id = ""
    
    def _new_batch_id(self) -> str:
        """Generate batch ID"""
        import hashlib
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return hashlib.md5(timestamp.encode()).hexdigest()[:16]
    
    async def deposit(self, request: DepositRequest) -> Dict[str, Any]:
        """Deposit single data"""
        # Check duplicate
        data_hash = request.compute_data_hash()
        is_dup = await self.es_service.is_duplicate(data_hash)
        if is_dup:
            existing = await self._get_existing_by_hash(data_hash)
            if existing:
                logger.info(f"Duplicate data, skip: hash={data_hash[:16]}...")
                return {
                    "success": True,
                    "data_id": existing["data_id"],
                    "message": "Data already exists"
                }
        
        if not self.batch_id:
            self.batch_id = self._new_batch_id()
        
        data = QAData.from_deposit_request(request, self.batch_id)
        
        await self.es_service.index_data(data)
        
        logger.info(f"Data deposit successful: data_id={data.data_id}, trace_id={data.source_trace_id}, priority={data.priority}, caller={data.caller}, callee={data.callee}")
        
        return {
            "success": True,
            "data_id": data.data_id,
            "message": "Deposit successful"
        }
    
    async def _get_existing_by_hash(self, data_hash: str) -> Optional[Dict]:
        """Get existing data by hash"""
        try:
            search_body = {
                "query": {"term": {"data_hash": data_hash}},
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
        """Batch deposit data"""
        if not self.batch_id:
            self.batch_id = self._new_batch_id()
        
        data_list = []
        skipped = []
        failed = []
        
        for item in request.items:
            data_hash = item.compute_data_hash()
            is_dup = await self.es_service.is_duplicate(data_hash)
            
            if is_dup:
                skipped.append(item)
                continue
            
            try:
                data = QAData.from_deposit_request(item, self.batch_id)
                data_list.append(data)
            except Exception as e:
                failed.append({"item": item, "error": str(e)})
        
        if data_list:
            success_count, failed_batch = await self.es_service.bulk_index_data(data_list)
            failed.extend(failed_batch)
        else:
            success_count = 0
        
        return {
            "success": True,
            "total": len(request.items),
            "success_count": success_count,
            "skipped_count": len(skipped),
            "failed_count": len(failed),
            "data_ids": [d.data_id for d in data_list],
            "message": f"Batch deposit: {success_count} succeeded, {len(skipped)} skipped, {len(failed)} failed"
        }
    
    async def get_data_list(
        self,
        filter_params: DataFilter,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """Get data list"""
        return await self.es_service.search_data(filter_params, page, page_size)
    
    async def get_data_by_id(self, data_id: str) -> Optional[Dict[str, Any]]:
        """Get data details by ID"""
        return await self.es_service.get_data_by_id(data_id)
    
    async def get_by_trace_id(self, trace_id: str) -> List[Dict[str, Any]]:
        """Get all related data by trace_id"""
        return await self.es_service.get_by_trace_id(trace_id)
    
    async def get_by_group_id(self, group_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all related data by group_id"""
        return await self.es_service.get_by_group_id(group_id, limit)
    
    async def get_grouped_summary(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """Get grouped summary"""
        return await self.es_service.get_grouped_summary(page, page_size)
    
    async def update_annotation(
        self, 
        data_id: str, 
        update: AnnotationUpdate
    ) -> Dict[str, Any]:
        """Update annotation"""
        update_data = {}
        
        if update.status:
            update_data["status"] = update.status
        
        if update.annotation:
            update_data["annotation"] = update.annotation
        
        if update.scores:
            update_data["scores"] = update.scores
        
        if not update_data:
            return {"success": False, "message": "No content to update"}
        
        success = await self.es_service.update_data(data_id, update_data)
        
        if success:
            return {"success": True, "message": "Update successful"}
        else:
            return {"success": False, "message": "Update failed"}
    
    async def get_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> StatsResponse:
        """Get statistics (support time filtering)"""
        stats = await self.es_service.get_stats(start_time=start_time, end_time=end_time)
        return StatsResponse(**stats)
    
    async def approve(self, data_id: str, auto_ingest: bool = False) -> Dict[str, Any]:
        """
        Approve review
        
        Args:
            data_id: Data ID to approve
            auto_ingest: Whether to automatically ingest to KB after approval
        """
        from ..config import get_app_config
        
        success = await self.es_service.update_data(
            data_id, 
            {"status": DataStatus.APPROVED.value}
        )
        
        if not success:
            return {"success": False, "message": "Failed to approve"}
        
        # Check if auto-ingest is enabled (config or parameter)
        config = get_app_config()
        should_auto_ingest = auto_ingest or config.kb.auto_ingest
        
        if should_auto_ingest and config.kb.enabled:
            # Auto-ingest to KB
            ingest_result = await self.ingest_to_kb(data_id)
            return {
                "success": True, 
                "message": "Approved and ingested to Knowledge Base",
                "kb_ingested": ingest_result.get("success", False)
            }
        
        return {"success": True, "message": "Approved"}
    
    async def reject(self, data_id: str, reject_reason: str = None) -> Dict[str, Any]:
        """Reject review"""
        update_data = {
            "status": DataStatus.REJECTED.value,
            "reject_reason": reject_reason or ""
        }
        success = await self.es_service.update_data(data_id, update_data)
        return {"success": success, "message": "Rejected" if success else "Failed"}
    
    # ==================== Knowledge Base Ingestion ====================
    
    async def ingest_to_kb(self, data_id: str) -> Dict[str, Any]:
        """
        Ingest data to Knowledge Base
        
        Args:
            data_id: Data ID to ingest
        
        Returns:
            Dict with success status and message
        """
        # Get data details
        data = await self.es_service.get_data_by_id(data_id)
        if not data:
            return {"success": False, "message": "Data not found"}
        
        # Check status - only approved data can be ingested
        if data.get("status") not in [DataStatus.APPROVED.value, DataStatus.KB_FAILED.value]:
            return {
                "success": False, 
                "message": f"Cannot ingest data with status '{data.get('status')}'. Only approved data can be ingested."
            }
        
        # Check if already ingested
        if data.get("kb_status") == DataStatus.KB_INGESTED.value:
            return {"success": False, "message": "Data has already been ingested to KB"}
        
        # Get KB service
        kb_service = get_kb_service()
        
        # Extract score and remark from annotation
        score = None
        remark = None
        correct_answer = None
        if data.get("annotation"):
            score = data["annotation"].get("score")
            remark = data["annotation"].get("comment")
            correct_answer = data["annotation"].get("content")
        
        # If score not in annotation, check scores
        if score is None and data.get("scores"):
            score = data["scores"].get("overall_score")
        
        # Ingest to KB
        result = await kb_service.ingest(
            data=data,
            question=data.get("question", ""),
            answer=correct_answer,
            score=score,
            remark=remark
        )
        
        if result.success:
            # Update status to KB_INGESTED
            await self.es_service.update_data(data_id, {
                "status": DataStatus.KB_INGESTED.value,
                "kb_status": DataStatus.KB_INGESTED.value,
                "kb_ingested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                "kb_error_message": ""
            })
            logger.info(f"KB ingestion successful: data_id={data_id}, kb_doc_id={result.kb_doc_id}")
            return {
                "success": True, 
                "message": "Successfully ingested to Knowledge Base",
                "kb_doc_id": result.kb_doc_id
            }
        else:
            # Update status to KB_FAILED
            await self.es_service.update_data(data_id, {
                "status": DataStatus.KB_FAILED.value,
                "kb_status": DataStatus.KB_FAILED.value,
                "kb_error_message": result.message
            })
            logger.error(f"KB ingestion failed: data_id={data_id}, error={result.message}")
            return {
                "success": False, 
                "message": f"KB ingestion failed: {result.message}"
            }


# Global Service Instance
_annotation_service: Optional[AnnotationService] = None


def get_annotation_service() -> AnnotationService:
    """Get annotation service (singleton)"""
    global _annotation_service
    if _annotation_service is None:
        es_service = get_es_service()
        _annotation_service = AnnotationService(es_service)
    return _annotation_service


def reset_annotation_service():
    """Reset annotation service (for testing)"""
    global _annotation_service
    _annotation_service = None
