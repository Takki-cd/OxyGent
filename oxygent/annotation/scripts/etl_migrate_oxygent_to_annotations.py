"""
Minimal ETL script: migrate from oxygent trace/node/message indices into the annotations index.
"""
import asyncio
import os
import json
from elasticsearch import AsyncElasticsearch, helpers

ES_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
APP_NAME = os.getenv("OXYGENT_APP_NAME", "oxygent")
TARGET = os.getenv("ANNOTATIONS_INDEX", f"{APP_NAME}_annotations")

async def extract_and_migrate(index_type="message", batch_size=500):
    es = AsyncElasticsearch([ES_URL])
    source = f"{APP_NAME}_{index_type}"
    q = {"query": {"match_all": {}}}
    resp = await es.search(index=source, body=q, size=batch_size)
    actions = []
    for h in resp.get("hits", {}).get("hits", []):
        src = h.get("_source", {})
        # very small extraction logic: try to find query/output
        user_query = src.get("input") or (src.get("group_data") and src.get("group_data").get("query")) or ""
        agent_response = src.get("output") or ""
        doc = {
            "id": h.get("_id"),
            "qa_id": h.get("_id"),
            "user_query": user_query,
            "agent_response": agent_response,
            "raw": src,
            "status": "pending"
        }
        actions.append({"_op_type": "index", "_index": TARGET, "_id": f"{index_type}::"+h.get("_id"), "_source": doc})
    if actions:
        await helpers.async_bulk(client=es, actions=actions)
    await es.close()

if __name__ == "__main__":
    asyncio.run(extract_and_migrate())
