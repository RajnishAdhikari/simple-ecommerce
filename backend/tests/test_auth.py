import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ["DATABASE_URL"] = f"sqlite:///{PROJECT_ROOT / 'test_ecommerce.db'}"
os.environ["APP_ENV"] = "development"
os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"
os.environ["ADMIN_API_KEY"] = "test-admin-api-key-for-content-tools-123456"
os.environ["ADMIN_EMAILS"] = "newuser@example.com"

sys.path.append(str(PROJECT_ROOT))

from backend.app.database import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import User
from backend.app.rate_limit import rate_limiter
from backend.app.seed_data import seed_products_if_needed


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_app_state():
    client.cookies.clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_products_if_needed(db)
    finally:
        db.close()

    rate_limiter.reset()


def register_payload():
    return {
        "email": "newuser@example.com",
        "username": "newuser",
        "full_name": "New User",
        "password": "StrongPass#123",
    }


def login_admin_user() -> dict[str, str]:
    response = client.post("/api/auth/register", json=register_payload())
    assert response.status_code == 201
    return {"X-Admin-API-Key": os.environ["ADMIN_API_KEY"]}


def test_register_login_and_me_flow():
    register_response = client.post("/api/auth/register", json=register_payload())
    assert register_response.status_code == 201
    token = register_response.json()["access_token"]

    me_response = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "newuser@example.com"

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "newuser@example.com",
            "password": "StrongPass#123",
        },
    )
    assert login_response.status_code == 200
    assert "access_token" in login_response.json()

    cookie_me_response = client.get("/api/users/me")
    assert cookie_me_response.status_code == 200
    assert cookie_me_response.json()["email"] == "newuser@example.com"


def test_password_policy_blocks_weak_password():
    response = client.post(
        "/api/auth/register",
        json={
            "email": "weak@example.com",
            "username": "weakuser",
            "full_name": "Weak User",
            "password": "weakpass",
        },
    )
    assert response.status_code == 422


def test_register_blocks_case_insensitive_duplicates():
    first = client.post("/api/auth/register", json=register_payload())
    assert first.status_code == 201

    duplicate_email = client.post(
        "/api/auth/register",
        json={
            "email": "NEWUSER@EXAMPLE.COM",
            "username": "anotheruser",
            "full_name": "Another User",
            "password": "StrongPass#123",
        },
    )
    assert duplicate_email.status_code == 409

    duplicate_username = client.post(
        "/api/auth/register",
        json={
            "email": "another@example.com",
            "username": "NewUser",
            "full_name": "Another User",
            "password": "StrongPass#123",
        },
    )
    assert duplicate_username.status_code == 409


def test_login_rate_limit():
    payload = register_payload()
    client.post("/api/auth/register", json=payload)

    for _ in range(8):
        response = client.post(
            "/api/auth/login",
            json={"email": payload["email"], "password": "WrongPass#123"},
            headers={"x-forwarded-for": "203.0.113.42"},
        )
        assert response.status_code == 401

    blocked_response = client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": "WrongPass#123"},
        headers={"x-forwarded-for": "203.0.113.42"},
    )
    assert blocked_response.status_code == 429


def test_search_endpoint_returns_relevant_result_first():
    response = client.get("/api/products/search", params={"q": "cloud crop tp", "limit": 5})
    assert response.status_code == 200

    results = response.json()["products"]
    assert len(results) >= 1
    assert results[0]["name"] == "Cloud Mesh Crop Top"


