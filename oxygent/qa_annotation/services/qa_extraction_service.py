# -*- encoding: utf-8 -*-
"""
QA标注平台 - QA提取核心服务

MVP版本：直接从ES提取QA数据并建立层级关系，同步写入qa_task表
跳过MQ，简化流程，确保归属关系正确建立
"""

import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta

from oxygent.config import Config
from oxygent.utils.common_utils import generate_uuid, get_format_time, get_md5
from oxygent.qa_annotation.schemas import QATaskStatus, QATaskStage

logger = logging.getLogger(__name__)


class QAExtractionService:
    """
    QA提取核心服务
    
    核心功能：
    1. 从ES的trace/node表提取QA对
    2. 建立端到端(E2E)与子任务的层级关系
    3. 同步写入qa_task表
    4. 支持去重
    
    层级关系说明：
    - E2E任务（P0）：用户->主Agent的完整对话，parent_task_id为空
    - 子任务（P1-P3）：E2E任务触发的内部调用，parent_task_id指向E2E任务
    
    数据来源：
    - trace表：存储E2E对话 (caller_category=user)
    - node表：存储所有节点调用记录
    """
    
    def __init__(self, es_client):
        self.es_client = es_client
        self.app_name = Config.get_app_name()
        self.collector_config = Config.get_qa_collector_config()
        self.task_config = Config.get_qa_task_config()
        
        # 索引名称
        self.trace_index = f"{self.app_name}_trace"
        self.node_index = f"{self.app_name}_node"
        self.task_index = f"{self.app_name}_qa_task"
        
        # 去重缓存
        self._hash_cache: set = set()
    
    async def extract_and_save(
        self,
        start_time: str,
        end_time: str,
        include_sub_nodes: bool = True,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """
        提取QA并保存到任务表
        
        核心流程：
        1. 查询时间范围内的trace记录（E2E对话）
        2. 为每个trace创建E2E任务
        3. 查询该trace下的node记录（子调用）
        4. 为每个node创建子任务，parent_task_id指向E2E任务
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            include_sub_nodes: 是否包含子节点
            limit: 最大提取数量
            
        Returns:
            提取结果统计
        """
        batch_id = generate_uuid()
        stats = {
            "batch_id": batch_id,
            "e2e_count": 0,
            "sub_task_count": 0,
            "skipped": 0,
            "errors": [],
            "started_at": get_format_time(),
        }
        
        # 确保索引存在
        await self._ensure_index_exists()
        
        try:
            # 1. 查询trace记录
            traces = await self._query_traces(start_time, end_time, limit)
            logger.info(f"Found {len(traces)} traces to extract")
            
            for trace in traces:
                trace_id = trace.get("trace_id", "")
                
                # 2. 创建E2E任务
                e2e_task = self._trace_to_task(trace, batch_id)
                if e2e_task is None:
                    stats["skipped"] += 1
                    continue
                
                # 去重检查（内存缓存 + ES）
                if await self._is_duplicate_full(e2e_task["qa_hash"]):
                    stats["skipped"] += 1
                    continue
                
                # 保存E2E任务
                try:
                    await self._save_task(e2e_task)
                    stats["e2e_count"] += 1
                except Exception as e:
                    stats["errors"].append(f"Save E2E task error: {e}")
                    continue
                
                # 3. 提取子节点
                if include_sub_nodes:
                    sub_count = await self._extract_sub_nodes(
                        trace_id=trace_id,
                        parent_task_id=e2e_task["task_id"],
                        batch_id=batch_id,
                        stats=stats
                    )
                    stats["sub_task_count"] += sub_count
        
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            stats["errors"].append(str(e))
        
        stats["finished_at"] = get_format_time()
        stats["total_extracted"] = stats["e2e_count"] + stats["sub_task_count"]
        
        logger.info(
            f"Extraction completed: batch={batch_id}, "
            f"e2e={stats['e2e_count']}, sub={stats['sub_task_count']}, "
            f"skipped={stats['skipped']}"
        )
        
        return stats
    
    async def _query_traces(
        self,
        start_time: str,
        end_time: str,
        limit: int
    ) -> List[dict]:
        """查询trace记录"""
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
            result = await self.es_client.search(self.trace_index, query)
            return [hit["_source"] for hit in result.get("hits", {}).get("hits", [])]
        except Exception as e:
            logger.error(f"Query traces error: {e}")
            return []
    
    async def _extract_sub_nodes(
        self,
        trace_id: str,
        parent_task_id: str,
        batch_id: str,
        stats: dict
    ) -> int:
        """提取trace下的子节点"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"trace_id": trace_id}},
                        {"term": {"state": 3}},  # COMPLETED
                    ],
                    "must_not": [
                        {"term": {"caller": "user"}}  # 排除用户直接调用
                    ]
                }
            },
            "size": 500,
            "sort": [{"create_time": {"order": "asc"}}]
        }
        
        try:
            result = await self.es_client.search(self.node_index, query)
            nodes = [hit["_source"] for hit in result.get("hits", {}).get("hits", [])]
        except Exception as e:
            logger.warning(f"Query nodes error for trace {trace_id}: {e}")
            return 0
        
        count = 0
        for node in nodes:
            task = self._node_to_task(node, batch_id, parent_task_id)
            if task is None:
                stats["skipped"] += 1
                continue
            
            # 去重（内存缓存 + ES）
            if await self._is_duplicate_full(task["qa_hash"]):
                stats["skipped"] += 1
                continue
            
            try:
                await self._save_task(task)
                count += 1
            except Exception as e:
                stats["errors"].append(f"Save sub task error: {e}")
        
        return count
    
    def _trace_to_task(self, trace: dict, batch_id: str) -> Optional[dict]:
        """将trace记录转换为E2E任务"""
        try:
            # 解析input获取question
            input_str = trace.get("input", "{}")
            if isinstance(input_str, str):
                input_data = json.loads(input_str)
            else:
                input_data = input_str or {}
            
            question = input_data.get("query", "")
            
            # 解析output获取answer
            output = trace.get("output", "")
            if isinstance(output, str):
                answer = output
            else:
                answer = str(output) if output else ""
            
            # 验证长度
            min_q = self.collector_config.get("min_question_length", 2)
            min_a = self.collector_config.get("min_answer_length", 10)
            
            if len(str(question)) < min_q or len(answer) < min_a:
                return None
            
            # 计算过期时间
            expire_hours = self.task_config.get("expire_hours", 24)
            expire_at = (datetime.now() + timedelta(hours=expire_hours)).strftime("%Y-%m-%d %H:%M:%S")
            
            task_id = generate_uuid()
            qa_hash = get_md5(f"{question}:{answer}")
            
            return {
                "task_id": task_id,
                "qa_id": generate_uuid(),
                "batch_id": batch_id,
                
                # QA内容
                "question": str(question),
                "answer": answer,
                "qa_hash": qa_hash,
                
                # 来源追溯
                "source_type": "e2e",
                "source_trace_id": trace.get("trace_id", ""),
                "source_node_id": "",
                "source_group_id": trace.get("group_id", ""),
                "call_chain": ["user", trace.get("callee", "")],
                
                # 层级关系 - E2E是顶层，没有parent
                "parent_task_id": "",
                
                # 优先级
                "priority": 0,  # P0
                "category": "",
                "tags": [],
                
                # 状态
                "status": QATaskStatus.PENDING.value,
                "stage": QATaskStage.PENDING.value,
                
                # 分配
                "assigned_to": "",
                "assigned_at": "",
                "expire_at": expire_at,
                
                # 时间
                "created_at": trace.get("create_time", get_format_time()),
                "updated_at": get_format_time(),
            }
        except Exception as e:
            logger.warning(f"Parse trace error: {e}")
            return None
    
    def _node_to_task(
        self,
        node: dict,
        batch_id: str,
        parent_task_id: str
    ) -> Optional[dict]:
        """将node记录转换为子任务"""
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
            output = node.get("output", "")
            if isinstance(output, str):
                answer = output
            else:
                answer = str(output) if output else ""
            
            # 验证
            min_q = self.collector_config.get("min_question_length", 2)
            min_a = self.collector_config.get("min_answer_length", 10)
            
            if len(str(question)) < min_q or len(answer) < min_a:
                return None
            
            # 排除LLM和retrieve_tools
            callee = node.get("callee", "")
            node_type = node.get("node_type", "")
            exclude_callees = self.collector_config.get(
                "exclude_callees", ["retrieve_tools", "default_llm"]
            )
            exclude_types = self.collector_config.get("exclude_callee_types", ["llm"])
            
            if callee in exclude_callees or node_type in exclude_types:
                return None
            
            # 计算优先级和source_type
            caller = node.get("caller", "")
            if caller == "user":
                priority = 1
                source_type = "user_agent"
            elif node_type == "agent":
                priority = 2
                source_type = "agent_agent"
            else:
                priority = 3
                source_type = "agent_tool"
            
            # 过期时间
            expire_hours = self.task_config.get("expire_hours", 24)
            expire_at = (datetime.now() + timedelta(hours=expire_hours)).strftime("%Y-%m-%d %H:%M:%S")
            
            task_id = generate_uuid()
            qa_hash = get_md5(f"{question}:{answer}")
            
            return {
                "task_id": task_id,
                "qa_id": generate_uuid(),
                "batch_id": batch_id,
                
                # QA内容
                "question": str(question),
                "answer": answer,
                "qa_hash": qa_hash,
                
                # 来源追溯
                "source_type": source_type,
                "source_trace_id": node.get("trace_id", ""),
                "source_node_id": node.get("node_id", ""),
                "source_group_id": node.get("group_id", ""),
                "call_chain": node.get("call_stack", []),
                
                # 层级关系 - 指向E2E父任务
                "parent_task_id": parent_task_id,
                
                # 优先级
                "priority": priority,
                "category": "",
                "tags": [],
                
                # 状态
                "status": QATaskStatus.PENDING.value,
                "stage": QATaskStage.PENDING.value,
                
                # 分配
                "assigned_to": "",
                "assigned_at": "",
                "expire_at": expire_at,
                
                # 时间
                "created_at": node.get("create_time", get_format_time()),
                "updated_at": get_format_time(),
            }
        except Exception as e:
            logger.warning(f"Parse node error: {e}")
            return None
    
    def _is_duplicate(self, qa_hash: str) -> bool:
        """检查是否重复（内存缓存）"""
        if not self.task_config.get("dedup_enabled", True):
            return False
        
        if qa_hash in self._hash_cache:
            return True
        
        self._hash_cache.add(qa_hash)
        
        # 限制缓存大小
        if len(self._hash_cache) > 100000:
            self._hash_cache = set(list(self._hash_cache)[50000:])
        
        return False
    
    async def _check_hash_exists_in_es(self, qa_hash: str) -> bool:
        """检查qa_hash是否已存在于ES中"""
        try:
            query = {
                "query": {"term": {"qa_hash": qa_hash}},
                "size": 0
            }
            result = await self.es_client.search(self.task_index, query)
            count = result.get("hits", {}).get("total", {}).get("value", 0)
            return count > 0
        except Exception:
            return False
    
    async def _is_duplicate_full(self, qa_hash: str) -> bool:
        """完整去重检查：内存缓存 + ES查询"""
        # 先检查内存缓存
        if self._is_duplicate(qa_hash):
            return True
        
        # 再检查ES
        if await self._check_hash_exists_in_es(qa_hash):
            self._hash_cache.add(qa_hash)
            return True
        
        return False
    
    async def _save_task(self, task: dict):
        """保存任务到ES"""
        await self.es_client.index(
            self.task_index,
            doc_id=task["task_id"],
            body=task
        )
    
    async def _ensure_index_exists(self):
        """确保任务索引存在"""
        try:
            exists = await self.es_client.index_exists(self.task_index)
            if not exists:
                from oxygent.qa_annotation.schemas.task import QA_TASK_MAPPING
                await self.es_client.create_index(self.task_index, QA_TASK_MAPPING)
                logger.info(f"Created index: {self.task_index}")
        except Exception as e:
            logger.warning(f"Check/create index error: {e}")
    
    async def preview(
        self,
        start_time: str,
        end_time: str,
    ) -> Dict[str, Any]:
        """预览可提取的数据量"""
        stats = {
            "trace_count": 0,
            "node_count": 0,
            "estimated_total": 0,
        }
        
        # 统计trace
        try:
            query = {
                "query": {
                    "range": {"create_time": {"gte": start_time, "lte": end_time}}
                },
                "size": 0
            }
            result = await self.es_client.search(self.trace_index, query)
            stats["trace_count"] = result.get("hits", {}).get("total", {}).get("value", 0)
        except Exception as e:
            logger.warning(f"Count traces error: {e}")
        
        # 统计node
        try:
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {"range": {"create_time": {"gte": start_time, "lte": end_time}}},
                            {"term": {"state": 3}},
                        ],
                        "must_not": [
                            {"term": {"caller": "user"}}
                        ]
                    }
                },
                "size": 0
            }
            result = await self.es_client.search(self.node_index, query)
            stats["node_count"] = result.get("hits", {}).get("total", {}).get("value", 0)
        except Exception as e:
            logger.warning(f"Count nodes error: {e}")
        
        stats["estimated_total"] = stats["trace_count"] + stats["node_count"]
        
        return stats

