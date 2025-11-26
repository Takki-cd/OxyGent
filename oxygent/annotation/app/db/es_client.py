from elasticsearch import AsyncElasticsearch
from ..config import ES_URL

# Lightweight wrapper: reuse oxygent's ES if available; otherwise create new client
es_client = AsyncElasticsearch([ES_URL])
