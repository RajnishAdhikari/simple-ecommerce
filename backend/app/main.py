import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import models
from .database import Base, SessionLocal, engine
from .routes import admin, auth, cart, catalog, recommendations
from .security import validate_runtime_secret
from .seed_data import seed_products_if_needed


def parse_csv_env(var_name: str, default: str) -> list[str]:
    raw = os.getenv(var_name, default)
    return [value.strip() for value in raw.split(",") if value.strip()]


allowed_origins = parse_csv_env(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000",
)
allowed_hosts = parse_csv_env("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_runtime_secret()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_products_if_needed(db)
    finally:
        db.close()

    yield


app = FastAPI(
    title="Simple Ecommerce Web App",
    version="2.0.0",
    description="Production-ready ecommerce platform with FastAPI backend, PostgreSQL, and responsive frontend.",
    lifespan=lifespan,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=allowed_hosts,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Session-ID"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(recommendations.router)

project_root = Path(__file__).resolve().parents[2]
frontend_root = project_root / "frontend"
assets_root = frontend_root / "assets"

if assets_root.exists():
    app.mount("/assets", StaticFiles(directory=assets_root), name="assets")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
        "img-src 'self' https://images.unsplash.com data:; "
        "font-src 'self' https://fonts.gstatic.com; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )

    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

    if request.url.path.startswith("/api/auth"):
        response.headers["Cache-Control"] = "no-store"

    return response


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


def resolve_safe_frontend_path(path_name: str) -> Path:
    frontend_real_path = frontend_root.resolve()
    requested = (frontend_root / path_name).resolve()

    try:
        requested.relative_to(frontend_real_path)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc

    return requested


@app.get("/", include_in_schema=False)
def serve_homepage():
    index_path = frontend_root / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index_path)


@app.get("/{path_name:path}", include_in_schema=False)
def serve_frontend(path_name: str):
    if path_name.startswith("api"):
        raise HTTPException(status_code=404, detail="API route not found")

    candidate_path = resolve_safe_frontend_path(path_name)
    if candidate_path.exists() and candidate_path.is_file():
        return FileResponse(candidate_path)

    index_path = frontend_root / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    raise HTTPException(status_code=404, detail="Frontend not found")
