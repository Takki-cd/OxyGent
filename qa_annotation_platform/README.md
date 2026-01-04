# QA Annotation Platform

AI Agent data collection and QA annotation system using Oxygent's ES client.

## Quick Start

```bash
cd qa_annotation_platform
python run.py
# Service: http://localhost:8001
# Frontend: http://localhost:8001/web/index.html
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `QA_PORT` | Service port | 8001 |
| `QA_ES_HOSTS` | ES hosts | http://localhost:9200 |
| `QA_ES_INDEX_PREFIX` | ES index prefix | qa_annotation_platform |

## Data Model

### Request Fields

| Field | Required | Description |
|-------|----------|-------------|
| `source_trace_id` | Yes | Trace ID from Oxygent |
| `source_request_id` | Yes | Request ID from Oxygent |
| `question` | Yes | User query |
| `answer` | No | Agent response |
| `caller` | Yes | Caller name (user/agent) |
| `callee` | Yes | Callee name (agent/tool/LLM) |
| `priority` | No | 0-4 (default: 0=End-to-End) |
| `data_type` | No | e2e/agent/llm/tool/custom (auto-inferred) |
| `source_group_id` | No | Session group ID |

### Priority & Data Type

| Priority | Value | Typical Data Type |
|----------|-------|-------------------|
| P0 | 0 | e2e (End-to-End) |
| P1 | 1 | agent |
| P2 | 2 | llm |
| P3 | 3 | tool |
| P4 | 4 | custom |

Auto-inferred by callee name: `llm`/`gpt` → llm, `tool`/`api` → tool, `agent` → agent.

## API Endpoints

### Deposit

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/deposit` | Single record |
| POST | `/api/v1/deposit/batch` | Batch records |

### Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/data` | List with filters |
| GET | `/api/v1/data/{id}` | Get by ID |
| PUT | `/api/v1/data/{id}/annotate` | Submit annotation |
| GET | `/api/v1/data/trace/{trace_id}` | By trace |
| GET | `/api/v1/data/group/{group_id}` | By group |
| GET | `/api/v1/data/groups/summary` | Group stats |
| POST | `/api/v1/data/{id}/approve` | Approve |
| POST | `/api/v1/data/{id}/reject` | Reject |

### Stats

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/stats` | Overall statistics |
| GET | `/api/v1/stats/pending-p0` | Pending P0 data |
| GET | `/api/v1/stats/by-oxy-type` | By component |

## Usage Examples

### Deposit Data

```python
# End-to-End (P0)
requests.post("http://localhost:8001/api/v1/deposit", json={
    "source_trace_id": "trace_001",
    "source_request_id": "req_001",
    "question": "Hello",
    "answer": "Hi!",
    "caller": "user",
    "callee": "chat_agent",
    "priority": 0  # End-to-End
})

# LLM call (P2)
requests.post("http://localhost:8001/api/v1/deposit", json={
    "source_trace_id": "trace_001",
    "source_request_id": "req_002",
    "question": "LLM Prompt",
    "answer": "LLM Response",
    "caller": "chat_agent",
    "callee": "gpt-4",
    "priority": 2  # Auto-inferred as llm
})

# Batch
requests.post("http://localhost:8001/api/v1/deposit/batch", json={
    "items": [...]
})
```

### Query Data

```python
# List with pagination
requests.get("http://localhost:8001/api/v1/data", params={
    "page": 1, "page_size": 20
})

# Filters
requests.get("http://localhost:8001/api/v1/data", params={
    "show_p0_only": True,
    "status": "pending",
    "callee": "gpt-4",
    "search": "weather"
})

# By trace
requests.get("http://localhost:8001/api/v1/data/trace/trace_001")

# By group
requests.get("http://localhost:8001/api/v1/data/group/session_001")
```

### Annotate

```python
# Submit annotation
requests.put("http://localhost:8001/api/v1/data/id/annotate", json={
    "status": "annotated",
    "annotation": {"content": "...", "quality_score": 0.85},
    "scores": {"overall_score": 0.85}
})

# Approve/Reject
requests.post("http://localhost:8001/api/v1/data/id/approve")
requests.post("http://localhost:8001/api/v1/data/id/reject", json={
    "reject_reason": "Inaccurate"
})
```

### Statistics

```python
requests.get("http://localhost:8001/api/v1/stats")
# Returns: {total, pending, annotated, approved, rejected, 
#           by_priority, by_caller, by_callee, by_status}
```

## Integration

```python
from qa_annotation_platform.client import create_qa_depositor

depositor = create_qa_depositor("http://localhost:8001")

class MyAgent(BaseAgent):
    async def run(self, oxy_request, oxy_response):
        result = await self._run(oxy_request, oxy_response)
        
        depositor.deposit_e2e(
            source_trace_id=oxy_request.current_trace_id,
            source_request_id=oxy_request.request_id,
            question=oxy_request.arguments.get("query", ""),
            answer=str(result),
            callee="my_agent"
        )
        
        return result
```

## Deduplication

Records are deduplicated by hash of: `trace_id + request_id + question + answer`
