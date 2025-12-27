# -*- encoding: utf-8 -*-
"""
QA标注平台 - 任务分配器

将处理后的QA数据分配为标注任务

Pipeline: qa:raw/qa:processed -> qa:pending
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from oxygent.config import Config
from oxygent.utils.common_utils import generate_uuid, get_format_time
from oxygent.qa_annotation.mq.base_mq import BaseMQ, MQMessage, MQTopic
from oxygent.qa_annotation.schemas import QATaskStatus, QATaskStage
from .base_processor import BaseProcessor

logger = logging.getLogger(__name__)


class TaskDispatcher(BaseProcessor):
    """
    任务分配器
    
    职责:
    1. 从qa:raw或qa:processed消费消息
    2. 创建标注任务
    3. 可选：分配给标注者
    4. 发布到qa:pending队列
    5. 同时写入ES持久化
    
    MVP版本说明:
    - 跳过LLM处理器，直接从qa:raw消费
    - 简化任务分配，不分配具体标注者
    """
    
    def __init__(
        self,
        mq: BaseMQ,
        es_client = None,
        skip_llm_processor: bool = True,
        consumer_group: str = "task_dispatcher",
        **kwargs
    ):
        """
        初始化任务分配器
        
        Args:
            mq: MQ客户端
            es_client: ES客户端（用于持久化任务）
            skip_llm_processor: 是否跳过LLM处理器（MVP模式）
            consumer_group: 消费者组名
        """
        # MVP模式：直接从raw消费；完整模式：从processed消费
        input_topic = MQTopic.RAW.value if skip_llm_processor else MQTopic.PROCESSED.value
        
        super().__init__(
            mq=mq,
            input_topic=input_topic,
            output_topic=MQTopic.PENDING.value,
            consumer_group=consumer_group,
            **kwargs
        )
        
        self.es_client = es_client
        self.skip_llm_processor = skip_llm_processor
        self.app_name = Config.get_app_name()
        self.task_config = Config.get_qa_task_config()
        
        # 去重缓存（简单实现，生产环境应使用Redis）
        self._qa_hash_cache: set = set()
    
    async def on_before_process(self, message: MQMessage) -> bool:
        """
        处理前检查
        
        1. 去重检查
        2. 质量过滤（如果有LLM处理结果）
        """
        data = message.data
        
        # 去重检查
        qa_hash = data.get("qa_hash", "")
        if qa_hash and self.task_config.get("dedup_enabled", True):
            if qa_hash in self._qa_hash_cache:
                logger.debug(f"Duplicate QA detected: {qa_hash}")
                return False
            self._qa_hash_cache.add(qa_hash)
            
            # 限制缓存大小
            if len(self._qa_hash_cache) > 100000:
                # 简单清理策略：清空一半
                self._qa_hash_cache = set(list(self._qa_hash_cache)[50000:])
        
        # 质量过滤（如果有LLM处理结果）
        if not self.skip_llm_processor:
            llm_is_valid = data.get("llm_is_valid", True)
            if not llm_is_valid:
                logger.debug(f"Invalid QA filtered: {data.get('qa_id')}")
                return False
            
            quality_threshold = self.task_config.get("quality_threshold", 0.3)
            llm_quality_score = data.get("llm_quality_score", 1.0)
            if llm_quality_score < quality_threshold:
                logger.debug(f"Low quality QA filtered: {data.get('qa_id')}, score={llm_quality_score}")
                return False
        
        return True
    
    async def process(self, message: MQMessage) -> Optional[dict]:
        """
        处理消息：创建标注任务
        
        Args:
            message: 输入消息（RawQAMessage或ProcessedQAMessage）
            
        Returns:
            TaskMessage字典
        """
        data = message.data
        
        # 生成任务ID
        task_id = generate_uuid()
        
        # 计算过期时间
        expire_hours = self.task_config.get("expire_hours", 24)
        expire_at = (datetime.now() + timedelta(hours=expire_hours)).strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建任务数据
        task_data = {
            # 任务标识
            "task_id": task_id,
            "qa_id": data.get("qa_id", ""),
            "batch_id": data.get("batch_id", ""),
            
            # QA内容
            "question": data.get("question", ""),
            "answer": data.get("answer", ""),
            "qa_hash": data.get("qa_hash", ""),
            
            # 来源信息
            "source_type": data.get("source_type", ""),
            "source_trace_id": data.get("source_trace_id", ""),
            "source_node_id": data.get("source_node_id", ""),
            "source_group_id": data.get("source_group_id", ""),
            "call_chain": data.get("call_chain", []),
            
            # 归属关系
            "parent_task_id": "",  # TODO: 根据parent_qa_id查找
            "parent_qa_id": data.get("parent_qa_id", ""),
            
            # LLM处理结果（如果有）
            "llm_summary": data.get("llm_summary", ""),
            "llm_quality_score": data.get("llm_quality_score", 0.0),
            "llm_suggested_category": data.get("llm_suggested_category", ""),
            "llm_is_valid": data.get("llm_is_valid", True),
            
            # 优先级与分类
            "priority": data.get("priority", 3),
            "category": data.get("llm_suggested_category", ""),
            "tags": [],
            
            # 状态管理
            "status": QATaskStatus.PENDING.value,
            "stage": QATaskStage.PENDING.value,
            
            # 分配信息（MVP版本暂不分配）
            "assigned_to": "",
            "assigned_at": "",
            "expire_at": expire_at,
            
            # 时间戳
            "created_at": get_format_time(),
            "updated_at": get_format_time(),
        }
        
        # 持久化到ES
        if self.es_client:
            try:
                await self._save_task_to_es(task_data)
            except Exception as e:
                logger.error(f"Failed to save task to ES: {e}")
                # ES保存失败不阻断流程
        
        logger.debug(f"Created task: {task_id} for QA: {data.get('qa_id')}")
        return task_data
    
    async def _save_task_to_es(self, task_data: dict):
        """保存任务到ES"""
        index_name = f"{self.app_name}_qa_task"
        
        await self.es_client.index(
            index_name,
            doc_id=task_data["task_id"],
            body=task_data
        )
    
    async def on_after_process(self, message: MQMessage, result: Optional[dict]):
        """处理后记录日志"""
        if result:
            logger.info(
                f"Task dispatched: task_id={result.get('task_id')}, "
                f"priority={result.get('priority')}, "
                f"source_type={result.get('source_type')}"
            )
    
    def get_stats(self) -> dict:
        """获取分配器统计信息"""
        base_stats = self.stats
        base_stats.update({
            "dedup_cache_size": len(self._qa_hash_cache),
            "skip_llm_processor": self.skip_llm_processor,
        })
        return base_stats


class SimplifiedTaskDispatcher:
    """
    简化版任务分配器
    
    不启动后台消费，提供手动处理方法，适合API调用场景
    """
    
    def __init__(self, mq: BaseMQ, es_client = None):
        self.mq = mq
        self.es_client = es_client
        self.app_name = Config.get_app_name()
        self.task_config = Config.get_qa_task_config()
    
    async def dispatch_raw_message(self, raw_data: dict) -> dict:
        """
        直接将原始QA数据转为任务
        
        Args:
            raw_data: RawQAMessage格式的数据
            
        Returns:
            创建的任务数据
        """
        task_id = generate_uuid()
        expire_hours = self.task_config.get("expire_hours", 24)
        expire_at = (datetime.now() + timedelta(hours=expire_hours)).strftime("%Y-%m-%d %H:%M:%S")
        
        task_data = {
            "task_id": task_id,
            "qa_id": raw_data.get("qa_id", ""),
            "batch_id": raw_data.get("batch_id", ""),
            "question": raw_data.get("question", ""),
            "answer": raw_data.get("answer", ""),
            "qa_hash": raw_data.get("qa_hash", ""),
            "source_type": raw_data.get("source_type", ""),
            "source_trace_id": raw_data.get("source_trace_id", ""),
            "source_node_id": raw_data.get("source_node_id", ""),
            "source_group_id": raw_data.get("source_group_id", ""),
            "call_chain": raw_data.get("call_chain", []),
            "parent_task_id": "",
            "parent_qa_id": raw_data.get("parent_qa_id", ""),
            "priority": raw_data.get("priority", 3),
            "category": "",
            "tags": [],
            "status": QATaskStatus.PENDING.value,
            "stage": QATaskStage.PENDING.value,
            "assigned_to": "",
            "assigned_at": "",
            "expire_at": expire_at,
            "created_at": get_format_time(),
            "updated_at": get_format_time(),
        }
        
        # 发布到pending队列
        await self.mq.publish(MQTopic.PENDING.value, task_data, priority=task_data["priority"])
        
        # 保存到ES
        if self.es_client:
            try:
                await self.es_client.index(
                    f"{self.app_name}_qa_task",
                    doc_id=task_id,
                    body=task_data
                )
            except Exception as e:
                logger.error(f"Failed to save task to ES: {e}")
        
        return task_data

