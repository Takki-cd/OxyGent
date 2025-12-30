# QA标注平台

独立QA标注系统，复用Oxygent的ES客户端。

## 启动服务

```bash
cd qa_annotation_platform
python run.py
```

服务将在 `http://localhost:8001` 启动

- 前端: http://localhost:8001/web/index.html
- API文档: http://localhost:8001/docs

## 配置

标注平台使用独立配置，通过环境变量设置：

| 环境变量 | 说明 | 默认值 |
|---------|------|-------|
| `QA_HOST` | 服务地址 | 0.0.0.0 |
| `QA_PORT` | 服务端口 | 8001 |
| `QA_ES_HOSTS` | ES地址（逗号分隔） | http://localhost:9200 |
| `QA_ES_USER` | ES用户名 | - |
| `QA_ES_PASSWORD` | ES密码 | - |
| `QA_ES_INDEX_PREFIX` | ES索引前缀 | app_qa |

## 数据模型

```python
{
  "qa_id": "唯一ID",
  "task_id": "任务ID",
  
  # QA内容
  "question": "问题",
  "answer": "答案",
  "qa_hash": "去重hash",
  
  # 来源追溯
  "source_type": "e2e/agent/tool/llm",     # 来源类型
  "source_trace_id": "原始trace_id",         # 关联Oxygent的trace
  "source_node_id": "节点ID",
  "source_group_id": "group_id",
  
  # 层级关系
  "is_root": True/False,                    # 是否为根节点（端到端）
  "parent_qa_id": "父QA ID",                # 子节点指向父节点
  "depth": 0,                               # 深度：0=端到端, 1+=子节点
  
  # 调用链信息
  "caller": "调用者",
  "callee": "被调用者",
  
  # 优先级
  "priority": 0-4,  # 0=P0端到端, 1=P1子Agent, 2=P2 LLM, 3=P3 Tool, 4=P4其他
  
  # 状态
  "status": "pending/annotated/approved/rejected"
}
```

## API接口

### 注入接口

| 方法 | 路径 | 说明 |
|-----|-----|-----|
| POST | `/api/v1/deposit` | 注入单条QA（核心接口） |
| POST | `/api/v1/deposit/root` | 快捷接口：注入根节点 |
| POST | `/api/v1/deposit/child/{parent_qa_id}` | 快捷接口：注入子节点 |
| POST | `/api/v1/deposit/batch` | 批量注入QA |

### 任务管理接口

| 方法 | 路径 | 说明 |
|-----|-----|-----|
| GET | `/api/v1/tasks` | 获取任务列表（支持过滤分页） |
| GET | `/api/v1/tasks/{id}` | 获取任务详情 |
| GET | `/api/v1/tasks/{id}/children` | 获取子节点列表 |
| PUT | `/api/v1/tasks/{id}/annotate` | 更新标注 |
| POST | `/api/v1/tasks/{id}/approve` | 审核通过 |
| POST | `/api/v1/tasks/{id}/reject` | 审核拒绝 |

### 统计接口

| 方法 | 路径 | 说明 |
|-----|-----|-----|
| GET | `/api/v1/stats` | 获取统计信息 |
| GET | `/api/v1/stats/low-score` | 获取低分任务列表 |

## 使用示例

### 1. 注入根节点（端到端QA）

```python
# 方式1：使用 parent_qa_id 字段
requests.post("http://localhost:8001/api/v1/deposit", json={
    "source_trace_id": "trace_001",
    "source_group_id": "session_001",
    "question": "你好",
    "answer": "你好！我是AI助手。",
    "is_root": True,
    "priority": 0,
    "caller": "user",
    "callee": "chat_agent"
})

# 方式2：使用快捷接口
requests.post("http://localhost:8001/api/v1/deposit/root", json={
    "source_trace_id": "trace_001",
    "question": "你好",
    "answer": "你好！我是AI助手。",
    "caller": "user",
    "callee": "chat_agent"
})
```

### 2. 注入子节点（LLM/Tool调用）

```python
# 方式1：使用 parent_qa_id 字段
requests.post("http://localhost:8001/api/v1/deposit", json={
    "source_trace_id": "trace_001",
    "question": "Prompt: 你好",
    "answer": "你好！我是AI助手。",
    "parent_qa_id": "qa_xxx",  # 根节点返回的qa_id
    "source_type": "agent_llm",
    "priority": 2,
    "caller": "chat_agent",
    "callee": "gpt-3.5-turbo"
})

# 方式2：使用快捷接口
requests.post("http://localhost:8001/api/v1/deposit/child/qa_xxx", json={
    "source_trace_id": "trace_001",
    "question": "Prompt: 你好",
    "answer": "你好！我是AI助手。",
    "source_type": "agent_llm",
    "priority": 2,
    "caller": "chat_agent",
    "callee": "gpt-3.5-turbo"
})
```

### 3. 批量注入

```python
requests.post("http://localhost:8001/api/v1/deposit/batch", json={
    "items": [
        {
            "source_trace_id": "trace_001",
            "question": "根节点问题",
            "answer": "根节点答案",
            "is_root": True,
            "priority": 0
        },
        {
            "source_trace_id": "trace_001",
            "question": "LLM问题",
            "answer": "LLM答案",
            "parent_qa_id": "qa_root_xxx",
            "source_type": "agent_llm",
            "priority": 2
        }
    ]
})
```

### 4. 获取任务列表

```python
requests.get("http://localhost:8001/api/v1/tasks", params={
    "qa_type": "e2e",           # 来源类型过滤
    "status": "pending",        # 状态过滤
    "priority": 0,              # 优先级过滤
    "search": "你好",           # 全文搜索
    "page": 1,
    "page_size": 20
})
```

### 5. 更新标注

```python
requests.put("http://localhost:8001/api/v1/tasks/qa_xxx/annotate", json={
    "status": "annotated",
    "annotation": {
        "content": "标注结果",
        "quality_score": 0.85,
        "comment": "回答正确"
    },
    "scores": {
        "overall_score": 0.85,
        "relevance": 0.9,
        "accuracy": 0.8
    }
})
```

## 运行演示

```bash
python demo.py
```
