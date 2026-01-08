#!/usr/bin/env python3
"""
QA Annotation Platform Startup Script

Simple and direct execution
"""
import os
import sys
import uvicorn
from qa_annotation_platform.server.config import get_app_config

# First add project root directory (critical!)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


if __name__ == "__main__":    
    config = get_app_config()
    
    uvicorn.run(
        "qa_annotation_platform.server.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug
    )
