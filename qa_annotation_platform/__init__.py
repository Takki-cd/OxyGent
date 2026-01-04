"""
QA Annotation Platform

Independent QA annotation system, supports users to deposit QA data via API.

Main Features:
1. Deposit QA data via API (support single and batch)
2. Support chain relationships (linked via parent_qa_id)
3. Support priority filtering
4. Support arbitrary data format
5. Provide annotation progress statistics
6. Reuse Oxygent's ES client

Quick Start:
```bash
# Start service
python run.py

# Run demo
python demo.py
```

Frontend: http://localhost:8001/web/index.html
API Docs: http://localhost:8001/docs
"""

__version__ = "1.0.0"
