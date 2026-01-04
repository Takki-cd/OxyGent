"""
标注服务层 - 业务逻辑

按group_id/trace_id聚合
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


logger = logging.getLogger(__name__)


class AnnotationService:
    """标注服务类 - 简化版
    
    核心变更：
    - 删除QAContext，不再维护内存中的层级关系
    - 直接通过group_id/trace_id聚合查询
    - 简化去重逻辑（基于data_hash）
    """
    
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
        """注入单条数据"""
        # 检查重复
        data_hash = request.compute_data_hash()
        is_dup = await self.es_service.is_duplicate(data_hash)
        if is_dup:
            existing = await self._get_existing_by_hash(data_hash)
            if existing:
                logger.info(f"数据重复，跳过: hash={data_hash[:16]}...")
                return {
                    "success": True,
                    "data_id": existing["data_id"],
                    "message": "数据已存在"
                }
        
        if not self.batch_id:
            self.batch_id = self._new_batch_id()
        
        data = QAData.from_deposit_request(request, self.batch_id)
        
        await self.es_service.index_data(data)
        
        logger.info(f"数据注入成功: data_id={data.data_id}, trace_id={data.source_trace_id}, priority={data.priority}, caller={data.caller}, callee={data.callee}")
        
        return {
            "success": True,
            "data_id": data.data_id,
            "message": "注入成功"
        }
    
    async def _get_existing_by_hash(self, data_hash: str) -> Optional[Dict]:
        """根据hash获取已存在的数据"""
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
        """批量注入数据"""
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
            "message": f"批量注入: 成功{success_count}条, 跳过{len(skipped)}条, 失败{len(failed)}条"
        }
    
    async def get_data_list(
        self,
        filter_params: DataFilter,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """获取数据列表"""
        return await self.es_service.search_data(filter_params, page, page_size)
    
    async def get_data_by_id(self, data_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取数据详情"""
        return await self.es_service.get_data_by_id(data_id)
    
    async def get_by_trace_id(self, trace_id: str) -> List[Dict[str, Any]]:
        """根据trace_id获取所有关联数据"""
        return await self.es_service.get_by_trace_id(trace_id)
    
    async def get_by_group_id(self, group_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """根据group_id获取所有关联数据"""
        return await self.es_service.get_by_group_id(group_id, limit)
    
    async def get_grouped_summary(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取分组汇总"""
        return await self.es_service.get_grouped_summary(page, page_size)
    
    async def update_annotation(
        self, 
        data_id: str, 
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
        
        success = await self.es_service.update_data(data_id, update_data)
        
        if success:
            return {"success": True, "message": "更新成功"}
        else:
            return {"success": False, "message": "更新失败"}
    
    async def get_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> StatsResponse:
        """获取统计信息（支持时间过滤）"""
        stats = await self.es_service.get_stats(start_time=start_time, end_time=end_time)
        return StatsResponse(**stats)
    
    async def approve(self, data_id: str) -> Dict[str, Any]:
        """审核通过"""
        success = await self.es_service.update_data(
            data_id, 
            {"status": DataStatus.APPROVED.value}
        )
        return {"success": success, "message": "已通过" if success else "失败"}
    
    async def reject(self, data_id: str, reject_reason: str = None) -> Dict[str, Any]:
        """审核拒绝"""
        update_data = {
            "status": DataStatus.REJECTED.value,
            "reject_reason": reject_reason or ""
        }
        success = await self.es_service.update_data(data_id, update_data)
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
