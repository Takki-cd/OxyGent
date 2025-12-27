# -*- encoding: utf-8 -*-
"""
QA标注平台 - ES索引初始化脚本

用于创建QA标注平台所需的ES索引
可通过命令行运行或在应用启动时调用
"""

import asyncio
import logging
from typing import Optional

from oxygent.config import Config
from oxygent.db_factory import DBFactory
from oxygent.qa_annotation.schemas.task import QA_TASK_MAPPING
from oxygent.qa_annotation.schemas.annotation import QA_ANNOTATION_MAPPING

logger = logging.getLogger(__name__)


async def init_qa_indices(es_client=None, force_recreate: bool = False) -> dict:
    """
    初始化QA标注平台ES索引
    
    Args:
        es_client: ES客户端（可选，不传则自动创建）
        force_recreate: 是否强制重建索引（会删除现有数据）
        
    Returns:
        创建结果
    """
    # 获取ES客户端
    if es_client is None:
        db_factory = DBFactory()
        es_config = Config.get_es_config()
        if es_config:
            from oxygent.databases.db_es.jes_es import JesEs
            es_client = db_factory.get_instance(
                JesEs,
                es_config["hosts"],
                es_config.get("user"),
                es_config.get("password"),
            )
        else:
            from oxygent.databases.db_es.local_es import LocalEs
            es_client = db_factory.get_instance(LocalEs)
    
    app_name = Config.get_app_name()
    results = {}
    
    indices = [
        (f"{app_name}_qa_task", QA_TASK_MAPPING),
        (f"{app_name}_qa_annotation", QA_ANNOTATION_MAPPING),
    ]
    
    for index_name, mapping in indices:
        try:
            exists = await es_client.index_exists(index_name)
            
            if exists:
                if force_recreate:
                    await es_client.delete_index(index_name)
                    await es_client.create_index(index_name, mapping)
                    results[index_name] = "recreated"
                    logger.info(f"Index {index_name} recreated")
                else:
                    results[index_name] = "already_exists"
                    logger.info(f"Index {index_name} already exists, skipped")
            else:
                await es_client.create_index(index_name, mapping)
                results[index_name] = "created"
                logger.info(f"Index {index_name} created")
                
        except Exception as e:
            results[index_name] = f"error: {str(e)}"
            logger.error(f"Failed to create index {index_name}: {e}")
    
    return results


def init_qa_indices_sync(es_client=None, force_recreate: bool = False) -> dict:
    """同步版本的索引初始化"""
    return asyncio.run(init_qa_indices(es_client, force_recreate))


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Initialize QA Annotation ES Indices")
    parser.add_argument("--config", "-c", help="Config file path", default=None)
    parser.add_argument("--force", "-f", action="store_true", help="Force recreate indices")
    args = parser.parse_args()
    
    # 加载配置
    if args.config:
        Config.init(args.config)
    else:
        Config.init()
    
    # 执行初始化
    logging.basicConfig(level=logging.INFO)
    results = init_qa_indices_sync(force_recreate=args.force)
    
    print("\n" + "="*50)
    print("QA Annotation ES Indices Initialization Results:")
    print("="*50)
    for index, status in results.items():
        print(f"  {index}: {status}")
    print("="*50)

