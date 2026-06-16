import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..rate_limit import AUTH_LOGIN_LIMIT, AUTH_REGISTER_LIMIT, get_client_identifier, rate_limiter
from ..schemas import AuthResponse, LoginRequest, RegisterRequest
from ..security import clear_access_token_cookie, create_access_token, hash_password, set_access_token_cookie, verify_password
from ..store import safe_user_profile

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

FULL_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,99}$")
PASSWORD_UPPER = re.compile(r"[A-Z]")
PASSWORD_LOWER = re.compile(r"[a-z]")
PASSWORD_DIGIT = re.compile(r"\d")
PASSWORD_SYMBOL = re.compile(r"[^A-Za-z0-9]")


def validate_password_strength(password: str) -> None:
    if not PASSWORD_UPPER.search(password):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password must include uppercase")
    if not PASSWORD_LOWER.search(password):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password must include lowercase")
    if not PASSWORD_DIGIT.search(password):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password must include number")
    if not PASSWORD_SYMBOL.search(password):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password must include symbol")


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    identifier = get_client_identifier(request)
    rate_limiter.enforce("auth_register", identifier, AUTH_REGISTER_LIMIT)

    email_key = payload.email.lower().strip()
    username_value = payload.username.strip()
    full_name = " ".join(payload.full_name.split())

    if not FULL_NAME_PATTERN.fullmatch(full_name):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid full name")
    validate_password_strength(payload.password)

    duplicate_user = (
        db.query(User.id)
        .filter(
            (func.lower(User.email) == email_key.lower())
            | (func.lower(User.username) == username_value.lower())
        )
        .first()
    )
    if duplicate_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Registration failed")

    new_user = User(
        email=email_key,
        username=username_value,
        full_name=full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(new_user)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Registration failed") from exc

    db.refresh(new_user)

    token = create_access_token(user_id=new_user.id, email=email_key)
    set_access_token_cookie(response, token)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": safe_user_profile(new_user),
    }


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    identifier = get_client_identifier(request)
    rate_limiter.enforce("auth_login", identifier, AUTH_LOGIN_LIMIT)

    email_key = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email_key).first()

    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(user_id=user.id, email=email_key)
    set_access_token_cookie(response, token)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": safe_user_profile(user),
    }


@router.post("/logout")
def logout(response: Response):
    clear_access_token_cookie(response)
    return {"status": "ok"}
