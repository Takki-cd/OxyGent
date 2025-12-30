"""
QA标注平台主入口

独立FastAPI服务，端口8001
"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse

# 相对导入（因为run.py已经添加了路径）
from .config import get_app_config
from .api import deposit_router, tasks_router, stats_router
from .services.es_service import init_es_service


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("QA标注平台服务启动中...")
    
    try:
        # 初始化ES索引
        await init_es_service()
        logger.info("ES索引初始化完成")
    except Exception as e:
        logger.error(f"ES初始化失败: {e}")
        # 继续启动，允许ES暂时不可用
    
    yield
    
    # 关闭时清理
    logger.info("QA标注平台服务关闭")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    config = get_app_config()
    
    app = FastAPI(
        title="QA标注平台API",
        description="""
## 核心功能

- **注入QA数据**: `POST /api/v1/deposit` - 外部Agent调用此接口注入QA数据
- **任务管理**: `GET/POST /api/v1/tasks` - 获取和更新任务
- **统计分析**: `GET /api/v1/stats` - 获取统计信息

## 使用方式

```python
import requests

# 注入根节点（端到端QA）
requests.post("http://localhost:8001/api/v1/deposit", json={
    "source_trace_id": "abc123",
    "source_group_id": "session_001",
    "question": "用户输入",
    "answer": "Agent输出",
    "is_root": True,
    "priority": 0,
    "caller": "user",
    "callee": "my_agent"
})

# 注入子节点（自动串联到根节点）
requests.post("http://localhost:8001/api/v1/deposit", json={
    "source_trace_id": "abc123",
    "question": "检索查询",
    "answer": "检索结果",
    "parent_qa_id": "qa_xxx",  # 指向根节点
    "priority": 2,
    "source_type": "agent_llm"
})
```
        """,
        version="1.0.0",
        lifespan=lifespan
    )
    
    # CORS配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins if config.cors_origins != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册路由
    app.include_router(deposit_router)
    app.include_router(tasks_router)
    app.include_router(stats_router)
    
    # 健康检查
    @app.get("/health")
    async def health():
        return {"status": "ok"}
    
    # 前端页面路由
    @app.get("/")
    async def root():
        """Redirect to web interface"""
        return RedirectResponse(url="./web/index.html")
    
    @app.get("/web/index.html")
    async def web_index():
        """Serve the main web page"""
        web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
        return FileResponse(os.path.join(web_dir, "index.html"))
    
    @app.get("/web/{path:path}")
    async def serve_static(path: str):
        """Serve static files from web directory"""
        web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
        file_path = os.path.join(web_dir, path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return RedirectResponse(url="./web/index.html")
    
    return app


# 创建应用实例
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    config = get_app_config()
    uvicorn.run(
        "qa_annotation_platform.server.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug
    )
