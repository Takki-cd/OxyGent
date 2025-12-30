"""
QA标注平台演示脚本

演示如何注入QA数据和管理标注任务
"""
import requests
from datetime import datetime


BASE_URL = "http://127.0.0.1:8001"


def demo_deposit_single():
    """演示：注入单条QA数据（根节点）"""
    print("\n" + "="*50)
    print("演示1：注入单条QA数据（根节点）")
    print("="*50)
    
    data = {
        "source_trace_id": f"trace_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "source_group_id": "session_demo_001",
        "question": "你好，请介绍一下你自己",
        "answer": "我是OxyGent，一个AI Agent框架。",
        "is_root": True,
        "source_type": "e2e",
        "priority": 0,
        "caller": "user",
        "callee": "chat_agent"
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/deposit", json=data)
    print(f"请求: {data}")
    print(f"响应: {response.json()}")
    return response.json()


def demo_deposit_root():
    """演示：使用快捷接口注入根节点"""
    print("\n" + "="*50)
    print("演示1a：使用快捷接口注入根节点")
    print("="*50)
    
    data = {
        "source_trace_id": f"trace_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "source_group_id": "session_demo_001",
        "question": "快捷接口测试：今天天气如何？",
        "answer": "今天天气晴朗，适合出行。",
        "caller": "user",
        "callee": "weather_agent"
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/deposit/root", json=data)
    print(f"请求: {data}")
    print(f"响应: {response.json()}")
    return response.json()


def demo_deposit_with_children():
    """演示：注入带有子节点的QA数据（使用parent_qa_id字段）"""
    print("\n" + "="*50)
    print("演示2：注入端到端+子节点QA数据（parent_qa_id字段）")
    print("="*50)
    
    # 根节点trace_id
    root_trace_id = f"trace_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    
    # 1. 注入端到端记录（根节点）
    e2e_data = {
        "source_trace_id": root_trace_id,
        "source_group_id": "session_demo_002",
        "question": "帮我查一下北京天气",
        "answer": "北京今天天气晴朗，温度25度。",
        "is_root": True,
        "source_type": "e2e",
        "priority": 0,
        "caller": "user",
        "callee": "weather_agent"
    }
    
    response1 = requests.post(f"{BASE_URL}/api/v1/deposit", json=e2e_data)
    root_qa_id = response1.json().get("qa_id")
    print(f"根节点: {response1.json()}")
    
    # 2. 注入LLM子节点（通过parent_qa_id字段串联）
    llm_data = {
        "source_trace_id": root_trace_id,
        "source_group_id": "session_demo_002",
        "question": "天气查询Prompt: 用户查询=北京天气",
        "answer": "北京今天天气晴朗，温度25度。",
        "parent_qa_id": root_qa_id,
        "source_type": "agent_llm",
        "priority": 2,
        "caller": "weather_agent",
        "callee": "gpt-3.5-turbo"
    }
    
    response2 = requests.post(f"{BASE_URL}/api/v1/deposit", json=llm_data)
    print(f"LLM子节点: {response2.json()}")
    
    # 3. 注入Tool子节点
    tool_data = {
        "source_trace_id": root_trace_id,
        "source_group_id": "session_demo_002",
        "question": "调用天气API: 北京",
        "answer": '{"city": "北京", "weather": "晴朗", "temp": 25}',
        "parent_qa_id": root_qa_id,
        "source_type": "agent_tool",
        "priority": 3,
        "caller": "weather_agent",
        "callee": "weather_api"
    }
    
    response3 = requests.post(f"{BASE_URL}/api/v1/deposit", json=tool_data)
    print(f"Tool子节点: {response3.json()}")
    
    return {
        "root_trace_id": root_trace_id,
        "root_qa_id": root_qa_id
    }


def demo_deposit_child():
    """演示：使用快捷接口注入子节点"""
    print("\n" + "="*50)
    print("演示2a：使用快捷接口注入子节点")
    print("="*50)
    
    # 先创建根节点
    root_data = {
        "source_trace_id": f"trace_child_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "source_group_id": "session_demo_003",
        "question": "查询上海天气",
        "answer": "上海今天多云，温度22度。",
        "is_root": True,
        "priority": 0,
        "caller": "user",
        "callee": "weather_agent"
    }
    
    root_response = requests.post(f"{BASE_URL}/api/v1/deposit", json=root_data)
    root_qa_id = root_response.json().get("qa_id")
    print(f"根节点: {root_response.json()}")
    
    # 使用快捷接口注入子节点
    child_response = requests.post(
        f"{BASE_URL}/api/v1/deposit/child/{root_qa_id}",
        json={
            "source_trace_id": root_data["source_trace_id"],
            "source_group_id": "session_demo_003",
            "question": "LLM生成: 用户查询=上海天气",
            "answer": "上海今天多云，温度22度。",
            "source_type": "agent_llm",
            "priority": 2,
            "caller": "weather_agent",
            "callee": "gpt-4"
        }
    )
    print(f"子节点（快捷接口）: {child_response.json()}")
    
    return root_qa_id


def demo_batch_deposit():
    """演示：批量注入QA数据"""
    print("\n" + "="*50)
    print("演示3：批量注入QA数据")
    print("="*50)
    
    batch_trace_id = f"batch_trace_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    
    batch_data = {
        "items": [
            {
                "source_trace_id": batch_trace_id,
                "source_group_id": "session_batch",
                "question": "批量测试问题1",
                "answer": "批量测试答案1",
                "is_root": True,
                "source_type": "e2e",
                "priority": 0,
                "caller": "user",
                "callee": "agent_1"
            },
            {
                "source_trace_id": batch_trace_id,
                "source_group_id": "session_batch",
                "question": "LLM调用1",
                "answer": "LLM回答1",
                "parent_qa_id": "",  # 会在服务端通过QAContext建立关联
                "source_type": "agent_llm",
                "priority": 2,
                "caller": "agent_1",
                "callee": "llm_1"
            },
            {
                "source_trace_id": batch_trace_id,
                "source_group_id": "session_batch",
                "question": "批量测试问题2",
                "answer": "批量测试答案2",
                "is_root": True,
                "source_type": "e2e",
                "priority": 0,
                "caller": "user",
                "callee": "agent_2"
            }
        ]
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/deposit/batch", json=batch_data)
    print(f"批量注入响应: {response.json()}")
    return response.json()


def demo_get_tasks():
    """演示：获取任务列表"""
    print("\n" + "="*50)
    print("演示4：获取任务列表")
    print("="*50)
    
    response = requests.get(f"{BASE_URL}/api/v1/tasks", params={
        "page": 1,
        "page_size": 10,
        "show_roots_only": True  # 只显示根节点
    })
    print(f"任务列表: {response.json()}")
    return response.json()


def demo_get_tasks_with_children():
    """演示：获取包含子节点的任务"""
    print("\n" + "="*50)
    print("演示4a：获取任务详情和子节点")
    print("="*50)
    
    # 先获取任务列表
    list_response = requests.get(f"{BASE_URL}/api/v1/tasks", params={
        "page": 1,
        "page_size": 1,
        "status": "pending"
    })
    
    if list_response.json().get("items"):
        task = list_response.json()["items"][0]
        qa_id = task["qa_id"]
        
        # 获取详情
        detail_response = requests.get(f"{BASE_URL}/api/v1/tasks/{qa_id}")
        print(f"任务详情: {detail_response.json()}")
        
        # 获取子节点
        children_response = requests.get(f"{BASE_URL}/api/v1/tasks/{qa_id}/children")
        print(f"子节点: {children_response.json()}")
        
        return detail_response.json(), children_response.json()
    
    return None, None


def demo_get_stats():
    """演示：获取统计信息"""
    print("\n" + "="*50)
    print("演示5：获取统计信息")
    print("="*50)
    
    response = requests.get(f"{BASE_URL}/api/v1/stats")
    print(f"统计信息: {response.json()}")
    return response.json()


def demo_get_low_score_tasks():
    """演示：获取低分任务"""
    print("\n" + "="*50)
    print("演示5a：获取低分任务（需要关注）")
    print("="*50)
    
    response = requests.get(f"{BASE_URL}/api/v1/stats/low-score", params={
        "threshold": 0.6
    })
    print(f"低分任务: {response.json()}")
    return response.json()


def demo_annotate(qa_id: str):
    """演示：更新标注"""
    print("\n" + "="*50)
    print(f"演示6：更新标注 - {qa_id}")
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
    
    response = requests.put(f"{BASE_URL}/api/v1/tasks/{qa_id}/annotate", json=annotation_data)
    print(f"标注响应: {response.json()}")
    return response.json()


def demo_approve(qa_id: str):
    """演示：审核通过"""
    print("\n" + "="*50)
    print(f"演示7：审核通过 - {qa_id}")
    print("="*50)
    
    response = requests.post(f"{BASE_URL}/api/v1/tasks/{qa_id}/approve")
    print(f"通过响应: {response.json()}")
    return response.json()


def demo_reject(qa_id: str):
    """演示：审核拒绝"""
    print("\n" + "="*50)
    print(f"演示8：审核拒绝 - {qa_id}")
    print("="*50)
    
    response = requests.post(f"{BASE_URL}/api/v1/tasks/{qa_id}/reject")
    print(f"拒绝响应: {response.json()}")
    return response.json()


def main():
    """运行所有演示"""
    print("="*50)
    print("QA标注平台功能演示")
    print("="*50)
    
    # 1. 注入单条数据（基础方式）
    demo_deposit_single()
    
    # 1a. 快捷接口注入根节点
    demo_deposit_root()
    
    # 2. 注入链式数据（基础方式）
    chain_result = demo_deposit_with_children()
    
    # 2a. 快捷接口注入子节点
    demo_deposit_child()
    
    # 3. 批量注入
    demo_batch_deposit()
    
    # 4. 获取统计
    demo_get_stats()
    
    # 4a. 获取低分任务
    demo_get_low_score_tasks()
    
    # 5. 获取任务列表
    tasks_result = demo_get_tasks()
    
    # 5a. 获取任务详情和子节点
    demo_get_tasks_with_children()
    
    # 6. 如果有任务，演示标注操作
    if tasks_result.get("items"):
        qa_id = tasks_result["items"][0]["qa_id"]
        
        # 更新标注
        demo_annotate(qa_id)
        
        # 审核通过
        demo_approve(qa_id)
        
        # 如果有多个任务，演示拒绝
        if len(tasks_result["items"]) > 1:
            qa_id2 = tasks_result["items"][1]["qa_id"]
            demo_reject(qa_id2)
    
    print("\n" + "="*50)
    print("演示完成！")
    print("请访问 http://localhost:8001/web/index.html 查看前端界面")
    print("="*50)


if __name__ == "__main__":
    main()
