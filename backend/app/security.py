import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .rate_limit import ADMIN_LIMIT, get_client_identifier, rate_limiter

_configured_secret = os.getenv("SECRET_KEY")
IS_EPHEMERAL_SECRET = not _configured_secret
SECRET_KEY = _configured_secret or secrets.token_urlsafe(48)
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "30"))
JWT_ISSUER = os.getenv("JWT_ISSUER", "skycart-api")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "skycart-web")
PBKDF2_ITERATIONS = int(os.getenv("PBKDF2_ITERATIONS", "240000"))
SESSION_COOKIE_NAME = "skycart_session"
security_scheme = HTTPBearer(auto_error=False)


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith("replace-with") or lowered in {"changeme", "change-me", "secret"}


def validate_runtime_secret() -> None:
    app_env = os.getenv("APP_ENV", "development").lower()
    if app_env == "production" and (
        IS_EPHEMERAL_SECRET or len(SECRET_KEY) < 32 or _looks_like_placeholder(SECRET_KEY)
    ):
        raise RuntimeError("SECRET_KEY must be set to a strong value in production.")

    admin_api_key = os.getenv("ADMIN_API_KEY", "").strip()
    if app_env == "production" and (len(admin_api_key) < 32 or _looks_like_placeholder(admin_api_key)):
        raise RuntimeError("ADMIN_API_KEY must be set to a strong value in production.")

    admin_emails = parse_csv_env("ADMIN_EMAILS")
    if app_env == "production" and not admin_emails:
        raise RuntimeError("ADMIN_EMAILS must include at least one admin email in production.")

    if app_env == "production" and not os.getenv("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL must be set in production.")


def parse_csv_env(var_name: str) -> set[str]:
    raw = os.getenv(var_name, "")
    return {value.strip().lower() for value in raw.split(",") if value.strip()}


def _enforce_admin_api_key(
    request: Request,
    x_admin_api_key: Optional[str] = Header(default=None, alias="X-Admin-API-Key"),
) -> None:
    identifier = get_client_identifier(request)
    rate_limiter.enforce("admin", identifier, ADMIN_LIMIT)

    configured_key = os.getenv("ADMIN_API_KEY", "").strip()
    if len(configured_key) < 32 or _looks_like_placeholder(configured_key):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key is not configured",
        )

    supplied_key = (x_admin_api_key or "").strip()
    if len(supplied_key) > 256 or not hmac.compare_digest(supplied_key, configured_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication failed")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${base64.b64encode(digest).decode('utf-8')}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        algorithm, iterations, salt, encoded_digest = hashed_password.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False

        expected_digest = base64.b64decode(encoded_digest.encode("utf-8"))
        iteration_count = int(iterations)
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt.encode("utf-8"),
        iteration_count,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def create_access_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": secrets.token_hex(12),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def set_access_token_cookie(response: Response, token: str) -> None:
    app_env = os.getenv("APP_ENV", "development").lower()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=app_env == "production",
        samesite="lax",
        path="/",
    )


def clear_access_token_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def _decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={
                "require_sub": True,
                "require_iat": True,
                "require_nbf": True,
                "require_exp": True,
                "require_jti": True,
            },
        )
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def _token_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[str]:
    if credentials is not None:
        return credentials.credentials
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    return cookie_token.strip() if cookie_token else None


def _current_user_from_payload(payload: dict, db: Session) -> dict:
    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = db.query(User).filter(User.id == int(user_id), User.email == str(email).lower()).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return {
        "id": user.id,
        "email": user.email,
    }


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> dict:
    token = _token_from_request(request, credentials)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    payload = _decode_access_token(token)
    return _current_user_from_payload(payload, db)


def get_optional_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
):
    token = _token_from_request(request, credentials)
    if token is None:
        return None

    try:
        payload = _decode_access_token(token)
        return _current_user_from_payload(payload, db)
    except HTTPException:
        return None


def require_admin_user(
    request: Request,
    x_admin_api_key: Optional[str] = Header(default=None, alias="X-Admin-API-Key"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    _enforce_admin_api_key(request=request, x_admin_api_key=x_admin_api_key)

    admin_emails = parse_csv_env("ADMIN_EMAILS")
    if not admin_emails:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin emails are not configured")

    if current_user["email"].lower() not in admin_emails:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access denied")

    return current_user


def require_admin_key(
    request: Request,
    x_admin_api_key: Optional[str] = Header(default=None, alias="X-Admin-API-Key"),
) -> None:
    _enforce_admin_api_key(request=request, x_admin_api_key=x_admin_api_key)
