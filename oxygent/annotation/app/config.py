from typing import Any
import os

ES_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Index names prefix - keep stable across oxygent
INDEX_PREFIX = os.getenv("OXYGENT_INDEX_PREFIX", "oxygent")
ANNOTATIONS_INDEX = f"{INDEX_PREFIX}_annotations"
TASKS_INDEX = f"{INDEX_PREFIX}_tasks"
TAGS_INDEX = f"{INDEX_PREFIX}_tags"
WORKFLOW_INDEX = f"{INDEX_PREFIX}_workflow_state_changes"

JWT_SECRET = os.getenv("ANNOTATION_JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
