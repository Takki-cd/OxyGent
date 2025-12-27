# -*- encoding: utf-8 -*-
"""
QA标注平台 - MQ工厂类

提供消息队列实例的创建和管理（单例模式）
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MQFactory:
    """
    消息队列工厂类（单例模式）
    
    使用示例:
        # 异步获取MQ实例
        mq = await MQFactory().get_instance()
        await mq.publish("raw", {"question": "...", "answer": "..."})
        
        # 或使用上下文管理器
        async with await MQFactory().get_instance() as mq:
            await mq.publish("raw", data)
    """
    
    _factory_instance: Optional["MQFactory"] = None
    _mq_client = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._factory_instance is None:
            cls._factory_instance = super().__new__(cls)
        return cls._factory_instance
    
    async def get_instance(self, mq_type: str = None, **kwargs):
        """
        获取MQ实例（异步初始化）
        
        Args:
            mq_type: MQ类型（redis/rabbitmq/kafka），默认从配置读取
            **kwargs: MQ配置参数，会覆盖配置文件中的值
            
        Returns:
            BaseMQ实例
        """
        if self._mq_client is not None and self._initialized:
            return self._mq_client
        
        from oxygent.config import Config
        
        if mq_type is None:
            mq_type = Config.get_qa_mq_type()
        
        mq_config = Config.get_qa_mq_config().get(mq_type, {}).copy()
        mq_config.update(kwargs)
        
        if mq_type == "redis":
            from oxygent.qa_annotation.mq.redis_stream_mq import RedisStreamMQ
            
            # 从配置获取Redis连接信息
            redis_config = Config.get_redis_config()
            if redis_config:
                # 合并redis配置和mq配置
                full_config = {
                    "stream_prefix": mq_config.get("stream_prefix", "qa"),
                    "max_len": mq_config.get("max_len", 100000),
                    "block_timeout_ms": mq_config.get("block_timeout_ms", 5000),
                    "consumer_group": mq_config.get("consumer_group", "qa_processor"),
                }
                # Redis连接参数
                if "host" in redis_config:
                    full_config["host"] = redis_config["host"]
                if "port" in redis_config:
                    full_config["port"] = redis_config["port"]
                if "password" in redis_config:
                    full_config["password"] = redis_config["password"]
                if "db" in redis_config:
                    full_config["db"] = redis_config["db"]
                    
                self._mq_client = RedisStreamMQ(**full_config)
            else:
                self._mq_client = RedisStreamMQ(**mq_config)
                
        elif mq_type == "rabbitmq":
            # TODO: 第二期实现
            raise NotImplementedError("RabbitMQ support is planned for phase 2")
            
        elif mq_type == "kafka":
            # TODO: 第三期实现
            raise NotImplementedError("Kafka support is planned for phase 3")
            
        else:
            raise ValueError(f"Unsupported MQ type: {mq_type}")
        
        # 建立连接
        await self._mq_client.connect()
        self._initialized = True
        
        logger.info(f"Initialized MQ client: {mq_type}")
        return self._mq_client
    
    def get_instance_sync(self):
        """
        同步获取已初始化的实例（用于非异步上下文）
        
        注意：必须先调用 get_instance() 完成初始化
        
        Returns:
            BaseMQ实例或None
        """
        if not self._initialized:
            return None
        return self._mq_client
    
    async def close(self):
        """关闭MQ连接"""
        if self._mq_client and self._initialized:
            await self._mq_client.disconnect()
            self._initialized = False
            self._mq_client = None
            logger.info("MQ client closed")
    
    def reset(self):
        """重置MQ实例（用于测试）"""
        self._mq_client = None
        self._initialized = False
    
    @classmethod
    def reset_factory(cls):
        """完全重置工厂（用于测试）"""
        if cls._factory_instance:
            cls._factory_instance._mq_client = None
            cls._factory_instance._initialized = False
        cls._factory_instance = None


# 便捷函数
async def get_mq_client(mq_type: str = None, **kwargs):
    """
    获取MQ客户端的便捷函数
    
    Args:
        mq_type: MQ类型
        **kwargs: 额外配置
        
    Returns:
        BaseMQ实例
    """
    return await MQFactory().get_instance(mq_type, **kwargs)

