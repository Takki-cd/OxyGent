# QA标注平台（简化版）

独立QA标注系统，复用Oxygent的ES客户端。

## 核心设计变更

**简化设计理念：**
- 删除parent_qa_id等层级关系，改用group_id/trace_id聚合
- 统一唯一ID（data_id），替代qa_id和task_id
- 使用caller/callee描述调用链信息
- 端到端固定为P0=0，其他按需设置
- 先关注P0，再显示关联子对

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
  "data_id": "唯一ID（替代qa_id和task_id）",
  
  # QA内容
  "question": "问题",
  "answer": "答案",
  "data_hash": "去重hash",
  
  # 来源追溯（三大核心字段）
  "source_trace_id": "原始trace_id（关联Oxygent的trace）",
  "source_request_id": "原始request_id",
  "source_group_id": "group_id（用于会话聚合）",
  
  # 调用链信息（caller/callee）
  "caller": "调用者（user/agent名称）",
  "callee": "被调用者（agent/tool/llm名称）",
  
  # 数据类型（用于标注时区分来源）
  "data_type": "e2e/agent/llm/tool/custom",
  
  # 优先级
  "priority": 0-4,  # 0=P0端到端（最高优先级），1-4为子节点
  
  # 分类与标签
  "category": "分类",
  "tags": ["标签1", "标签2"],
  
  # 状态
  "status": "pending/annotated/approved/rejected",
  
  # 标注结果
  "annotation": {...},
  "scores": {...},
  
  # 时间戳
  "created_at": "创建时间",
  "updated_at": "更新时间"
}
```

### 优先级定义

| 优先级 | 值 | 说明 |
|-------|-----|------|
| P0 | 0 | 端到端（用户->Agent，最高优先级） |
| P1 | 1 | 一级子节点 |
| P2 | 2 | 二级子节点（通常为LLM调用） |
| P3 | 3 | 三级子节点（通常为Tool调用） |
| P4 | 4 | 其他 |

### 调用链示例

| 场景 | caller | callee | data_type |
|-----|--------|--------|----------|
| 用户调用Agent | user | chat_agent | e2e |
| Agent调用LLM | chat_agent | gpt-3.5-turbo | llm |
| Agent调用Tool | chat_agent | weather_api | tool |

## API接口

### 注入接口

| 方法 | 路径 | 说明 |
|-----|-----|-----|
| POST | `/api/v1/deposit` | 注入单条数据（核心接口） |
| POST | `/api/v1/deposit/batch` | 批量注入数据 |

### 数据管理接口

| 方法 | 路径 | 说明 |
|-----|-----|-----|
| GET | `/api/v1/data` | 获取数据列表（支持过滤分页） |
| GET | `/api/v1/data/{data_id}` | 获取数据详情 |
| PUT | `/api/v1/data/{data_id}/annotate` | 更新标注 |
| GET | `/api/v1/data/trace/{trace_id}` | 根据trace_id获取关联数据 |
| GET | `/api/v1/data/group/{group_id}` | 根据group_id获取关联数据 |
| GET | `/api/v1/data/groups/summary` | 获取分组汇总 |
| POST | `/api/v1/data/{data_id}/approve` | 审核通过 |
| POST | `/api/v1/data/{data_id}/reject` | 审核拒绝 |

### 统计接口

| 方法 | 路径 | 说明 |
|-----|-----|-----|
| GET | `/api/v1/stats` | 获取统计信息 |
| GET | `/api/v1/stats/pending-p0` | 获取待标注的P0数据 |

## 使用示例

### 1. 注入端到端数据（P0）

```python
requests.post("http://localhost:8001/api/v1/deposit", json={
    "source_trace_id": "trace_001",
    "source_request_id": "req_001",
    "source_group_id": "session_001",
    "question": "你好",
    "answer": "你好！我是AI助手。",
    "caller": "user",
    "callee": "chat_agent",
    "data_type": "e2e",
    "priority": 0  # 端到端必须是P0
})
```

### 2. 注入子节点（LLM/Tool调用）

```python
# 注入LLM调用（P2）
requests.post("http://localhost:8001/api/v1/deposit", json={
    "source_trace_id": "trace_001",
    "source_request_id": "req_002",
    "source_group_id": "session_001",
    "question": "Prompt: 你好",
    "answer": "你好！我是AI助手。",
    "caller": "chat_agent",
    "callee": "gpt-3.5-turbo",
    "data_type": "llm",
    "priority": 2  # LLM调用
})

