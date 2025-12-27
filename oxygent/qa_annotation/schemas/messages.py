# -*- encoding: utf-8 -*-
"""
QA标注平台 - 数据源类型和优先级定义

MVP版本简化：仅保留核心枚举定义，MQ消息结构在后续版本扩展
"""

from enum import Enum


class QASourceType(str, Enum):
    """QA数据源类型"""
    E2E = "e2e"                    # 端到端对话 (P0)
    USER_AGENT = "user_agent"      # 用户→Agent (P1)
    AGENT_AGENT = "agent_agent"    # Agent→Agent (P2)
    AGENT_TOOL = "agent_tool"      # Agent→Tool (P3)


class QAPriority(int, Enum):
    """QA优先级 (数值越小优先级越高)"""
    P0_E2E = 0           # 端到端对话
    P1_USER_AGENT = 1    # 用户直接调用Agent
    P2_AGENT_AGENT = 2   # Agent调用Agent
    P3_AGENT_TOOL = 3    # Agent调用Tool
