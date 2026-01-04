"""
QA Annotation Platform Demo Script (Simplified)

Demonstrate how to deposit data and manage annotation tasks
"""
import requests
from datetime import datetime


BASE_URL = "http://127.0.0.1:8001"


def demo_deposit_single():
    """Demo: Deposit single data (End-to-End, P0)"""
    print("\n" + "="*50)
    print("Demo 1: Deposit End-to-End data (P0 priority)")
    print("="*50)
    
    data = {
        "source_trace_id": f"trace_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "source_request_id": f"req_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "source_group_id": "session_demo_001",
        "question": "Hello, please introduce yourself",
        "answer": "I am OxyGent, an AI Agent framework.",
        "caller": "user",
        "callee": "chat_agent",
        "data_type": "e2e",
        "priority": 0  # End-to-End must be P0
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/deposit", json=data)
    print(f"Request: {data}")
    print(f"Response: {response.json()}")
    return response.json()


def demo_deposit_with_children():
    """Demo: Deposit End-to-End + child node data (aggregate by trace)"""
    print("\n" + "="*50)
    print("Demo 2: Deposit End-to-End + child node data (aggregate by trace)")
    print("="*50)
    
    # Same trace_id
    trace_id = f"trace_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    request_id_base = datetime.now().strftime('%Y%m%d%H%M%S%f')
    
    # 1. Deposit End-to-End record (P0)
    e2e_data = {
        "source_trace_id": trace_id,
        "source_request_id": f"{request_id_base}_e2e",
        "source_group_id": "session_demo_002",
        "question": "Please check Beijing weather",
        "answer": "Beijing weather is sunny today, temperature 25 degrees.",
        "caller": "user",
        "callee": "weather_agent",
        "data_type": "e2e",
        "priority": 0  # End-to-End
    }
    
    response1 = requests.post(f"{BASE_URL}/api/v1/deposit", json=e2e_data)
    print(f"End-to-End(P0): {response1.json()}")
    
    # 2. Deposit LLM child node (P2)
    llm_data = {
        "source_trace_id": trace_id,
        "source_request_id": f"{request_id_base}_llm",
        "source_group_id": "session_demo_002",
        "question": "Weather Query Prompt: User query=Beijing weather",
        "answer": "Beijing weather is sunny today, temperature 25 degrees.",
        "caller": "weather_agent",
        "callee": "gpt-3.5-turbo",
        "data_type": "llm",
        "priority": 2  # LLM call
    }
    
    response2 = requests.post(f"{BASE_URL}/api/v1/deposit", json=llm_data)
    print(f"LLM child node(P2): {response2.json()}")
    
    # 3. Deposit Tool child node (P3)
    tool_data = {
        "source_trace_id": trace_id,
        "source_request_id": f"{request_id_base}_tool",
        "source_group_id": "session_demo_002",
        "question": "Call weather API: Beijing",
        "answer": '{"city": "Beijing", "weather": "sunny", "temp": 25}',
        "caller": "weather_agent",
        "callee": "weather_api",
        "data_type": "tool",
        "priority": 3  # Tool call
    }
    
    response3 = requests.post(f"{BASE_URL}/api/v1/deposit", json=tool_data)
    print(f"Tool child node(P3): {response3.json()}")
    
    return {
        "trace_id": trace_id,
        "e2e_data_id": response1.json().get("data_id")
    }


def demo_batch_deposit():
    """Demo: Batch deposit data"""
    print("\n" + "="*50)
    print("Demo 3: Batch deposit data")
    print("="*50)
    
    trace_id = f"batch_trace_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    request_id_base = datetime.now().strftime('%Y%m%d%H%M%S%f')
    
    batch_data = {
        "items": [
            {
                "source_trace_id": trace_id,
                "source_request_id": f"{request_id_base}_1",
                "source_group_id": "session_batch",
                "question": "Batch test question 1",
                "answer": "Batch test answer 1",
                "caller": "user",
                "callee": "agent_1",
                "priority": 0  # End-to-End
            },
            {
                "source_trace_id": trace_id,
                "source_request_id": f"{request_id_base}_2",
                "source_group_id": "session_batch",
                "question": "LLM call 1",
                "answer": "LLM response 1",
                "caller": "agent_1",
                "callee": "llm_1",
                "data_type": "llm",
                "priority": 2
            },
            {
                "source_trace_id": trace_id,
                "source_request_id": f"{request_id_base}_3",
                "source_group_id": "session_batch",
                "question": "Batch test question 2",
                "answer": "Batch test answer 2",
                "caller": "user",
                "callee": "agent_2",
                "priority": 0  # End-to-End
            }
        ]
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/deposit/batch", json=batch_data)
    print(f"Batch deposit response: {response.json()}")
    return response.json()


def demo_get_data_list():
    """Demo: Get data list"""
    print("\n" + "="*50)
    print("Demo 4: Get data list")
    print("="*50)
    
    response = requests.get(f"{BASE_URL}/api/v1/data", params={
        "page": 1,
        "page_size": 10,
        "show_p0_only": True  # Only show P0
    })
    print(f"Data list: {response.json()}")
    return response.json()


def demo_get_data_by_trace():
    """Demo: Get all related data by trace_id"""
    print("\n" + "="*50)
    print("Demo 5: Get related data by trace_id")
    print("="*50)
    
    # Get a trace_id from existing data first
    list_response = requests.get(f"{BASE_URL}/api/v1/data", params={
        "page": 1,
        "page_size": 1
    })
    
    if list_response.json().get("items"):
        trace_id = list_response.json()["items"][0]["source_trace_id"]
        
        response = requests.get(f"{BASE_URL}/api/v1/data/trace/{trace_id}")
        print(f"Related data for trace_id={trace_id}: {response.json()}")
        return response.json()
    
    return None


def demo_get_groups_summary():
    """Demo: Get grouped summary"""
    print("\n" + "="*50)
    print("Demo 6: Get grouped summary")
    print("="*50)
    
    response = requests.get(f"{BASE_URL}/api/v1/data/groups/summary")
    print(f"Grouped summary: {response.json()}")
    return response.json()


def demo_get_stats():
    """Demo: Get statistics"""
    print("\n" + "="*50)
    print("Demo 7: Get statistics")
    print("="*50)
    
    response = requests.get(f"{BASE_URL}/api/v1/stats")
    print(f"Statistics: {response.json()}")
    return response.json()


def demo_get_pending_p0():
    """Demo: Get pending P0 data"""
    print("\n" + "="*50)
    print("Demo 8: Get pending P0 data")
    print("="*50)
    
    response = requests.get(f"{BASE_URL}/api/v1/stats/pending-p0")
    print(f"Pending P0: {response.json()}")
    return response.json()


def demo_annotate(data_id: str):
    """Demo: Update annotation"""
    print("\n" + "="*50)
    print(f"Demo 9: Update annotation - {data_id}")
    print("="*50)
    
    annotation_data = {
        "status": "annotated",
        "annotation": {
            "content": "This is a correct response",
            "quality_score": 0.85,
            "comment": "Response is basically correct, can be optimized"
        },
        "scores": {
            "overall_score": 0.85,
            "relevance": 0.9,
            "accuracy": 0.8,
            "fluency": 0.85
        }
    }
    
    response = requests.put(f"{BASE_URL}/api/v1/data/{data_id}/annotate", json=annotation_data)
    print(f"Annotation response: {response.json()}")
    return response.json()


def demo_approve(data_id: str):
    """Demo: Approve review"""
    print("\n" + "="*50)
    print(f"Demo 10: Approve review - {data_id}")
    print("="*50)
    
    response = requests.post(f"{BASE_URL}/api/v1/data/{data_id}/approve")
    print(f"Approve response: {response.json()}")
    return response.json()


def demo_reject(data_id: str):
    """Demo: Reject review"""
    print("\n" + "="*50)
    print(f"Demo 11: Reject review - {data_id}")
    print("="*50)
    
    response = requests.post(f"{BASE_URL}/api/v1/data/{data_id}/reject")
    print(f"Reject response: {response.json()}")
    return response.json()


def main():
    """Run all demos"""
    print("="*50)
    print("QA Annotation Platform Feature Demo (Simplified)")
    print("="*50)
    
    # 1. Deposit single data
    demo_deposit_single()
    
    # 2. Deposit chain data
    chain_result = demo_deposit_with_children()
    
    # 3. Batch deposit
    demo_batch_deposit()
    
    # 4. Get statistics
    demo_get_stats()
    
    # 5. Get pending P0
    demo_get_pending_p0()
    
    # 6. Get grouped summary
    demo_get_groups_summary()
    
    # 7. Get data list
    list_result = demo_get_data_list()
    
    # 8. Get trace-related data
    demo_get_data_by_trace()
    
    # 9. If there is data, demo annotation operations
    if list_result.get("items"):
        data_id = list_result["items"][0]["data_id"]
        
        # Update annotation
        demo_annotate(data_id)
        
        # Approve review
        demo_approve(data_id)
        
        # If there are multiple data, demo rejection
        if len(list_result["items"]) > 1:
            data_id2 = list_result["items"][1]["data_id"]
            demo_reject(data_id2)
    
    print("\n" + "="*50)
    print("Demo completed!")
    print("Please visit http://localhost:8001/web/index.html to view the frontend interface")
    print("="*50)


if __name__ == "__main__":
    main()
