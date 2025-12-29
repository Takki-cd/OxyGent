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
            "skip_reasons": {
                "validation_failed": 0,
                "duplicate_es": 0,
                "duplicate_memory": 0,
            },
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

                # 记录验证失败的具体原因
                if e2e_task is None:
                    # 解析数据，查看是因为什么问题验证失败
                    input_str = trace.get("input", "{}")
                    question = ""
                    if isinstance(input_str, str):
                        try:
                            input_data = json.loads(input_str)
                            question = input_data.get("query", "")
                        except Exception:
                            pass
                    else:
                        question = input_data.get("query", "") if isinstance(input_data, dict) else ""

                    output = trace.get("output", "")
                    answer = output if isinstance(output, str) else str(output) if output else ""

                    min_q = self.collector_config.get("min_question_length", 2)
                    min_a = self.collector_config.get("min_answer_length", 1)

                    q_len = len(str(question))
                    a_len = len(answer)

                    if q_len < min_q:
                        logger.debug(f"Skip trace {trace_id}: question_too_short (len={q_len}, min={min_q}, question='{str(question)[:50]}')")
                    if a_len < min_a:
                        logger.debug(f"Skip trace {trace_id}: answer_too_short (len={a_len}, min={min_a}, answer='{answer[:50] if answer else 'empty'}')")

                    stats["skipped"] += 1
                    stats["skip_reasons"]["validation_failed"] += 1
                    continue
                
                # 去重检查（内存缓存 + ES）
                is_dup, dup_source = await self._is_duplicate_full_with_source(e2e_task["qa_hash"])

                if is_dup:
                    logger.debug(f"Skip trace {trace_id}: duplicate_qa_hash (hash={e2e_task['qa_hash'][:16]}..., source={dup_source})")
                    stats["skipped"] += 1
                    if dup_source == "memory":
                        stats["skip_reasons"]["duplicate_memory"] += 1
                    else:
                        stats["skip_reasons"]["duplicate_es"] += 1
                    # 即使E2E任务重复，也要提取子节点（llm/tool）
                    if include_sub_nodes:
                        sub_count = await self._extract_sub_nodes(
                            trace_id=trace_id,
                            parent_task_id="",  # 重复的E2E任务不保存，子节点独立
                            batch_id=batch_id,
                            stats=stats
                        )
                        stats["sub_task_count"] += sub_count
                    continue
                
                # 保存E2E任务
                try:
                    await self._save_task(e2e_task)
                    stats["e2e_count"] += 1
                    logger.info(f"Saved E2E task: trace_id={trace_id}, question='{str(e2e_task['question'])[:30]}...'")
                except Exception as e:
                    stats["errors"].append(f"Save E2E task error: {e}")
                    logger.warning(f"Failed to save E2E task {trace_id}: {e}")
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
            f"skipped={stats['skipped']} (validation={stats['skip_reasons']['validation_failed']}, "
            f"dup_es={stats['skip_reasons']['duplicate_es']}, dup_mem={stats['skip_reasons']['duplicate_memory']})"
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
        """
        提取trace下的子节点

        改造说明：
        子节点不再设置parent_task_id（独立为顶级任务），
        而是通过trace_id建立关联关系用于后续追溯。
        这样所有任务都可以在列表中直接展示input/output。
        """
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
            # 改造：传递空parent_task_id，使子节点成为独立任务
            task = self._node_to_task(node, batch_id, parent_task_id="")
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
            
            # 验证长度（只验证question，answer允许为空以保留bad case）
            min_q = self.collector_config.get("min_question_length", 2)
            
            if len(str(question)) < min_q:
                return None
            
            # 计算过期时间
            expire_hours = self.task_config.get("expire_hours", 24)
            expire_at = (datetime.now() + timedelta(hours=expire_hours)).strftime("%Y-%m-%d %H:%M:%S")
            
            # 获取caller/callee信息
            caller = trace.get("caller", "user")
            callee = trace.get("callee", "")
            caller_type = trace.get("caller_category", "user")
            callee_type = trace.get("node_type", "agent")
            
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
                "call_chain": ["user", callee] if callee else [],

                # 层级关系 - E2E任务标记
                "is_root": True,  # 标记为根任务（端到端）
                "parent_task_id": "",

                # 调用者与被调用者信息
                "caller": caller,
                "callee": callee,
                "caller_type": caller_type,
                "callee_type": callee_type,

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
        parent_task_id: str = ""  # 改造：默认为空，子节点独立存储
    ) -> Optional[dict]:
        """
        将node记录转换为子任务

        改造说明：
        子节点现在独立存储，不设置parent_task_id。
        保留source_trace_id用于追溯属于哪个E2E对话。
        每个节点的input和output作为独立的QA对展示。

        简化处理（用户需求）：
        - 对于llm/tool类型节点：直接把input的JSON作为question存储
        - 对于agent类型节点：提取query字段作为question
        """
        try:
            # 解析input
            input_str = node.get("input", "{}")
            if isinstance(input_str, str):
                input_data = json.loads(input_str)
            else:
                input_data = input_str or {}
            
            arguments = input_data.get("arguments", {})
            node_type = node.get("node_type", "")
            
            # 根据node_type提取question（简化处理）
            if node_type in ["llm", "tool"]:
                # llm/tool类型：直接把input的JSON字符串作为question
                question = input_str if isinstance(input_str, str) else json.dumps(input_data)
            else:
                # agent类型：提取query字段
                question = arguments.get("query", "")
            
            # 解析output
            output = node.get("output", "")
            if isinstance(output, str):
                answer = output
            else:
                answer = str(output) if output else ""
            
            # 验证（只验证question，answer允许为空以保留bad case）
            min_q = self.collector_config.get("min_question_length", 2)
            
            if len(str(question)) < min_q:
                return None
            
            # 改造：不再排除LLM和tool，所有类型的节点都需要导入
            callee = node.get("callee", "")
            node_type = node.get("node_type", "")
            exclude_callees = self.collector_config.get(
                "exclude_callees", ["retrieve_tools"]
            )
            
            # 只排除指定的callee名称，不再按node_type排除
            if callee in exclude_callees:
                return None
            
            # 获取caller/callee信息（新增）
            caller = node.get("caller", "")
            caller_type = node.get("caller_type", "")
            callee_type = node_type  # node_type就是callee_type
            
            # 优先级计算（改造：新的优先级定义）
            # P0: 端到端（E2E）- 已在trace处理
            # P1: 子agent
            # P2: llm
            # P3: tool
            # P4: 其他
            if caller == "user":
                # 用户直接调用的agent
                priority = 1
                source_type = "user_agent"
            elif node_type == "agent":
                # 子agent
                priority = 1
                source_type = "agent_agent"
            elif node_type == "llm":
                # LLM调用
                priority = 2
                source_type = "agent_llm"
            elif node_type == "tool":
                # Tool调用
                priority = 3
                source_type = "agent_tool"
            else:
                # 其他类型
                priority = 4
                source_type = "agent_other"
            
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
                
                # 调用者与被调用者信息（新增）
                "caller": caller,
                "callee": callee,
                "caller_type": caller_type,
                "callee_type": callee_type,

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
    
    async def _is_duplicate_full_with_source(self, qa_hash: str) -> Tuple[bool, str]:
        """
        完整去重检查：内存缓存 + ES查询（返回来源）
        
        Returns:
            (is_duplicate, source): source为"memory"、"es"或""
        """
        # 先检查内存缓存
        if qa_hash in self._hash_cache:
            return True, "memory"
        
        # 再检查ES
        if await self._check_hash_exists_in_es(qa_hash):
            self._hash_cache.add(qa_hash)
            return True, "es"
        
        return False, ""
    
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
        include_sub_nodes: bool = True,
        limit: int = 1000,
        search_keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        预览可提取的数据量（支持过滤条件，排除已导入）

        改造说明：
        支持按关键词过滤，并自动排除已导入的数据。
        返回真正的待导入数量，而非原始trace数量。

        Args:
            start_time: 开始时间
            end_time: 结束时间
            include_sub_nodes: 是否包含子节点
            limit: 最大预览数量
            search_keyword: 搜索关键词（过滤question/answer）

        Returns:
            {
                "trace_count": int,           # 时间范围内总trace数
                "trace_imported": int,        # 已导入的trace数
                "trace_pending": int,         # 待导入的trace数（去重后）
                "node_count": int,            # 时间范围内总node数（不含user调用）
                "node_imported": int,         # 已导入的node数
                "node_pending": int,          # 待导入的node数（去重后）
                "estimated_total": int,       # 预估总量
            }
        """
        stats = {
            "trace_count": 0,
            "trace_imported": 0,
            "trace_pending": 0,
            "node_count": 0,
            "node_imported": 0,
            "node_pending": 0,
            "estimated_total": 0,
        }

        # 构建时间范围查询
        time_range = {"range": {"create_time": {"gte": start_time, "lte": end_time}}}

        # 构建关键词过滤条件（如果有）
        keyword_filter = {}
        if search_keyword:
            keyword_filter = {
                "bool": {
                    "should": [
                        {"match": {"question": search_keyword}},
                        {"match": {"answer": search_keyword}},
                    ],
                    "minimum_should_match": 1
                }
            }

        # 1. 查询时间范围内的trace记录
        try:
            trace_query = {
                "query": {
                    "bool": {
                        "must": [time_range]
                    }
                },
                "size": 0
            }
            # 添加关键词过滤
            if search_keyword:
                trace_query["query"]["bool"]["must"].append(keyword_filter)

            result = await self.es_client.search(self.trace_index, trace_query)
            stats["trace_count"] = result.get("hits", {}).get("total", {}).get("value", 0)
        except Exception as e:
            logger.warning(f"Count traces error: {e}")

        # 2. 查询已导入的trace_id集合（用于去重）
        try:
            imported_trace_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"priority": 0}},  # E2E任务
                        ]
                    }
                },
                "size": 10000,
                "_source": ["source_trace_id"]
            }
            # 添加时间范围过滤（只查询时间范围内的已导入数据）
            if start_time or end_time:
                imported_time_range = {}
                if start_time:
                    imported_time_range["gte"] = start_time
                if end_time:
                    imported_time_range["lte"] = end_time
                imported_trace_query["query"]["bool"]["must"].append(
                    {"range": {"created_at": imported_time_range}}
                )
            # 添加关键词过滤
            if search_keyword:
                imported_trace_query["query"]["bool"]["must"].append(keyword_filter)

            imported_result = await self.es_client.search(self.task_index, imported_trace_query)
            imported_trace_ids = set()
            for hit in imported_result.get("hits", {}).get("hits", []):
                trace_id = hit.get("_source", {}).get("source_trace_id")
                if trace_id:
                    imported_trace_ids.add(trace_id)

            stats["trace_imported"] = len(imported_trace_ids)
            stats["trace_pending"] = max(0, stats["trace_count"] - len(imported_trace_ids))
        except Exception as e:
            logger.warning(f"Query imported traces error: {e}")
            stats["trace_imported"] = 0
            stats["trace_pending"] = stats["trace_count"]

        # 3. 查询时间范围内的node记录（不含user调用）
        if include_sub_nodes:
            try:
                node_query = {
                    "query": {
                        "bool": {
                            "must": [time_range],
                            "must_not": [
                                {"term": {"caller": "user"}}
                            ]
                        }
                    },
                    "size": 0
                }
                # 添加关键词过滤
                if search_keyword:
                    node_query["query"]["bool"]["must"].append(keyword_filter)

                result = await self.es_client.search(self.node_index, node_query)
                stats["node_count"] = result.get("hits", {}).get("total", {}).get("value", 0)
            except Exception as e:
                logger.warning(f"Count nodes error: {e}")

            # 4. 查询已导入的node（用于去重）
            try:
                imported_node_query = {
                    "query": {"match_all": {}},
                    "size": 10000,
                    "_source": ["qa_hash"]
                }
                # 添加时间范围过滤
                if start_time or end_time:
                    imported_node_time_range = {}
                    if start_time:
                        imported_node_time_range["gte"] = start_time
                    if end_time:
                        imported_node_time_range["lte"] = end_time
                    imported_node_query["query"] = {
                        "bool": {
                            "must": [{"range": {"created_at": imported_node_time_range}}]
                        }
                    }
                    # 添加关键词过滤
                    if search_keyword:
                        imported_node_query["query"]["bool"]["must"].append(keyword_filter)

                imported_result = await self.es_client.search(self.task_index, imported_node_query)
                imported_hashes = set()
                for hit in imported_result.get("hits", {}).get("hits", []):
                    qa_hash = hit.get("_source", {}).get("qa_hash")
                    if qa_hash:
                        imported_hashes.add(qa_hash)

                # 统计子节点已导入数量（估算）
                stats["node_imported"] = len(imported_hashes)
                stats["node_pending"] = max(0, stats["node_count"] - stats["node_imported"])
            except Exception as e:
                logger.warning(f"Query imported nodes error: {e}")

        stats["estimated_total"] = stats["trace_pending"] + stats["node_pending"]

        return stats
