from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from ..content_generator import build_product_content
from ..database import get_db
from ..models import Product
from ..schemas import AdminProductCreateRequest, ProductContentRequest
from ..security import require_admin_key, require_admin_user
from ..store import product_to_payload

router = APIRouter(prefix="/api/admin", tags=["Admin Content"])

DEFAULT_PRODUCT_IMAGE_URL = (
    "https://images.unsplash.com/photo-1523275335684-37898b6baf30"
    "?auto=format&fit=crop&w=900&q=80"
)


@router.get("/products/dashboard")
def get_dashboard_products(
    category: Optional[str] = Query(default=None),
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_db),
):
    query = db.query(Product).filter(Product.is_active == True)  # noqa: E712
    if category and category != "All":
        query = query.filter(Product.category == category)
    products = query.order_by(Product.category, Product.name).all()

    all_categories = (
        db.query(Product.category)
        .filter(Product.is_active == True)  # noqa: E712
        .distinct()
        .all()
    )
    categories = sorted({row.category for row in all_categories})

    result = []
    for product in products:
        content = build_product_content({
            "name": product.name,
            "brand": product.brand,
            "category": product.category,
            "description": product.description,
            "price": product.price,
            "original_price": product.original_price,
            "colors": product.colors or [],
            "sizes": product.sizes or [],
        })
        result.append({
            "product": product_to_payload(product),
            "description": content["description"],
            "social_content": content["social_media_formats"],
        })

    return {"products": result, "total": len(result), "categories": categories}


@router.post("/products/content-preview")
def preview_product_content(payload: ProductContentRequest, admin_user: dict = Depends(require_admin_user)):
    return build_product_content(payload.model_dump())


@router.post("/products", status_code=status.HTTP_201_CREATED)
def create_product(
    payload: AdminProductCreateRequest,
    admin_user: dict = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    generated_content = build_product_content(payload.model_dump())
    description = payload.description or generated_content["description"]

    product = Product(
        name=payload.name,
        brand=payload.brand or "Unbranded",
        description=description,
        price=float(payload.price),
        original_price=float(payload.original_price or payload.price),
        rating=float(payload.rating),
        reviews=int(payload.reviews),
        category=payload.category,
        badge=payload.badge or "",
        is_new=payload.is_new,
        colors=payload.colors,
        sizes=payload.sizes,
        image=payload.image or DEFAULT_PRODUCT_IMAGE_URL,
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    generated_content["description"] = description
    return {
        "product": product_to_payload(product),
        "generated_content": generated_content,
        "created_by": admin_user["email"],
    }
