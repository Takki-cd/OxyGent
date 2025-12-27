# -*- encoding: utf-8 -*-
"""
QA标注平台 - 数据导入服务

提供数据导入的API层封装
"""

import logging
from typing import Dict, Any, Optional

from oxygent.config import Config
from oxygent.qa_annotation.collectors import QAHistoryImporter
from oxygent.qa_annotation.mq_factory import MQFactory

logger = logging.getLogger(__name__)


class ImportService:
    """
    数据导入服务
    
    封装历史数据导入功能，提供预览和执行导入能力
    """
    
    def __init__(self, es_client):
        """
        初始化导入服务
        
        Args:
            es_client: ES客户端
        """
        self.es_client = es_client
        self._importer: Optional[QAHistoryImporter] = None
    
    async def _get_importer(self) -> QAHistoryImporter:
        """获取导入器实例"""
        if self._importer is None:
            mq = await MQFactory().get_instance()
            self._importer = QAHistoryImporter(self.es_client, mq)
        return self._importer
    
    async def preview_import(
        self,
        start_time: str,
        end_time: str,
        include_trace: bool = True,
        include_node_agent: bool = True,
        include_node_tool: bool = False,
    ) -> Dict[str, Any]:
        """
        预览导入数据量
        
        Args:
            start_time: 开始时间 (YYYY-MM-DD HH:mm:ss)
            end_time: 结束时间
            include_trace: 是否包含trace表
            include_node_agent: 是否包含agent类型node
            include_node_tool: 是否包含tool类型node
            
        Returns:
            预览统计结果
        """
        importer = await self._get_importer()
        return await importer.preview_import(
            start_time=start_time,
            end_time=end_time,
            include_trace=include_trace,
            include_node_agent=include_node_agent,
            include_node_tool=include_node_tool,
        )
    
    async def execute_import(
        self,
        start_time: str,
        end_time: str,
        include_trace: bool = True,
        include_node_agent: bool = True,
        include_node_tool: bool = False,
        include_sub_nodes: bool = True,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """
        执行导入
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            include_trace: 是否导入trace表
            include_node_agent: 是否导入agent类型node
            include_node_tool: 是否导入tool类型node
            include_sub_nodes: 是否导入子节点
            limit: 最大导入数量
            
        Returns:
            导入结果统计
        """
        importer = await self._get_importer()
        return await importer.import_data(
            start_time=start_time,
            end_time=end_time,
            include_trace=include_trace,
            include_node_agent=include_node_agent,
            include_node_tool=include_node_tool,
            include_sub_nodes=include_sub_nodes,
            limit=limit,
        )
    
    async def get_available_date_range(self) -> Dict[str, Any]:
        """
        获取可导入的数据日期范围
        
        Returns:
            {
                "trace_min_date": str,
                "trace_max_date": str,
                "node_min_date": str,
                "node_max_date": str
            }
        """
        app_name = Config.get_app_name()
        result = {}
        
        # 查询trace表日期范围
        try:
            trace_query = {
                "size": 0,
                "aggs": {
                    "min_date": {"min": {"field": "create_time"}},
                    "max_date": {"max": {"field": "create_time"}}
                }
            }
            trace_result = await self.es_client.search(f"{app_name}_trace", trace_query)
            aggs = trace_result.get("aggregations", {})
            result["trace_min_date"] = aggs.get("min_date", {}).get("value_as_string", "")
            result["trace_max_date"] = aggs.get("max_date", {}).get("value_as_string", "")
        except Exception as e:
            logger.warning(f"Failed to get trace date range: {e}")
            result["trace_min_date"] = ""
            result["trace_max_date"] = ""
        
        # 查询node表日期范围
        try:
            node_query = {
                "size": 0,
                "aggs": {
                    "min_date": {"min": {"field": "create_time"}},
                    "max_date": {"max": {"field": "create_time"}}
                }
            }
            node_result = await self.es_client.search(f"{app_name}_node", node_query)
            aggs = node_result.get("aggregations", {})
            result["node_min_date"] = aggs.get("min_date", {}).get("value_as_string", "")
            result["node_max_date"] = aggs.get("max_date", {}).get("value_as_string", "")
        except Exception as e:
            logger.warning(f"Failed to get node date range: {e}")
            result["node_min_date"] = ""
            result["node_max_date"] = ""
        
        return result
    
    async def get_import_history(
        self,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        获取导入历史记录
        
        TODO: 实现导入批次记录的存储和查询
        """
        # 当前版本简化处理，返回空列表
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "records": [],
        }

