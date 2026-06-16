# Architecture Diagram

## High-Level Architecture

```mermaid
flowchart LR
    Shopper["Shopper Browser"] -->|HTTPS| Proxy["Reverse Proxy / Load Balancer"]
    Admin["Admin Operator"] -->|HTTPS + Cookie + X-Admin-API-Key| Proxy

    Proxy --> App["FastAPI App\nGunicorn + Uvicorn\n1 worker unless distributed rate limit is added"]

    App --> Static["Frontend Static Files\nindex.html / assets"]
    App --> API["API Routers"]
    App --> Security["Security Middleware\nTrustedHost / CORS / CSP / headers"]

    API --> Auth["Auth Router\nregister / login / logout / me"]
    API --> Catalog["Catalog Router\nproducts / search / categories / banners"]
    API --> Cart["Cart & Checkout Router\ncart items / orders"]
    API --> Reco["Recommendations Router\npersonalized and similar products"]
    API --> AdminAPI["Admin Router\nproduct create / content preview"]

    Auth --> Cookie["HttpOnly Session Cookie\nJWT fallback via Authorization header"]
    AdminAPI --> AdminGuard["Admin Guard\nactive user + ADMIN_EMAILS + API key"]
    AdminAPI --> ContentGen["Content Generator\ndescription + social media formats"]

    Catalog --> Store["Store/Search Helpers\nbounded list responses"]
    Reco --> RecoEngine["Recommendation Engine\ncontent + authenticated events + popularity"]
    Cart --> RecoEngine

    Auth --> DB[(PostgreSQL)]
    Catalog --> DB
    Cart --> DB
    Reco --> DB
    AdminAPI --> DB
```

## Container Architecture

```mermaid
flowchart TB
    Client["Browser"] -->|http://localhost:8000 or HTTPS in production| Web

    subgraph DockerHost["Docker Host"]
      Web["web container\nPython 3.12 FastAPI\nGunicorn/Uvicorn"]
      Db["db container\nPostgreSQL 16"]
      Volume["postgres_data volume"]
    end

    Web -->|SQLAlchemy / psycopg2| Db
    Db --> Volume

    Env["Required environment\nDATABASE_URL\nSECRET_KEY\nADMIN_API_KEY\nADMIN_EMAILS\nPOSTGRES_PASSWORD\nALLOWED_HOSTS\nCORS_ALLOWED_ORIGINS"] --> Web
    Env --> Db
```

## Backend Module Diagram

```mermaid
flowchart TB
    Main["backend.app.main"] --> Middleware["Security + static-file middleware"]
    Main --> Routers["Routes"]
    Main --> Startup["Startup\nvalidate secrets\ncreate tables\nseed products"]

    Routers --> Auth["routes/auth.py"]
    Routers --> Admin["routes/admin.py"]
    Routers --> Catalog["routes/catalog.py"]
    Routers --> Cart["routes/cart.py"]
    Routers --> Recommendations["routes/recommendations.py"]

    Auth --> Security["security.py\nJWT/cookie auth\nactive-user checks"]
    Admin --> Security
    Admin --> ContentGenerator["content_generator.py"]

    Catalog --> Store["store.py\npayloads/search/sort"]
    Cart --> Recommender["recommender.py"]
    Recommendations --> Recommender

    Auth --> Schemas["schemas.py"]
    Admin --> Schemas
    Cart --> Schemas
    Recommendations --> Schemas

    Security --> RateLimit["rate_limit.py"]
    Catalog --> RateLimit
    Cart --> RateLimit
    Recommendations --> RateLimit

    Store --> Models["models.py"]
    Recommender --> Models
    Auth --> Models
    Admin --> Models
    Cart --> Models

    Models --> Database["database.py\nSQLAlchemy engine/session"]
```

## Admin Content Flow

```mermaid
sequenceDiagram
    participant Admin as Admin Browser / Backend Tool
    participant API as FastAPI Admin Router
    participant Sec as Admin Guard
    participant Gen as Content Generator
    participant DB as PostgreSQL

    Admin->>API: POST /api/admin/products/content-preview
    API->>Sec: Validate active auth cookie/JWT
    Sec->>Sec: Check email in ADMIN_EMAILS
    Sec->>Sec: Check X-Admin-API-Key
    API->>Gen: Build description and social formats
    Gen-->>API: Entered-only detail lines + captions
    API-->>Admin: Preview payload

    Admin->>API: POST /api/admin/products
    API->>Sec: Repeat admin authorization
    API->>Gen: Generate description if omitted
    API->>DB: Insert product
    API-->>Admin: Product + generated social content
```

## Authentication And Checkout Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI
    participant D as PostgreSQL

    C->>A: POST /api/auth/register or /api/auth/login
    A->>D: Create/read active user
    A-->>C: Auth response + HttpOnly session cookie

    C->>A: POST /api/cart/items
    A->>A: Resolve current user from cookie/JWT
    A->>D: Validate active user and product options
    A->>D: Upsert cart item + record cart event

    C->>A: POST /api/checkout
    A->>D: Create order and order_items
    A->>D: Record purchase events
    A->>D: Clear cart
    A-->>C: Confirmed order
```

## Recommendation Data Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Recommendations API
    participant D as PostgreSQL
    participant R as Recommendation Engine

    C->>A: POST /api/recommendations/track-view
    A->>A: Validate session/user and rate limit
    A->>D: Deduplicate recent view event
    A->>D: Insert recommendation_events(view)

    C->>A: GET /api/recommendations
    A->>D: Read products, cart, orders, authenticated events
    A->>R: Score candidates
    R->>R: Content similarity + purchase/cart signals + popularity
    R-->>A: Ranked product list
    A-->>C: Recommendations
```

## Security Boundaries

```mermaid
flowchart LR
    Internet["Internet"] --> Proxy["HTTPS Reverse Proxy"]
    Proxy --> App["FastAPI App"]

    App --> Headers["Response Security Headers\nCSP / frame denial / nosniff"]
    App --> HostCors["Trusted hosts + strict CORS"]
    App --> Authz["Authorization Checks\nactive users / admin emails / API key"]
    App --> Validation["Pydantic Validation\nlengths / patterns / allowed image hosts"]
    App --> RateLimit["In-Memory Rate Limiting\nsingle-worker deployment"]

    RateLimit -. future .-> Redis["Redis / shared limiter\nrequired before scaling workers"]
```
