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


if __name__ == "__main__":
    # Read port configuration from config file
    import os
    port = int(os.getenv("QA_PORT", "8001"))
    host = os.getenv("QA_HOST", "127.0.0.1")
    
    uvicorn.run(
        "qa_annotation_platform.server.main:app",
        host=host,
        port=port,
        reload=False
    )
