"""
QA标注平台演示脚本（简化版）

演示如何注入数据和管理标注任务
"""
import requests
from datetime import datetime


BASE_URL = "http://127.0.0.1:8001"


def demo_deposit_single():
    """演示：注入单条数据（端到端，P0）"""
    print("\n" + "="*50)
    print("演示1：注入端到端数据（P0优先级）")
    print("="*50)
    
    data = {
        "source_trace_id": f"trace_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "source_request_id": f"req_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "source_group_id": "session_demo_001",
        "question": "你好，请介绍一下你自己",
        "answer": "我是OxyGent，一个AI Agent框架。",
        "caller": "user",
        "callee": "chat_agent",
        "data_type": "e2e",
        "priority": 0  # 端到端必须是P0
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/deposit", json=data)
    print(f"请求: {data}")
    print(f"响应: {response.json()}")
    return response.json()


def demo_deposit_with_children():
    """演示：注入端到端+子节点数据（按trace聚合）"""
    print("\n" + "="*50)
    print("演示2：注入端到端+子节点数据（按trace聚合）")
    print("="*50)
    
    # 同一trace_id
    trace_id = f"trace_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    request_id_base = datetime.now().strftime('%Y%m%d%H%M%S%f')
    
    # 1. 注入端到端记录（P0）
    e2e_data = {
        "source_trace_id": trace_id,
        "source_request_id": f"{request_id_base}_e2e",
        "source_group_id": "session_demo_002",
        "question": "帮我查一下北京天气",
        "answer": "北京今天天气晴朗，温度25度。",
        "caller": "user",
        "callee": "weather_agent",
        "data_type": "e2e",
        "priority": 0  # 端到端
    }
    
    response1 = requests.post(f"{BASE_URL}/api/v1/deposit", json=e2e_data)
    print(f"端到端(P0): {response1.json()}")
    
    # 2. 注入LLM子节点（P2）
    llm_data = {
        "source_trace_id": trace_id,
        "source_request_id": f"{request_id_base}_llm",
        "source_group_id": "session_demo_002",
        "question": "天气查询Prompt: 用户查询=北京天气",
        "answer": "北京今天天气晴朗，温度25度。",
        "caller": "weather_agent",
        "callee": "gpt-3.5-turbo",
        "data_type": "llm",
        "priority": 2  # LLM调用
    }
    
    response2 = requests.post(f"{BASE_URL}/api/v1/deposit", json=llm_data)
    print(f"LLM子节点(P2): {response2.json()}")
    
    # 3. 注入Tool子节点（P3）
    tool_data = {
        "source_trace_id": trace_id,
        "source_request_id": f"{request_id_base}_tool",
        "source_group_id": "session_demo_002",
        "question": "调用天气API: 北京",
        "answer": '{"city": "北京", "weather": "晴朗", "temp": 25}',
        "caller": "weather_agent",
        "callee": "weather_api",
        "data_type": "tool",
        "priority": 3  # Tool调用
    }
    
    response3 = requests.post(f"{BASE_URL}/api/v1/deposit", json=tool_data)
    print(f"Tool子节点(P3): {response3.json()}")
    
    return {
        "trace_id": trace_id,
        "e2e_data_id": response1.json().get("data_id")
    }


def demo_batch_deposit():
    """演示：批量注入数据"""
    print("\n" + "="*50)
    print("演示3：批量注入数据")
    print("="*50)
    
    trace_id = f"batch_trace_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    request_id_base = datetime.now().strftime('%Y%m%d%H%M%S%f')
    
    batch_data = {
        "items": [
            {
                "source_trace_id": trace_id,
                "source_request_id": f"{request_id_base}_1",
                "source_group_id": "session_batch",
                "question": "批量测试问题1",
                "answer": "批量测试答案1",
                "caller": "user",
                "callee": "agent_1",
                "priority": 0  # 端到端
            },
            {
                "source_trace_id": trace_id,
                "source_request_id": f"{request_id_base}_2",
                "source_group_id": "session_batch",
                "question": "LLM调用1",
                "answer": "LLM回答1",
                "caller": "agent_1",
                "callee": "llm_1",
                "data_type": "llm",
                "priority": 2
            },
            {
                "source_trace_id": trace_id,
                "source_request_id": f"{request_id_base}_3",
                "source_group_id": "session_batch",
                "question": "批量测试问题2",
                "answer": "批量测试答案2",
                "caller": "user",
                "callee": "agent_2",
                "priority": 0  # 端到端
            }
        ]
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/deposit/batch", json=batch_data)
    print(f"批量注入响应: {response.json()}")
    return response.json()


def demo_get_data_list():
    """演示：获取数据列表"""
    print("\n" + "="*50)
    print("演示4：获取数据列表")
    print("="*50)
    
    response = requests.get(f"{BASE_URL}/api/v1/data", params={
        "page": 1,
        "page_size": 10,
        "show_p0_only": True  # 只显示P0
    })
    print(f"数据列表: {response.json()}")
    return response.json()


def demo_get_data_by_trace():
    """演示：根据trace_id获取所有关联数据"""
    print("\n" + "="*50)
    print("演示5：根据trace_id获取关联数据")
    print("="*50)
    
    # 先获取一条数据的trace_id
    list_response = requests.get(f"{BASE_URL}/api/v1/data", params={
        "page": 1,
        "page_size": 1
    })
    
    if list_response.json().get("items"):
        trace_id = list_response.json()["items"][0]["source_trace_id"]
        
        response = requests.get(f"{BASE_URL}/api/v1/data/trace/{trace_id}")
        print(f"trace_id={trace_id} 的关联数据: {response.json()}")
        return response.json()
    
    return None


def demo_get_groups_summary():
    """演示：获取分组汇总"""
    print("\n" + "="*50)
    print("演示6：获取分组汇总")
    print("="*50)
    
    response = requests.get(f"{BASE_URL}/api/v1/data/groups/summary")
    print(f"分组汇总: {response.json()}")
    return response.json()


def demo_get_stats():
    """演示：获取统计信息"""
    print("\n" + "="*50)
    print("演示7：获取统计信息")
    print("="*50)
    
    response = requests.get(f"{BASE_URL}/api/v1/stats")
    print(f"统计信息: {response.json()}")
    return response.json()


def demo_get_pending_p0():
    """演示：获取待标注的P0数据"""
    print("\n" + "="*50)
    print("演示8：获取待标注的P0数据")
    print("="*50)
    
    response = requests.get(f"{BASE_URL}/api/v1/stats/pending-p0")
    print(f"待标注P0: {response.json()}")
    return response.json()


def demo_annotate(data_id: str):
    """演示：更新标注"""
    print("\n" + "="*50)
    print(f"演示9：更新标注 - {data_id}")
    print("="*50)
    
    annotation_data = {
        "status": "annotated",
        "annotation": {
            "content": "这是一个正确的回答",
            "quality_score": 0.85,
            "comment": "回答基本正确，可以优化"
        },
        "scores": {
            "overall_score": 0.85,
            "relevance": 0.9,
            "accuracy": 0.8,
            "fluency": 0.85
        }
    }
    
    response = requests.put(f"{BASE_URL}/api/v1/data/{data_id}/annotate", json=annotation_data)
    print(f"标注响应: {response.json()}")
    return response.json()


def demo_approve(data_id: str):
    """演示：审核通过"""
    print("\n" + "="*50)
    print(f"演示10：审核通过 - {data_id}")
    print("="*50)
    
    response = requests.post(f"{BASE_URL}/api/v1/data/{data_id}/approve")
    print(f"通过响应: {response.json()}")
    return response.json()


def demo_reject(data_id: str):
    """演示：审核拒绝"""
    print("\n" + "="*50)
    print(f"演示11：审核拒绝 - {data_id}")
    print("="*50)
    
    response = requests.post(f"{BASE_URL}/api/v1/data/{data_id}/reject")
    print(f"拒绝响应: {response.json()}")
    return response.json()


def main():
    """运行所有演示"""
    print("="*50)
    print("QA标注平台功能演示（简化版）")
    print("="*50)
    
    # 1. 注入单条数据
    demo_deposit_single()
    
    # 2. 注入链式数据
    chain_result = demo_deposit_with_children()
    
    # 3. 批量注入
    demo_batch_deposit()
    
    # 4. 获取统计
    demo_get_stats()
    
    # 5. 获取待标注P0
    demo_get_pending_p0()
    
    # 6. 获取分组汇总
    demo_get_groups_summary()
    
    # 7. 获取数据列表
    list_result = demo_get_data_list()
    
    # 8. 获取trace关联数据
    demo_get_data_by_trace()
    
    # 9. 如果有数据，演示标注操作
    if list_result.get("items"):
        data_id = list_result["items"][0]["data_id"]
        
        # 更新标注
        demo_annotate(data_id)
        
        # 审核通过
        demo_approve(data_id)
        
        # 如果有多个数据，演示拒绝
        if len(list_result["items"]) > 1:
            data_id2 = list_result["items"][1]["data_id"]
            demo_reject(data_id2)
    
    print("\n" + "="*50)
    print("演示完成！")
    print("请访问 http://localhost:8001/web/index.html 查看前端界面")
    print("="*50)


if __name__ == "__main__":
    main()