# 注入Tool调用（P3）
requests.post("http://localhost:8001/api/v1/deposit", json={
    "source_trace_id": "trace_001",
    "source_request_id": "req_003",
    "source_group_id": "session_001",
    "question": "调用天气API: 北京",
    "answer": '{"city": "北京", "temp": 25}',
    "caller": "chat_agent",
    "callee": "weather_api",
    "data_type": "tool",
    "priority": 3  # Tool调用
})
```

### 3. 批量注入

```python
requests.post("http://localhost:8001/api/v1/deposit/batch", json={
    "items": [
        {
            "source_trace_id": "trace_001",
            "source_request_id": "req_001",
            "question": "根节点问题",
            "answer": "根节点答案",
            "caller": "user",
            "callee": "chat_agent",
            "priority": 0  # 端到端
        },
        {
            "source_trace_id": "trace_001",
            "source_request_id": "req_002",
            "question": "LLM问题",
            "answer": "LLM答案",
            "caller": "chat_agent",
            "callee": "gpt-3.5-turbo",
            "data_type": "llm",
            "priority": 2
        },
        {
            "source_trace_id": "trace_001",
            "source_request_id": "req_003",
            "question": "Tool问题",
            "answer": "Tool答案",
            "caller": "chat_agent",
            "callee": "weather_api",
            "data_type": "tool",
            "priority": 3
        }
    ]
})
```

### 4. 获取数据列表

```python
# 获取所有数据
requests.get("http://localhost:8001/api/v1/data", params={
    "page": 1,
    "page_size": 20
})

# 只显示P0（端到端）
requests.get("http://localhost:8001/api/v1/data", params={
    "show_p0_only": True,
    "page": 1,
    "page_size": 20
})

# 按callee过滤
requests.get("http://localhost:8001/api/v1/data", params={
    "callee": "gpt-3.5-turbo",
    "page": 1,
    "page_size": 20
})

# 按group_id聚合查询
requests.get("http://localhost:8001/api/v1/data/group/session_001", params={
    "limit": 100
})
```

### 5. 根据trace_id获取关联数据

```python
# 获取某个trace下所有关联数据（按优先级排序）
requests.get("http://localhost:8001/api/v1/data/trace/trace_001")

# 返回格式：
# {
#   "source_trace_id": "trace_001",
#   "total": 3,
#   "items": [
#     {"data_id": "...", "priority": 0, "caller": "user", "callee": "agent", ...},  # P0
#     {"data_id": "...", "priority": 2, "caller": "agent", "callee": "llm", ...},   # P2
#     {"data_id": "...", "priority": 3, "caller": "agent", "callee": "tool", ...}    # P3
#   ]
# }
```

### 6. 获取分组汇总

```python
# 获取所有分组的汇总统计
requests.get("http://localhost:8001/api/v1/data/groups/summary", params={
    "page": 1,
    "page_size": 20
})

# 返回格式：
# {
#   "groups": [
#     {
#       "source_group_id": "session_001",
#       "data_count": 10,
#       "p0_count": 3,
#       "p0_pending": 1
#     },
#     ...
#   ],
#   "total": 5,
#   "page": 1,
#   "page_size": 20
# }
```

### 7. 更新标注

```python
requests.put("http://localhost:8001/api/v1/data/data_xxx/annotate", json={
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

## 与Oxygent集成

在Oxygent Agent中调用标注平台：

```python
from qa_annotation_platform.client import create_qa_depositor

# 创建同步注入器
depositor = create_qa_depositor("http://localhost:8001")

# 在Agent处理完成后调用
class MyAgent(BaseAgent):
    async def run(self, oxy_request, oxy_response):
        result = await self._run(oxy_request, oxy_response)
        
        # 注入端到端数据（P0）
        depositor.deposit_e2e(
            source_trace_id=oxy_request.current_trace_id,
            source_request_id=oxy_request.request_id,
            source_group_id=oxy_request.group_id,
            question=oxy_request.arguments.get("query", ""),
            answer=str(result),
            callee="my_agent"
        )
        
        return result
```
