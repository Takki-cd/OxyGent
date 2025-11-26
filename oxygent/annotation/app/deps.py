from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from ..config import JWT_SECRET
from ..db.redis_client import redis_client
from ..models import user as user_model

oauth2 = OAuth2PasswordBearer(tokenUrl="/annotation/auth/login")


def get_current_user(token: str = Depends(oauth2)) -> user_model.User:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
    key = f"user:{username}"
    if not redis_client.exists(key):
        raise HTTPException(status_code=401, detail="user not found")
    info = redis_client.hgetall(key)
    return user_model.User(id=info.get("id"), username=info.get("username"), role=info.get("role"))
