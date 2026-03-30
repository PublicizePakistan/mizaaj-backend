from passlib.context import CryptContext
from fastapi import HTTPException

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    if not password:
        raise HTTPException(status_code=400, detail="Password cannot be empty")

    # bcrypt limit fix (72 bytes)
    if len(password) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password too long (max 72 characters allowed)"
        )

    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if len(plain) > 72:
        plain = plain[:72]  # truncate safely for verification

    return pwd_context.verify(plain, hashed)