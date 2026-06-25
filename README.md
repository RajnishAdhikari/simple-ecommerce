# Simple Ecommerce Web App

Production-grade ecommerce web app with FastAPI backend, PostgreSQL database, recommendation engine, and interactive mobile-responsive frontend.

## Features

- Secure authentication with JWT and strong password policy
- PostgreSQL-backed persistence for users, products, cart, orders, and recommendation events
- Fast search (`/api/products/search`) with typo tolerance and relevance ranking
- Amazon-style inspired hybrid recommendations
- Backend-only admin content generation for product descriptions and social media post formats
- Interactive frontend with search suggestions, quick view, cart drawer, and personalized recommendations
- Dockerized production-style runtime with Gunicorn + Uvicorn workers

## API overview

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/users/me`
- `GET /api/products`
- `GET /api/products/search`
- `GET /api/products/{id}`
- `GET /api/categories`
- `GET /api/hero-banners`
- `GET /api/cart`
- `POST /api/cart/items`
- `PATCH /api/cart/items/{product_id}`
- `DELETE /api/cart/items/{product_id}`
- `POST /api/checkout`
- `GET /api/recommendations`
- `GET /api/products/{id}/recommendations`
- `POST /api/recommendations/track-view`
- `POST /api/admin/products/content-preview`
- `POST /api/admin/products`

Admin endpoints require both an authenticated active user whose email is listed in `ADMIN_EMAILS` and an `X-Admin-API-Key` header matching `ADMIN_API_KEY`. They accept optional product attributes for grocery, clothing, handicraft, electronics, home goods, and other product types. Only provided fields are included in the generated detail lines and social media formats.

Example admin content preview:

```powershell
curl -X POST http://localhost:8000/api/admin/products/content-preview `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer <admin-access-token>" `
  -H "X-Admin-API-Key: $env:ADMIN_API_KEY" `
  -d '{
    "name": "Handwoven Bamboo Basket",
    "category": "Handicraft",
    "material": "Natural bamboo",
    "dimensions": "12 x 8 inches",
    "origin": "Local artisan workshop",
    "handmade": true,
    "features": ["Lightweight", "Reusable", "Decorative storage"]
  }'
```

## Local setup (virtual env)

1. Open terminal in project root:
cd ecommerce-platform

2. Create virtual environment:
   python -m venv .venv

3. Activate virtual environment:
.\.venv\Scripts\Activate.ps1

4. Install dependencies:
   pip install --upgrade pip
   pip install -r backend/requirements.txt

   For local testing/security tooling:
   pip install -r backend/requirements-dev.txt
   
5. Create env file from template:
   ```powershell
   copy .env.example .env
   ```
6. Ensure PostgreSQL is running and `DATABASE_URL` in `.env` is valid.
7. Start app:
   ```powershell
   uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
   ```
8. Open:
   - `http://localhost:8000`

## Docker setup

1. Build and run with PostgreSQL:
   ```powershell
   docker compose up --build
   ```
2. Open:
   - `http://localhost:8000`

## Testing and security checks

- Run tests:
  ```powershell
  pip install -r backend/requirements-dev.txt
  pytest -q
  ```
- Run static security scan:
  ```powershell
  pip install -r backend/requirements-dev.txt
  bandit -q -r backend/app
  ```

## Architecture docs

- System design: [SYSTEM_DESIGN.md](./SYSTEM_DESIGN.md)
- Architecture diagrams: [ARCHITECTURE_DIAGRAM.md](./ARCHITECTURE_DIAGRAM.md)

## Notes

- Product catalog is seeded automatically on first startup.
- For production deployment, use strong `SECRET_KEY`, `ADMIN_API_KEY`, `POSTGRES_PASSWORD`, and `DATABASE_URL` values, set `ADMIN_EMAILS`, set strict `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`, and deploy behind HTTPS reverse proxy.
- Runtime defaults to one Gunicorn worker so the in-memory rate limiter is not silently bypassed across worker processes. Move rate limiting to Redis or another shared store before increasing workers.
- Set `TRUST_X_FORWARDED_FOR=true` only when app runs behind a trusted reverse proxy that sanitizes forwarding headers.
