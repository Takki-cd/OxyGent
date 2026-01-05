"""Demo for using OxyGent with multiple LLMs and an agent."""

import asyncio
import os

from oxygent import MAS, Config, OxyRequest, OxyResponse, oxy

Config.set_agent_short_memory_size(7)


def update_query(oxy_request: OxyRequest) -> OxyRequest:
    query = oxy_request.get_query()
    oxy_request.set_query(query + " Please answer in detail.")
    return oxy_request


async def format_output(oxy_response: OxyResponse) -> OxyResponse:
    oxy_request = oxy_response.oxy_request
    oxy_response.output = "Answer:" + oxy_response.output
    
    # 构建QA标注数据
    import json
    from datetime import datetime
    
    annotation_data = {
        "source_trace_id": f"trace_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "source_request_id": f"req_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "source_group_id": "session_demo_001",
        "question": oxy_request.get_query(),
        "answer": oxy_response.output,
        "caller": "user",
        "callee": "chat_agent",
        "data_type": "e2e",
        "priority": 0
    }
    
    # 将数据转换为字符串格式传递给bank
    content = json.dumps(annotation_data, ensure_ascii=False)
    
    # 调用annotation_bank注入数据
    await oxy_response.oxy_request.call_async(
        callee="user_profile_deposit", 
        arguments={
            "content": content,
            "agent_pin": "master_agent",
            "user_pin": "user_001"
        }
    )
    return oxy_response


oxy_space = [
    oxy.HttpLLM(
        name="default_llm",
        api_key=os.getenv("DEFAULT_LLM_API_KEY"),
        base_url=os.getenv("DEFAULT_LLM_BASE_URL"),
        model_name=os.getenv("DEFAULT_LLM_MODEL_NAME"),
        llm_params={"temperature": 0.01},
        semaphore=4,
        timeout=300,
        retries=3,
    ),
    oxy.ChatAgent(
        name="master_agent",
        llm_model="default_llm",
        prompt="You are a helpful assistant.",
        banks=["annotation_bank"],
        func_process_input=update_query,
        func_format_output=format_output,
    ),
    oxy.BankClient(
        name="annotation_bank",
        server_url="http://127.0.0.1:8081",
    ),
]


async def main():
    async with MAS(oxy_space=oxy_space) as mas:
        await mas.start_web_service(
            first_query="Hello",
            welcome_message="Hi, I’m OxyGent. How can I assist you?",
        )


if __name__ == "__main__":
    asyncio.run(main())
