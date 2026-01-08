"""
Knowledge Base Ingestion Service

Handles integration with the Knowledge Base platform for ingesting annotated QA data.
"""
import logging
from typing import Any, Dict, Optional
from datetime import datetime
import aiohttp

from ..config import get_app_config, KBConfig
from ..models import KBIngestionRequest, KBIngestionResponse


logger = logging.getLogger(__name__)


class KBService:
    """Knowledge Base Ingestion Service Class
    
    Handles communication with the Knowledge Base platform API.
    """
    
    def __init__(self, config: KBConfig = None):
        """Initialize KB service
        
        Args:
            config: KB configuration (uses global config if not provided)
        """
        if config is None:
            app_config = get_app_config()
            self.config = app_config.kb
        else:
            self.config = config
        
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    def is_enabled(self) -> bool:
        """Check if KB ingestion is enabled"""
        return (
            self.config.enabled and 
            bool(self.config.endpoint) and 
            bool(self.config.kb_id)
        )
    
    async def ingest(
        self, 
        data: Dict[str, Any],
        question: str,
        answer: str,
        score: Optional[float] = None,
        remark: Optional[str] = None
    ) -> KBIngestionResponse:
        """
        Ingest QA data to Knowledge Base
        
        Args:
            data: Original QA data dictionary
            question: Question content
            answer: Answer content
            score: Quality score (0-1)
            remark: Additional remarks
        
        Returns:
            KBIngestionResponse: Ingestion result
        """
        if not self.is_enabled():
            return KBIngestionResponse(
                success=False,
                message="KB ingestion is not enabled. Please configure QA_KB_ENDPOINT and QA_KB_ID."
            )
        
        # Build ingestion request
        kb_request = KBIngestionRequest(
            question=question,
            answer=answer,
            score=score,
            caller=data.get("caller", ""),
            callee=data.get("callee", ""),
            remark=remark,
            source_trace_id=data.get("source_trace_id"),
            source_request_id=data.get("source_request_id"),
            data_type=data.get("data_type"),
            priority=data.get("priority"),
            category=data.get("category")
        )
        
        # Build API URL
        url = f"{self.config.endpoint}/api/v1/kb_base/{self.config.kb_id}/ingest_data"
        
        last_error = None
        for attempt in range(self.config.retry_times):
            try:
                session = await self._get_session()
                
                async with session.post(url, json=kb_request.model_dump()) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"KB ingestion successful: {result}")
                        return KBIngestionResponse(
                            success=True,
                            message="Ingestion successful",
                            kb_doc_id=result.get("doc_id") or result.get("id")
                        )
                    else:
                        error_text = await response.text()
                        logger.warning(f"KB ingestion API returned {response.status}: {error_text}")
                        last_error = f"API error {response.status}: {error_text}"
            
            except aiohttp.ClientError as e:
                logger.warning(f"KB ingestion attempt {attempt + 1} failed: {e}")
                last_error = str(e)
            
            # Wait before retry (except on last attempt)
            if attempt < self.config.retry_times - 1:
                await asyncio.sleep(self.config.retry_interval)
        
        # All retries failed
        logger.error(f"KB ingestion failed after {self.config.retry_times} attempts: {last_error}")
        return KBIngestionResponse(
            success=False,
            message=f"Ingestion failed after {self.config.retry_times} attempts: {last_error}"
        )
    
    async def ingest_batch(
        self,
        data_list: list,
        skip_on_error: bool = True
    ) -> Dict[str, Any]:
        """
        Batch ingest QA data to Knowledge Base
        
        Args:
            data_list: List of QA data dictionaries
            skip_on_error: Whether to skip remaining items on error
        
        Returns:
            Dict with success_count, failed_count, and results
        """
        if not self.is_enabled():
            return {
                "success": False,
                "message": "KB ingestion is not enabled",
                "total": len(data_list),
                "success_count": 0,
                "failed_count": len(data_list),
                "results": []
            }
        
        success_count = 0
        failed_count = 0
        results = []
        
        for idx, data in enumerate(data_list):
            try:
                # Extract data for ingestion
                question = data.get("question", "")
                answer = data.get("answer", "")
                score = data.get("scores", {}).get("overall_score")
                
                # Get annotation remark if available
                remark = None
                if data.get("annotation"):
                    remark = data["annotation"].get("comment") or data["annotation"].get("remark")
                
                result = await self.ingest(
                    data=data,
                    question=question,
                    answer=answer,
                    score=score,
                    remark=remark
                )
                
                if result.success:
                    success_count += 1
                    results.append({
                        "index": idx,
                        "data_id": data.get("data_id"),
                        "success": True,
                        "kb_doc_id": result.kb_doc_id
                    })
                else:
                    failed_count += 1
                    results.append({
                        "index": idx,
                        "data_id": data.get("data_id"),
                        "success": False,
                        "error": result.message
                    })
                    
                    if skip_on_error:
                        logger.warning(f"Stopping batch ingestion due to error at index {idx}")
                        break
            
            except Exception as e:
                logger.error(f"Error ingesting data at index {idx}: {e}")
                failed_count += 1
                results.append({
                    "index": idx,
                    "data_id": data.get("data_id"),
                    "success": False,
                    "error": str(e)
                })
                
                if skip_on_error:
                    break
        
        return {
            "success": failed_count == 0,
            "message": f"Batch ingestion: {success_count} succeeded, {failed_count} failed",
            "total": len(data_list),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results
        }


# Global KB Service Instance
_kb_service: Optional[KBService] = None


def get_kb_service() -> KBService:
    """Get KB service (singleton)"""
    global _kb_service
    if _kb_service is None:
        _kb_service = KBService()
    return _kb_service


async def close_kb_service():
    """Close KB service and cleanup"""
    global _kb_service
    if _kb_service:
        await _kb_service.close()
        _kb_service = None


import asyncio

