from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product
from ..rate_limit import CATALOG_LIMIT, SEARCH_LIMIT, get_client_identifier, rate_limiter
from ..seed_data import HERO_BANNERS
from ..store import apply_sort, product_to_payload, search_products

router = APIRouter(prefix="/api", tags=["Catalog"])

ALLOWED_SORTS = {"trending", "price_asc", "price_desc", "rating", "newest", "relevance"}


@router.get("/products")
def list_products(
    request: Request,
    q: Optional[str] = Query(default=None, max_length=80),
    category: Optional[str] = Query(default=None, max_length=40),
    sort: str = Query(default="trending", max_length=20),
    limit: int = Query(default=60, ge=1, le=120),
    offset: int = Query(default=0, ge=0, le=10000),
    db: Session = Depends(get_db),
):
    identifier = get_client_identifier(request)
    rate_limiter.enforce("catalog", identifier, CATALOG_LIMIT)

    requested_sort = sort.lower()
    if requested_sort not in ALLOWED_SORTS:
        requested_sort = "trending"

    query = (q or "").strip()
    selected_category = (category or "").strip()

    if query:
        products = [
            product_to_payload(product)
            for product in db.query(Product).filter(Product.is_active.is_(True)).all()
        ]
        filtered = search_products(products=products, query=query, category=selected_category, limit=200)
        if query and requested_sort in {"relevance", "trending"}:
            sorted_products = filtered
        else:
            sorted_products = apply_sort(filtered, requested_sort)

        return {
            "count": len(sorted_products[offset : offset + limit]),
            "total_count": len(sorted_products),
            "limit": limit,
            "offset": offset,
            "products": sorted_products[offset : offset + limit],
        }

    products_query = db.query(Product).filter(Product.is_active.is_(True))

    if selected_category and selected_category.lower() != "all":
        products_query = products_query.filter(Product.category.ilike(selected_category))

    if requested_sort == "price_asc":
        products_query = products_query.order_by(Product.price.asc(), Product.id.desc())
    elif requested_sort == "price_desc":
        products_query = products_query.order_by(Product.price.desc(), Product.id.desc())
    elif requested_sort == "rating":
        products_query = products_query.order_by(Product.rating.desc(), Product.reviews.desc(), Product.id.desc())
    elif requested_sort == "newest":
        products_query = products_query.order_by(Product.is_new.desc(), Product.id.desc())
    else:
        products_query = products_query.order_by(Product.reviews.desc(), Product.rating.desc(), Product.id.desc())

    total_count = products_query.count()
    sorted_products = [
        product_to_payload(product)
        for product in products_query.offset(offset).limit(limit).all()
    ]
    return {
        "count": len(sorted_products),
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "products": sorted_products,
    }


@router.get("/products/search")
def search_products_endpoint(
    request: Request,
    q: str = Query(min_length=1, max_length=80),
    category: Optional[str] = Query(default=None, max_length=40),
    limit: int = Query(default=12, ge=1, le=40),
    db: Session = Depends(get_db),
):
    identifier = get_client_identifier(request)
    rate_limiter.enforce("search", identifier, SEARCH_LIMIT)

    products = [product_to_payload(product) for product in db.query(Product).filter(Product.is_active.is_(True)).all()]

    query = q.strip()
    selected_category = (category or "").strip()
    results = search_products(products=products, query=query, category=selected_category, limit=limit)

    return {
        "query": query,
        "count": len(results),
        "products": results,
    }


@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id, Product.is_active.is_(True)).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product_to_payload(product)


@router.get("/categories")
def list_categories(request: Request, db: Session = Depends(get_db)):
    identifier = get_client_identifier(request)
    rate_limiter.enforce("catalog", identifier, CATALOG_LIMIT)

    products = db.query(Product).filter(Product.is_active.is_(True)).all()

    counts: dict[str, int] = {}
    for product in products:
        counts[product.category] = counts.get(product.category, 0) + 1

    categories = [{"name": "All", "count": len(products)}]
    categories.extend(
        [{"name": name, "count": count} for name, count in sorted(counts.items(), key=lambda entry: entry[0])]
    )
    return {"categories": categories}


@router.get("/hero-banners")
def list_hero_banners(request: Request):
    identifier = get_client_identifier(request)
    rate_limiter.enforce("catalog", identifier, CATALOG_LIMIT)
    return {"banners": HERO_BANNERS}
