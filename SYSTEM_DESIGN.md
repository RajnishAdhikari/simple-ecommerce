# System Design

## Goals

- Low-latency product browsing and search
- Secure authentication and state-changing API operations
- Persistent transactional commerce data
- Personalized recommendation serving
- Containerized deployment with reproducible environments

## Core components

- **Web Client**
  - Interactive SPA-like frontend (`frontend/index.html`, `frontend/assets/app.js`, `frontend/assets/styles.css`)
- **API Layer**
  - FastAPI routers for auth, catalog, cart/checkout, and recommendations
- **Data Layer**
  - PostgreSQL via SQLAlchemy ORM
- **Recommendation Engine**
  - Hybrid scoring with collaborative signals + content similarity + popularity prior
- **Security Controls**
  - JWT auth, rate limiting, strict headers, input validation, host/CORS restrictions

## Data model summary

- `users`
- `products`
- `cart_items`
- `orders`
- `order_items`
- `recommendation_events`

## Request flow (example: checkout)

1. Client adds items to cart (`POST /api/cart/items`)
2. API validates user/product options and persists `cart_items`
3. Client submits checkout (`POST /api/checkout`)
4. API creates `orders` + `order_items`, clears cart, records recommendation purchase events
5. Client fetches refreshed recommendations (`GET /api/recommendations`)

## Scalability direction

- Introduce Redis for distributed rate limiting/session caching
- Move recommendation pair-signal computation to background jobs
- Add async task queue for analytics and recommendation precomputation
- Use read replicas for catalog/search-heavy traffic

## Reliability and operations

- Health endpoint: `GET /api/health`
- Docker Compose service healthcheck for PostgreSQL
- Idempotent startup seeding for catalog products
- Environment-driven configuration via `.env`
