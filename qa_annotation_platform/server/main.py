"""
QA Annotation Platform Main Entry

Independent FastAPI service, port 8001
"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse

# Relative imports (since run.py has already added the path)
from .config import get_app_config
from .api import deposit_router, tasks_router, stats_router
from .services.es_service import init_es_service


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    # Initialize on startup
    logger.info("QA Annotation Platform service starting...")
    
    try:
        # Initialize ES index
        await init_es_service()
        logger.info("ES index initialization completed")
    except Exception as e:
        logger.error(f"ES initialization failed: {e}")
        # Continue startup, allow ES to be temporarily unavailable
    
    yield
    
    # Cleanup on shutdown
    logger.info("QA Annotation Platform service shutting down")


def create_app() -> FastAPI:
    """Create FastAPI application"""
    config = get_app_config()
    
    app = FastAPI(
        title="QA Annotation Platform API",
        description="""
## Core Features

- **Deposit QA Data**: `POST /api/v1/deposit` - External agents call this API to deposit QA data
- **Task Management**: `GET/POST /api/v1/tasks` - Get and update tasks
- **Statistics**: `GET /api/v1/stats` - Get statistics

## Usage

```python
import requests

# Deposit root node (End-to-End QA)
requests.post("http://localhost:8001/api/v1/deposit", json={
    "source_trace_id": "abc123",
    "source_group_id": "session_001",
    "question": "User input",
    "answer": "Agent output",
    "is_root": True,
    "priority": 0,
    "caller": "user",
    "callee": "my_agent"
})

# Deposit child node (automatically linked to root node)
requests.post("http://localhost:8001/api/v1/deposit", json={
    "source_trace_id": "abc123",
    "question": "Search query",
    "answer": "Search result",
    "parent_qa_id": "qa_xxx",  # Point to root node
    "priority": 2,
    "source_type": "agent_llm"
})
```
        """,
        version="1.0.0",
        lifespan=lifespan
    )
    
    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins if config.cors_origins != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Register routes
    app.include_router(deposit_router)
    app.include_router(tasks_router)
    app.include_router(stats_router)
    
    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok"}
    
    # Frontend page route
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


# Create application instance
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
