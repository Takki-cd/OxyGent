# -*- encoding: utf-8 -*-
"""
QA标注平台 - 实时Hook采集器

在Agent节点执行完成后自动采集QA数据并发布到MQ
"""

import logging
from typing import Optional

from oxygent.config import Config
from oxygent.schemas import OxyRequest, OxyResponse, OxyState
from oxygent.utils.common_utils import generate_uuid, get_format_time, get_md5

logger = logging.getLogger(__name__)


class QACollectorHook:
    """
    QA数据实时采集Hook
    
    在每个Agent节点执行完成后触发，将QA数据发布到消息队列。
    通过配置可控制是否启用，以及过滤规则。
    
    Usage:
        # 在base_agent.py的_post_save_data中调用
        if Config.is_qa_realtime_hook_enabled():
            hook = await QACollectorHook.get_instance()
            await hook.on_node_completed(oxy_request, oxy_response)
    """
    
    _instance: Optional["QACollectorHook"] = None
    
    @classmethod
    async def get_instance(cls) -> "QACollectorHook":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance._init()
        return cls._instance
    
    @classmethod
    def reset(cls):
        """重置实例（用于测试）"""
        cls._instance = None
    
    def __init__(self):
        self.config = Config.get_qa_collector_config()
        self.mq = None
        self.redis = None  # 用于缓存trace映射
        self._initialized = False
    
    async def _init(self):
        """异步初始化"""
        if self._initialized:
            return
            
        # 获取MQ客户端
        from oxygent.qa_annotation.mq_factory import MQFactory
        self.mq = await MQFactory().get_instance()
        
        # TODO: 获取Redis用于缓存trace映射（复用现有连接）
        # 当前版本简化处理，不使用缓存
        
        self._initialized = True
        logger.info("QACollectorHook initialized")
    
    async def on_node_completed(
        self,
        oxy_request: OxyRequest,
        oxy_response: OxyResponse
    ) -> Optional[str]:
        """
        节点执行完成时触发
        
        Args:
            oxy_request: 执行请求
            oxy_response: 执行响应
            
        Returns:
            发布的消息ID，如果未采集则返回None
        """
        # 1. 检查是否需要采集
        if not self._should_collect(oxy_request, oxy_response):
            return None
        
        # 2. 构建QA数据
        qa_data = self._build_qa_data(oxy_request, oxy_response)
        
        # 3. 处理归属关系
        await self._handle_parent_relationship(qa_data)
        
        # 4. 发布到消息队列
        try:
            message_id = await self.mq.publish(
                topic="raw",
                data=qa_data,
                priority=qa_data["priority"]
            )
            logger.debug(f"Published QA to MQ: {message_id}, qa_id={qa_data['qa_id']}")
            return message_id
        except Exception as e:
            logger.error(f"Failed to publish QA: {e}")
            # Hook失败不应抛出异常影响主流程
            return None
    
    def _should_collect(
        self,
        oxy_request: OxyRequest,
        oxy_response: OxyResponse
    ) -> bool:
        """
        判断是否需要采集该QA对
        
        过滤规则:
        1. 状态必须是成功(COMPLETED)
        2. 排除指定的callee名称
        3. 排除指定的callee类型
        4. question长度检查
        5. answer长度检查
        """
        # 1. 状态必须是成功
        if oxy_response.state != OxyState.COMPLETED:
            return False
        
        # 2. 排除指定的callee
        exclude_callees = self.config.get("exclude_callees", ["retrieve_tools", "default_llm"])
        if oxy_request.callee in exclude_callees:
            return False
        
        # 3. 排除指定类型
        exclude_types = self.config.get("exclude_callee_types", ["llm"])
        if oxy_request.callee_category in exclude_types:
            return False
        
        # 4. 必须有有效的query
        question = oxy_request.arguments.get("query", "")
        min_q_len = self.config.get("min_question_length", 2)
        if len(str(question)) < min_q_len:
            return False
        
        # 5. 答案长度检查
        answer = str(oxy_response.output) if oxy_response.output else ""
        min_a_len = self.config.get("min_answer_length", 10)
        max_a_len = self.config.get("max_answer_length", 50000)
        if len(answer) < min_a_len or len(answer) > max_a_len:
            return False
        
        return True
    
    def _build_qa_data(
        self,
        oxy_request: OxyRequest,
        oxy_response: OxyResponse
    ) -> dict:
        """
        构建QA数据结构
        
        Returns:
            符合RawQAMessage结构的字典
        """
        question = str(oxy_request.arguments.get("query", ""))
        answer = str(oxy_response.output) if oxy_response.output else ""
        qa_hash = get_md5(f"{question}:{answer}")
        
        priority = self._calculate_priority(oxy_request)
        source_type = self._get_source_type(oxy_request)
        
        return {
            # 标识
            "qa_id": generate_uuid(),
            "batch_id": "",  # 实时采集没有batch_id
            
            # QA内容
            "question": question,
            "answer": answer,
            "qa_hash": qa_hash,
            
            # 来源追溯
            "source_type": source_type,
            "source_node_id": oxy_request.node_id,
            "source_trace_id": oxy_request.current_trace_id,
            "source_group_id": oxy_request.group_id,
            
            # 调用信息
            "caller": oxy_request.caller,
            "callee": oxy_request.callee,
            "caller_category": oxy_request.caller_category,
            "callee_category": oxy_request.callee_category,
            "call_chain": oxy_request.call_stack,
            
            # 归属关系（后续处理）
            "parent_qa_id": "",
            
            # 优先级
            "priority": priority,
            
            # 时间
            "created_at": get_format_time(),
        }
    
    def _calculate_priority(self, oxy_request: OxyRequest) -> int:
        """
        计算优先级
        
        P0: 端到端（用户→主Agent，call_stack长度为2）
        P1: 用户直接调用子Agent
        P2: Agent→Agent
        P3: Agent→Tool
        """
        weights = Config.get_qa_task_config().get("priority_weights", {
            "e2e": 0, "user_agent": 1, "agent_agent": 2, "agent_tool": 3
        })
        
        caller_category = oxy_request.caller_category
        callee_category = oxy_request.callee_category
        call_stack_len = len(oxy_request.call_stack)
        
        # 用户发起的调用
        if caller_category == "user":
            if callee_category == "agent" and call_stack_len == 2:
                return weights.get("e2e", 0)  # P0
            return weights.get("user_agent", 1)  # P1
        
        # Agent调用Agent
        if caller_category == "agent" and callee_category == "agent":
            return weights.get("agent_agent", 2)  # P2
        
        # Agent调用Tool
        return weights.get("agent_tool", 3)  # P3
    
    def _get_source_type(self, oxy_request: OxyRequest) -> str:
        """获取数据源类型标识"""
        caller_category = oxy_request.caller_category
        callee_category = oxy_request.callee_category
        call_stack_len = len(oxy_request.call_stack)
        
        if caller_category == "user":
            if callee_category == "agent" and call_stack_len == 2:
                return "e2e"
            return "user_agent"
        elif callee_category == "agent":
            return "agent_agent"
        return "agent_tool"
    
    async def _handle_parent_relationship(self, qa_data: dict):
        """
        处理归属关系
        
        1. 如果是端到端QA，缓存trace_id → qa_id的映射
        2. 如果是子QA，尝试从缓存获取parent_qa_id
        
        注意：当前版本简化处理，归属关系在LLM处理阶段或批量导入时补全
        """
        trace_id = qa_data["source_trace_id"]
        
        if qa_data["source_type"] == "e2e":
            # 端到端任务本身没有parent
            qa_data["parent_qa_id"] = ""
            
            # TODO: 缓存映射关系供子任务使用
            # if self.redis:
            #     cache_key = f"qa:trace_parent:{trace_id}"
            #     cache_ttl = self.config.get("dedup_cache_ttl_seconds", 86400)
            #     await self.redis.setex(cache_key, cache_ttl, qa_data["qa_id"])
        else:
            # TODO: 尝试从缓存获取parent
            # 当前版本：parent_qa_id留空，在后续处理中补全
            qa_data["parent_qa_id"] = ""


async def publish_qa_to_mq(oxy_request: OxyRequest, oxy_response: OxyResponse) -> Optional[str]:
    """
    便捷函数：发布QA数据到MQ
    
    可以在Agent的_post_save_data中调用
    
    Args:
        oxy_request: 执行请求
        oxy_response: 执行响应
        
    Returns:
        消息ID或None
    """
    if not Config.is_qa_realtime_hook_enabled():
        return None
        
    try:
        hook = await QACollectorHook.get_instance()
        return await hook.on_node_completed(oxy_request, oxy_response)
    except Exception as e:
        logger.warning(f"QA annotation hook failed: {e}")
        return None

