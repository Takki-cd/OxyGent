"""
标注平台Bank Server

基于8081端口，封装标注平台8001的API服务。
按照OxyGent框架的bank协议实现，提供往标注平台注入数据的功能。
"""
import uvicorn
import requests
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
from datetime import datetime


app = FastAPI()

# router = APIRouter()

# 标注平台API地址
ANNOTATION_PLATFORM_URL = "http://127.0.0.1:8001"


class DepositRequest(BaseModel):
    """注入请求参数"""
    content: str
    agent_pin: str
    user_pin: str


def parse_content_to_deposit_data(content: str, agent_pin: str, user_pin: str) -> dict:
    """
    将content字符串解析为标注平台 deposit API 所需的格式
    
    content 格式示例:
    trace_id=request_id|caller=callee|group_id=xxx|question=xxx|answer=xxx|data_type=e2e|priority=0
    或者直接传入JSON格式的字典字符串
    """
    import json
    
    # 尝试解析JSON格式
    try:
        if content.startswith('{') and content.endswith('}'):
            data = json.loads(content)
            return {
                "source_trace_id": data.get("source_trace_id", f"trace_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"),
                "source_request_id": data.get("source_request_id", f"req_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"),
                "source_group_id": data.get("source_group_id", user_pin),
                "question": data.get("question", ""),
                "answer": data.get("answer", ""),
                "caller": data.get("caller", agent_pin),
                "callee": data.get("callee", "agent"),
                "data_type": data.get("data_type", "e2e"),
                "priority": data.get("priority", 0)
            }
    except json.JSONDecodeError:
        pass
    
    # 解析 key=value 格式
    result = {
        "source_trace_id": f"trace_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "source_request_id": f"req_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "source_group_id": user_pin,
        "question": "",
        "answer": "",
        "caller": agent_pin,
        "callee": "agent",
        "data_type": "e2e",
        "priority": 0
    }
    
    items = content.split('|')
    for item in items:
        if '=' in item:
            key, value = item.split('=', 1)
            key = key.strip()
            value = value.strip()
            
            if key == "trace_id":
                result["source_trace_id"] = value
            elif key == "request_id":
                result["source_request_id"] = value
            elif key == "group_id":
                result["source_group_id"] = value
            elif key == "question":
                result["question"] = value
            elif key == "answer":
                result["answer"] = value
            elif key == "caller":
                result["caller"] = value
            elif key == "callee":
                result["callee"] = value
            elif key == "data_type":
                result["data_type"] = value
            elif key == "priority":
                try:
                    result["priority"] = int(value)
                except ValueError:
                    pass
    
    return result


@app.post("/user_profile_deposit")
def user_profile_deposit(request: DepositRequest):
    """
    往标注平台注入数据
    
    格式支持:
    1. JSON格式: {"source_trace_id": "...", "source_request_id": "...", ...}
    2. Key-Value格式: trace_id=xxx|request_id=xxx|group_id=xxx|question=xxx|answer=xxx|data_type=e2e|priority=0
    """
    print(f"收到注入请求: content={request.content[:100]}...")
    
    # 解析content为标注平台所需的数据格式
    deposit_data = parse_content_to_deposit_data(request.content, request.agent_pin, request.user_pin)
    
    # 调用标注平台 deposit API
    try:
        response = requests.post(
            f"{ANNOTATION_PLATFORM_URL}/api/v1/deposit",
            json=deposit_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"注入成功: {result}")
            return {
                "status": "success",
                "message": "数据已成功注入标注平台",
                "data_id": result.get("data_id"),
                "deposit_data": deposit_data
            }
        else:
            print(f"注入失败: {response.status_code} - {response.text}")
            return {
                "status": "error",
                "message": f"标注平台返回错误: {response.status_code}",
                "detail": response.text
            }
            
    except requests.RequestException as e:
        print(f"请求标注平台失败: {e}")
        return {
            "status": "error",
            "message": f"无法连接标注平台: {str(e)}"
        }


@app.get("/list_banks")
def list_banks():
    """
    返回Bank列表，按照OxyGent框架协议
    """
    return [
        {
            "name": "user_profile_deposit",
            "endpoint": "/user_profile_deposit",
            "type": "deposit",
            "description": "A tool for depositing QA annotation data to annotation platform",
            "inputSchema": {
                "properties": {
                    "content": {
                        "description": "Deposit data content, support JSON format or key=value format separated by |. Fields: source_trace_id, source_request_id, source_group_id, question, answer, caller, callee, data_type, priority",
                        "type": "str"
                    },
                    "agent_pin": {"description": "SystemArg.agent_pin", "type": "str"},
                    "user_pin": {"description": "SystemArg.user_pin", "type": "str"},
                },
                "required": ["content", "agent_pin", "user_pin"],
                "type": "object",
            },
        },
    ]


# 注册路由到 app，添加 / 前缀确保路由匹配
# app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8081)

