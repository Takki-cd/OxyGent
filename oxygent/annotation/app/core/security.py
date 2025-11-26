from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from ..config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain, hashed):
    try:
        return pwd.verify(plain, hashed)
    except Exception:
        return False

def get_password_hash(pw):
    return pwd.hash(pw)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token
