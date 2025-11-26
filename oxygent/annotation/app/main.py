from fastapi import APIRouter

# This module registers the annotation routers into the oxygent FastAPI app.
# It can be mounted by the MAS startup code or included into the main oxygent router.

router = APIRouter()

# Import routers to expose
from .routers import auth, annotations  # noqa: E402, F401

router.include_router(auth.router, prefix="/annotation/auth", tags=["annotation-auth"])
router.include_router(annotations.router, prefix="/annotation/annotations", tags=["annotation"])

# Simple health endpoint for annotation subsystem
@router.get("/annotation/health")
async def health():
    return {"status": "ok", "subsystem": "annotation"}
