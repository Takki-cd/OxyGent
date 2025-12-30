"""
QA标注平台

独立QA标注系统，支持用户自定义注入QA数据。

主要功能：
1. 通过API注入QA数据（支持单条和批量）
2. 支持链式关系（通过parent_qa_id关联）
3. 支持优先级过滤
4. 支持任意数据格式
5. 提供标注进度统计
6. 复用Oxygent的ES客户端

快速开始：
```bash
# 启动服务
python run.py

# 运行演示
python demo.py
```

前端访问：http://localhost:8001/web/index.html
API文档：http://localhost:8001/docs
"""

__version__ = "1.0.0"
