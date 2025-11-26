from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from pydantic import BaseModel
from ..db.es_client import es_client
from ..config import ANNOTATIONS_INDEX
from ..deps import get_current_user

router = APIRouter()

class AnnotationCreate(BaseModel):
    qa_id: str
    user_query: str
    agent_response: str
    annotations: dict = {}
    tags: List[str] = []


@router.post("/")
async def create_annotation(payload: AnnotationCreate, current_user=Depends(get_current_user)):
    doc = payload.dict()
    doc.update({"annotator_id": current_user.id, "annotator_name": current_user.username})
    # generate id
    from uuid import uuid4
    doc_id = str(uuid4())
    doc.update({"id": doc_id, "status": "annotated"})
    await es_client.index(index=ANNOTATIONS_INDEX, id=doc_id, document=doc, refresh='wait_for')
    return {"id": doc_id}


@router.get("/search")
async def search_annotations(q: str = Query("", alias="q"), page: int = 1, page_size: int = 20):
    body = {"query": {"bool": {"must": []}}}
    if q:
        body["query"]["bool"]["must"].append({"multi_match": {"query": q, "fields": ["user_query", "agent_response"]}})
    res = await es_client.search(index=ANNOTATIONS_INDEX, body=body, from_=(page-1)*page_size, size=page_size)
    hits = res.get("hits", {}).get("hits", [])
    items = [h.get("_source") for h in hits]
    total = res.get("hits", {}).get("total", {}).get("value", 0)
    return {"total": total, "data": items}
