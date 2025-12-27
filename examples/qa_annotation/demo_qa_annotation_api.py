# -*- encoding: utf-8 -*-
"""
QA标注平台 - MVP Demo

演示如何启动QA标注平台API服务

使用方法:
    # 启动HTTP服务
    python examples/qa_annotation/demo_qa_annotation_api.py
    
    # 运行演示流程
    python examples/qa_annotation/demo_qa_annotation_api.py demo

前置条件:
    1. 配置好ES连接
    2. 已经有一些trace/node数据
"""

import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import FastAPI
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_qa_platform(app: FastAPI, config_path: str = None):
    """初始化QA标注平台"""
    from oxygent.config import Config
    from oxygent.db_factory import DBFactory
    
    if config_path:
        Config.init(config_path)
    else:
        Config.init()
    
    db_factory = DBFactory()
    es_config = Config.get_es_config()
    
    if es_config:
        from oxygent.databases.db_es.jes_es import JesEs
        es_client = db_factory.get_instance(
            JesEs, es_config["hosts"], es_config.get("user"), es_config.get("password")
        )
    else:
        from oxygent.databases.db_es.local_es import LocalEs
        es_client = db_factory.get_instance(LocalEs)
    
    from oxygent.qa_annotation import set_qa_clients, qa_router
    set_qa_clients(es_client)
    app.include_router(qa_router)
    
    from oxygent.qa_annotation.init_es import init_qa_indices
    await init_qa_indices(es_client)
    
    return es_client


def create_app():
    """创建FastAPI应用"""
    app = FastAPI(title="QA Annotation Platform", version="0.1.0")
    
    @app.on_event("startup")
    async def startup():
        await init_qa_platform(app)
        logger.info("QA Annotation Platform started!")
    
    @app.get("/")
    async def root():
        return {
            "message": "QA Annotation Platform MVP",
            "docs": "/docs",
            "api_prefix": "/api/qa",
            "core_apis": {
                "提取预览": "POST /api/qa/extract/preview",
                "执行提取": "POST /api/qa/extract/execute",
                "任务树形列表": "GET /api/qa/tasks/tree",
                "提交标注": "POST /api/qa/annotations/submit",
                "审核标注": "POST /api/qa/annotations/review",
            }
        }
    
    return app


async def run_demo():
    """运行演示流程"""
    from oxygent.config import Config
    from oxygent.db_factory import DBFactory
    
    Config.init()
    db_factory = DBFactory()
    es_config = Config.get_es_config()
    
    if es_config:
        from oxygent.databases.db_es.jes_es import JesEs
        es_client = db_factory.get_instance(
            JesEs, es_config["hosts"], es_config.get("user"), es_config.get("password")
        )
    else:
        from oxygent.databases.db_es.local_es import LocalEs
        es_client = db_factory.get_instance(LocalEs)
    
    from oxygent.qa_annotation.init_es import init_qa_indices
    from oxygent.qa_annotation.services import QAExtractionService, TaskService
    
    await init_qa_indices(es_client)
    
    # 1. 提取QA
    end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start_time = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"\n提取时间范围: {start_time} ~ {end_time}")
    
    extraction_service = QAExtractionService(es_client)
    preview = await extraction_service.preview(start_time, end_time)
    print(f"预览: trace={preview.get('trace_count')}, node={preview.get('node_count')}")
    
    result = await extraction_service.extract_and_save(start_time, end_time, limit=50)
    print(f"提取完成: e2e={result.get('e2e_count')}, sub={result.get('sub_task_count')}")
    
    # 2. 查询任务
    task_service = TaskService(es_client)
    stats = await task_service.get_stats()
    print(f"\n任务统计: total={stats.get('total')}, root={stats.get('root_count')}")
    
    tree = await task_service.list_root_tasks_with_tree(page=1, page_size=3)
    for task in tree.get('tasks', []):
        print(f"  E2E: {task.get('task_id')[:8]}... 子任务数: {task.get('children_count')}")
    
    print("\n演示完成！")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        asyncio.run(run_demo())
    else:
        app = create_app()
        uvicorn.run(app, host="0.0.0.0", port=8099)
