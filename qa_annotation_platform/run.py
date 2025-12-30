#!/usr/bin/env python3
"""
QA标注平台启动脚本

简单直接运行
"""
import os
import sys

# 先添加项目根目录（关键！）
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import uvicorn


if __name__ == "__main__":
    # 从配置文件读取端口配置
    import os
    port = int(os.getenv("QA_PORT", "8001"))
    host = os.getenv("QA_HOST", "127.0.0.1")
    
    uvicorn.run(
        "qa_annotation_platform.server.main:app",
        host=host,
        port=port,
        reload=False
    )
