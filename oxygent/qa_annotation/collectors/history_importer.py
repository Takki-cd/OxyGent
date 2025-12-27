# -*- encoding: utf-8 -*-
"""
QA标注平台 - 历史数据导入器

从ES历史数据批量导入QA数据到标注平台
"""

import json
import logging
from typing import Dict, Any, Optional, List

from oxygent.config import Config
from oxygent.utils.common_utils import generate_uuid, get_format_time, get_md5

logger = logging.getLogger(__name__)


class QAHistoryImporter:
    """
    从ES历史数据批量导入QA
    
    支持从trace表和node表导入数据，用于标注平台的历史数据初始化。
    
    Usage:
        importer = QAHistoryImporter(es_client)
        
        # 预览导入数据量
        stats = await importer.preview_import("2025-01-01", "2025-01-31")
        
        # 执行导入
        result = await importer.import_data(
            start_time="2025-01-01 00:00:00",
            end_time="2025-01-31 23:59:59",
            include_trace=True,
            include_node_agent=True,
        )
    """
    
    def __init__(self, es_client, mq_client=None):
        """
        初始化导入器
        
        Args:
            es_client: ES客户端实例
            mq_client: MQ客户端实例（可选，会自动获取）
        """
        self.es_client = es_client
        self.mq = mq_client
        self.app_name = Config.get_app_name()
        self.collector_config = Config.get_qa_collector_config()
    
    async def _ensure_mq(self):
        """确保MQ客户端已初始化"""
        if self.mq is None:
            from oxygent.qa_annotation.mq_factory import MQFactory
            self.mq = await MQFactory().get_instance()
    
    async def preview_import(
        self,
        start_time: str,
        end_time: str,
        include_trace: bool = True,
        include_node_agent: bool = True,
        include_node_tool: bool = False,
    ) -> Dict[str, int]:
        """
        预览导入数据量
        
        Args:
            start_time: 开始时间 (YYYY-MM-DD HH:mm:ss)
            end_time: 结束时间
            include_trace: 是否包含trace表
            include_node_agent: 是否包含agent类型node
            include_node_tool: 是否包含tool类型node
        
        Returns:
            各数据源的数量统计
        """
        stats = {
            "trace_count": 0,
            "node_agent_count": 0,
            "node_tool_count": 0,
            "estimated_total": 0,
        }
        
        time_range = {"range": {"create_time": {"gte": start_time, "lte": end_time}}}
        
        if include_trace:
            trace_query = {
                "query": {"bool": {"must": [time_range]}},
                "size": 0
            }
            try:
                result = await self.es_client.search(f"{self.app_name}_trace", trace_query)
                stats["trace_count"] = result.get("hits", {}).get("total", {}).get("value", 0)
            except Exception as e:
                logger.warning(f"Failed to count traces: {e}")
        
        if include_node_agent:
            agent_query = {
                "query": {
                    "bool": {
                        "must": [
                            time_range,
                            {"term": {"node_type": "agent"}},
                            {"term": {"state": 3}},  # COMPLETED
                        ]
                    }
                },
                "size": 0
            }
            try:
                result = await self.es_client.search(f"{self.app_name}_node", agent_query)
                stats["node_agent_count"] = result.get("hits", {}).get("total", {}).get("value", 0)
            except Exception as e:
                logger.warning(f"Failed to count agent nodes: {e}")
        
        if include_node_tool:
            tool_query = {
                "query": {
                    "bool": {
                        "must": [
                            time_range,
                            {"term": {"node_type": "tool"}},
                            {"term": {"state": 3}},
                        ]
                    }
                },
                "size": 0
            }
            try:
                result = await self.es_client.search(f"{self.app_name}_node", tool_query)
                stats["node_tool_count"] = result.get("hits", {}).get("total", {}).get("value", 0)
            except Exception as e:
                logger.warning(f"Failed to count tool nodes: {e}")
        
        stats["estimated_total"] = (
            stats["trace_count"] +
            stats["node_agent_count"] +
            stats["node_tool_count"]
        )
        
        return stats
    
    async def import_data(
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
            start_time: 开始时间 (YYYY-MM-DD HH:mm:ss)
            end_time: 结束时间
            include_trace: 是否导入trace表
            include_node_agent: 是否导入agent类型node
            include_node_tool: 是否导入tool类型node
            include_sub_nodes: 导入trace时是否同时导入关联的子节点
            limit: 最大导入数量
            
        Returns:
            导入结果统计
        """
        await self._ensure_mq()
        
        batch_id = generate_uuid()
        stats = {
            "batch_id": batch_id,
            "trace_imported": 0,
            "node_imported": 0,
            "skipped": 0,
            "errors": 0,
            "started_at": get_format_time(),
        }
        
        # 用于记录已处理的trace，避免重复导入子节点
        processed_traces = set()
        # 用于记录trace_id到qa_id的映射
        trace_qa_mapping = {}
        
        try:
            # 1. 导入trace表数据
            if include_trace:
                trace_result = await self._import_traces(
                    start_time, end_time, batch_id, limit,
                    include_sub_nodes, trace_qa_mapping, processed_traces
                )
                stats["trace_imported"] = trace_result["imported"]
                stats["node_imported"] += trace_result["sub_nodes"]
                stats["skipped"] += trace_result["skipped"]
            
            # 2. 导入node表数据（排除已通过trace导入的）
            remaining_limit = limit - stats["trace_imported"] - stats["node_imported"]
            if remaining_limit > 0 and (include_node_agent or include_node_tool):
                node_result = await self._import_nodes(
                    start_time, end_time, batch_id, remaining_limit,
                    include_node_agent, include_node_tool,
                    processed_traces, trace_qa_mapping
                )
                stats["node_imported"] += node_result["imported"]
                stats["skipped"] += node_result["skipped"]
        
        except Exception as e:
            logger.error(f"Import failed: {e}")
            stats["errors"] += 1
            stats["error_message"] = str(e)
        
        stats["finished_at"] = get_format_time()
        stats["total_imported"] = stats["trace_imported"] + stats["node_imported"]
        
        logger.info(f"Import completed: batch_id={batch_id}, total={stats['total_imported']}")
        return stats
    
    async def _import_traces(
        self,
        start_time: str,
        end_time: str,
        batch_id: str,
        limit: int,
        include_sub_nodes: bool,
        trace_qa_mapping: Dict[str, str],
        processed_traces: set,
    ) -> Dict[str, int]:
        """从trace表导入端到端QA"""
        result = {"imported": 0, "sub_nodes": 0, "skipped": 0}
        
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"range": {"create_time": {"gte": start_time, "lte": end_time}}}
                    ]
                }
            },
            "size": limit,
            "sort": [{"create_time": {"order": "desc"}}]
        }
        
        try:
            es_result = await self.es_client.search(f"{self.app_name}_trace", query)
            traces = es_result.get("hits", {}).get("hits", [])
        except Exception as e:
            logger.error(f"Failed to query traces: {e}")
            return result
        
        for trace_hit in traces:
            trace = trace_hit["_source"]
            trace_id = trace.get("trace_id")
            
            # 解析并验证
            qa_data = self._trace_to_qa(trace, batch_id)
            if qa_data is None:
                result["skipped"] += 1
                continue
            
            # 发布到MQ
            try:
                await self.mq.publish("raw", qa_data, priority=0)
                result["imported"] += 1
            except Exception as e:
                logger.warning(f"Failed to publish trace {trace_id}: {e}")
                result["skipped"] += 1
                continue
            
            # 记录映射关系
            trace_qa_mapping[trace_id] = qa_data["qa_id"]
            processed_traces.add(trace_id)
            
            # 导入关联的子节点
            if include_sub_nodes:
                sub_count = await self._import_sub_nodes(
                    trace_id, batch_id, qa_data["qa_id"]
                )
                result["sub_nodes"] += sub_count
        
        return result
    
    async def _import_sub_nodes(
        self,
        trace_id: str,
        batch_id: str,
        parent_qa_id: str
    ) -> int:
        """导入某个trace下的所有子节点"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"trace_id": trace_id}},
                        {"term": {"state": 3}},  # COMPLETED
                    ],
                    "must_not": [
                        {"term": {"caller": "user"}}  # 排除user直接调用的（已在trace中）
                    ]
                }
            },
            "size": 1000,
            "sort": [{"create_time": {"order": "asc"}}]
        }
        
        try:
            result = await self.es_client.search(f"{self.app_name}_node", query)
            nodes = result.get("hits", {}).get("hits", [])
        except Exception as e:
            logger.warning(f"Failed to query sub nodes for trace {trace_id}: {e}")
            return 0
        
        count = 0
        for node_hit in nodes:
            node = node_hit["_source"]
            qa_data = self._node_to_qa(node, batch_id, parent_qa_id)
            
            if qa_data is not None:
                try:
                    await self.mq.publish("raw", qa_data, priority=qa_data["priority"])
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to publish node: {e}")
        
        return count
    
    async def _import_nodes(
        self,
        start_time: str,
        end_time: str,
        batch_id: str,
        limit: int,
        include_agent: bool,
        include_tool: bool,
        processed_traces: set,
        trace_qa_mapping: Dict[str, str],
    ) -> Dict[str, int]:
        """从node表单独导入"""
        result = {"imported": 0, "skipped": 0}
        
        # 构建node_type过滤
        node_types = []
        if include_agent:
            node_types.append("agent")
        if include_tool:
            node_types.append("tool")
        
        if not node_types:
            return result
        
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"range": {"create_time": {"gte": start_time, "lte": end_time}}},
                        {"term": {"state": 3}},
                        {"terms": {"node_type": node_types}},
                    ]
                }
            },
            "size": limit,
            "sort": [{"create_time": {"order": "desc"}}]
        }
        
        try:
            es_result = await self.es_client.search(f"{self.app_name}_node", query)
            nodes = es_result.get("hits", {}).get("hits", [])
        except Exception as e:
            logger.error(f"Failed to query nodes: {e}")
            return result
        
        for node_hit in nodes:
            node = node_hit["_source"]
            trace_id = node.get("trace_id")
            
            # 跳过已处理的trace下的节点
            if trace_id in processed_traces:
                continue
            
            # 尝试获取parent_qa_id
            parent_qa_id = trace_qa_mapping.get(trace_id, "")
            
            qa_data = self._node_to_qa(node, batch_id, parent_qa_id)
            if qa_data is None:
                result["skipped"] += 1
                continue
            
            try:
                await self.mq.publish("raw", qa_data, priority=qa_data["priority"])
                result["imported"] += 1
            except Exception as e:
                logger.warning(f"Failed to publish node: {e}")
                result["skipped"] += 1
        
        return result
    
    def _trace_to_qa(self, trace: dict, batch_id: str) -> Optional[dict]:
        """将trace记录转换为QA数据"""
        try:
            # 解析input
            input_str = trace.get("input", "{}")
            if isinstance(input_str, str):
                input_data = json.loads(input_str)
            else:
                input_data = input_str or {}
            
            question = input_data.get("query", "")
            
            # 解析output
            output_str = trace.get("output", "")
            if isinstance(output_str, str):
                answer = output_str
            else:
                answer = str(output_str) if output_str else ""
            
            # 验证
            min_q = self.collector_config.get("min_question_length", 2)
            min_a = self.collector_config.get("min_answer_length", 10)
            
            if len(str(question)) < min_q or len(answer) < min_a:
                return None
            
            return {
                "qa_id": generate_uuid(),
                "batch_id": batch_id,
                "question": str(question),
                "answer": answer,
                "qa_hash": get_md5(f"{question}:{answer}"),
                "source_type": "e2e",
                "source_trace_id": trace.get("trace_id", ""),
                "source_node_id": "",
                "source_group_id": trace.get("group_id", ""),
                "caller": "user",
                "callee": trace.get("callee", ""),
                "caller_category": "user",
                "callee_category": "agent",
                "call_chain": ["user", trace.get("callee", "")],
                "parent_qa_id": "",  # 端到端没有parent
                "priority": 0,
                "created_at": trace.get("create_time", get_format_time()),
            }
        except Exception as e:
            logger.warning(f"Parse trace error: {e}")
            return None
    
    def _node_to_qa(
        self,
        node: dict,
        batch_id: str,
        parent_qa_id: str = ""
    ) -> Optional[dict]:
        """将node记录转换为QA数据"""
        try:
            # 解析input
            input_str = node.get("input", "{}")
            if isinstance(input_str, str):
                input_data = json.loads(input_str)
            else:
                input_data = input_str or {}
            
            arguments = input_data.get("arguments", {})
            question = arguments.get("query", "")
            
            # 解析output
            output_str = node.get("output", "")
            if isinstance(output_str, str):
                answer = output_str
            else:
                answer = str(output_str) if output_str else ""
            
            # 验证
            min_q = self.collector_config.get("min_question_length", 2)
            min_a = self.collector_config.get("min_answer_length", 10)
            
            if len(str(question)) < min_q or len(answer) < min_a:
                return None
            
            # 计算优先级
            caller = node.get("caller", "")
            node_type = node.get("node_type", "")
            
            if caller == "user":
                priority = 1
                source_type = "user_agent"
            elif node_type == "agent":
                priority = 2
                source_type = "agent_agent"
            else:
                priority = 3
                source_type = "agent_tool"
            
            return {
                "qa_id": generate_uuid(),
                "batch_id": batch_id,
                "question": str(question),
                "answer": answer,
                "qa_hash": get_md5(f"{question}:{answer}"),
                "source_type": source_type,
                "source_trace_id": node.get("trace_id", ""),
                "source_node_id": node.get("node_id", ""),
                "source_group_id": node.get("group_id", ""),
                "caller": caller,
                "callee": node.get("callee", ""),
                "caller_category": "agent" if caller != "user" else "user",
                "callee_category": node_type,
                "call_chain": node.get("call_stack", []),
                "parent_qa_id": parent_qa_id,
                "priority": priority,
                "created_at": node.get("create_time", get_format_time()),
            }
        except Exception as e:
            logger.warning(f"Parse node error: {e}")
            return None

