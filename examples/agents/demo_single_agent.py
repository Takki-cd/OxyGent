"""Demo for using OxyGent with multiple LLMs and an agent."""

import asyncio
import os

from oxygent import MAS, Config, OxyRequest, OxyResponse, oxy

Config.set_agent_short_memory_size(7)


def update_query(oxy_request: OxyRequest) -> OxyRequest:
    query = oxy_request.get_query()
    oxy_request.set_query(query + " Please answer in detail.")
    return oxy_request


def format_output(oxy_response: OxyResponse) -> OxyResponse:
    oxy_request = oxy_response.oxy_request
    oxy_response.output = "有output" + oxy_response.output
    oxy_response.oxy_request.call_async(callee="annotation_bank", arguments={"params": "各种QA数据需要的数据维度，例如：group_id、trace_ID、node_ID、类型、问题、答案、来源、时间、用户等"})
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
        server_url="http://127.0.0.1:8090",
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