def test_recommendations_endpoint_returns_results_for_session():
    response = client.get("/api/recommendations", headers={"X-Session-ID": "session_reco_1234567890"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] > 0
    assert isinstance(payload["products"], list)


def test_view_tracking_updates_similar_products_endpoint():
    track_response = client.post(
        "/api/recommendations/track-view",
        headers={"X-Session-ID": "session_reco_abcdefgh1234"},
        json={"product_id": 1},
    )
    assert track_response.status_code == 200

    rec_response = client.get("/api/products/1/recommendations", params={"limit": 5})
    assert rec_response.status_code == 200
    rec_products = rec_response.json()["products"]
    assert len(rec_products) > 0
    assert all(product["id"] != 1 for product in rec_products)


def test_authenticated_recommendations_after_cart_event():
    register_response = client.post("/api/auth/register", json=register_payload())
    token = register_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Session-ID": "session_reco_user123456"}

    add_response = client.post(
        "/api/cart/items",
        headers=headers,
        json={"product_id": 4, "quantity": 1, "size": "40", "color": "Orange"},
    )
    assert add_response.status_code == 201

    rec_response = client.get("/api/recommendations", headers=headers)
    assert rec_response.status_code == 200
    rec_products = rec_response.json()["products"]
    assert len(rec_products) > 0
    assert all(product["id"] != 4 for product in rec_products)


def test_security_headers_are_set():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_inactive_user_cannot_login_or_use_existing_token():
    register_response = client.post("/api/auth/register", json=register_payload())
    assert register_response.status_code == 201
    token = register_response.json()["access_token"]

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email="newuser@example.com").first()
        user.is_active = False
        db.commit()
    finally:
        db.close()

    login_response = client.post(
        "/api/auth/login",
        json={"email": "newuser@example.com", "password": "StrongPass#123"},
    )
    assert login_response.status_code == 401

    me_response = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 401


def test_admin_content_preview_requires_api_key():
    client.post("/api/auth/register", json=register_payload())
    response = client.post(
        "/api/admin/products/content-preview",
        json={"name": "Fresh Apple", "category": "Grocery"},
    )
    assert response.status_code == 401


def test_admin_content_preview_uses_only_entered_optional_fields():
    headers = login_admin_user()
    response = client.post(
        "/api/admin/products/content-preview",
        headers=headers,
        json={
            "name": "Handwoven Bamboo Basket",
            "category": "Handicraft",
            "material": "Natural bamboo",
            "dimensions": "12 x 8 inches",
            "handmade": True,
            "features": ["Lightweight", "Reusable"],
        },
    )
    assert response.status_code == 200

    payload = response.json()
    detail_lines = "\n".join(payload["detail_lines"])
    assert "Material: Natural bamboo" in detail_lines
    assert "Dimensions: 12 x 8 inches" in detail_lines
    assert "Handmade: Yes" in detail_lines
    assert "Ingredients" not in detail_lines
    assert "Storage" not in detail_lines
    assert "Care" not in detail_lines

    instagram_caption = payload["social_media_formats"]["instagram_caption"]
    assert "Handwoven Bamboo Basket" in instagram_caption
    assert "Natural bamboo" in instagram_caption
    assert "Ingredients" not in instagram_caption


def test_admin_create_product_generates_description_and_social_formats():
    headers = login_admin_user()
    response = client.post(
        "/api/admin/products",
        headers=headers,
        json={
            "name": "Organic Millet Flour",
            "category": "Grocery",
            "product_type": "Flour",
            "price": 8.5,
            "original_price": 10.0,
            "ingredients": "Organic millet",
            "shelf_life": "6 months",
            "storage_instructions": "Store in a cool dry place",
            "features": ["Stone ground", "No added sugar"],
        },
    )
    assert response.status_code == 201

    payload = response.json()
    assert payload["product"]["name"] == "Organic Millet Flour"
    assert payload["product"]["description"] == payload["generated_content"]["description"]

    detail_lines = "\n".join(payload["generated_content"]["detail_lines"])
    assert "Offer Price: $8.50" in detail_lines
    assert "Ingredients: Organic millet" in detail_lines
    assert "Shelf Life: 6 months" in detail_lines
    assert "Sizes" not in detail_lines
    assert "Care" not in detail_lines

    search_response = client.get("/api/products/search", params={"q": "organic millet", "limit": 5})
    assert search_response.status_code == 200
    assert any(product["name"] == "Organic Millet Flour" for product in search_response.json()["products"])
