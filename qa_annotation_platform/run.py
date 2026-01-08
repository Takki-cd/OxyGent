#!/usr/bin/env python3
"""
QA Annotation Platform Startup Script

Simple and direct execution
"""
import os
import sys

# First add project root directory (critical!)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import uvicorn

# Initialize Oxygent configuration (so LocalEs can find the correct cache_dir)
from oxygent.config import Config
Config.load_from_json(os.path.join(project_root, "config.json"))


if __name__ == "__main__":
    # Read port configuration from config file
    from qa_annotation_platform.server.config import get_app_config
    
    config = get_app_config()
    
    uvicorn.run(
        "qa_annotation_platform.server.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug
    )
