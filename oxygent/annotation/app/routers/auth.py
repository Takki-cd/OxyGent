from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db.redis_client import redis_client
from ..core.security import create_access_token, verify_password

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    key = f"user:{req.username}"
    if not redis_client.exists(key):
        raise HTTPException(status_code=401, detail="invalid credentials")
    user = redis_client.hgetall(key)
    if not verify_password(req.password, user.get("hashed_password", "")):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = create_access_token({"sub": user.get("username"), "role": user.get("role"), "id": user.get("id")})
    return {"access_token": token}
