import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CartItem, Order, OrderItem, Product, User
from ..rate_limit import CART_LIMIT, get_client_identifier, rate_limiter
from ..recommender import record_purchase_batch, track_cart_event
from ..schemas import AddCartItemRequest, CheckoutRequest, UpdateCartItemRequest
from ..security import get_current_user
from ..store import safe_user_profile

router = APIRouter(prefix="/api", tags=["Cart & Orders"])

ADDRESS_PATTERN = re.compile(r"^[A-Za-z0-9#.,'\-/ ]{6,255}$")


def enforce_cart_rate_limit(request: Request) -> None:
    identifier = get_client_identifier(request)
    rate_limiter.enforce("cart", identifier, CART_LIMIT)


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def build_cart_response(db: Session, user_id: int) -> dict:
    cart_items = (
        db.query(CartItem, Product)
        .join(Product, Product.id == CartItem.product_id)
        .filter(CartItem.user_id == user_id, Product.is_active.is_(True))
        .all()
    )

    detailed_items = []
    subtotal = 0.0

    for cart_item, product in cart_items:
        line_total = round(float(product.price) * cart_item.quantity, 2)
        subtotal += line_total
        detailed_items.append(
            {
                "product_id": product.id,
                "name": product.name,
                "price": float(product.price),
                "quantity": cart_item.quantity,
                "size": cart_item.size,
                "color": cart_item.color,
                "image": product.image,
                "line_total": line_total,
            }
        )

    shipping = 0.0 if subtotal >= 99 or subtotal == 0 else 7.99
    total = round(subtotal + shipping, 2)

    return {
        "items": detailed_items,
        "summary": {
            "subtotal": round(subtotal, 2),
            "shipping": shipping,
            "total": total,
            "item_count": sum(item["quantity"] for item in detailed_items),
        },
    }


@router.get("/users/me")
def get_me(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_cart_rate_limit(request)

    user = _get_user_or_404(db, current_user["id"])
    return safe_user_profile(user)


@router.get("/cart")
def get_cart(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_cart_rate_limit(request)
    _get_user_or_404(db, current_user["id"])
    return build_cart_response(db, current_user["id"])


@router.post("/cart/items", status_code=status.HTTP_201_CREATED)
def add_cart_item(
    payload: AddCartItemRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_cart_rate_limit(request)

    user = _get_user_or_404(db, current_user["id"])
    product = db.query(Product).filter(Product.id == payload.product_id, Product.is_active.is_(True)).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    selected_size = payload.size.strip() if payload.size else None
    selected_color = payload.color.strip() if payload.color else None

    if selected_size and selected_size not in (product.sizes or []):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid product size")
    if selected_color and selected_color not in (product.colors or []):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid product color")

    cart_item = (
        db.query(CartItem)
        .filter(CartItem.user_id == user.id, CartItem.product_id == product.id)
        .first()
    )

    if cart_item:
        cart_item.quantity = min(cart_item.quantity + payload.quantity, 20)
        if selected_size:
            cart_item.size = selected_size
        if selected_color:
            cart_item.color = selected_color
    else:
        cart_item = CartItem(
            user_id=user.id,
            product_id=product.id,
            quantity=payload.quantity,
            size=selected_size,
            color=selected_color,
        )
        db.add(cart_item)

    track_cart_event(db=db, product_id=product.id, user_id=user.id)
    try:
        db.commit()
    except IntegrityError:
        # Handle concurrent inserts for the same (user_id, product_id) unique key.
        db.rollback()
        existing_item = (
            db.query(CartItem)
            .filter(CartItem.user_id == user.id, CartItem.product_id == product.id)
            .first()
        )
        if not existing_item:
            raise
        existing_item.quantity = min(existing_item.quantity + payload.quantity, 20)
        if selected_size:
            existing_item.size = selected_size
        if selected_color:
            existing_item.color = selected_color
        db.commit()

    return build_cart_response(db, user.id)


@router.patch("/cart/items/{product_id}")
def update_cart_item(
    product_id: int,
    payload: UpdateCartItemRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_cart_rate_limit(request)

    _get_user_or_404(db, current_user["id"])
    cart_item = (
        db.query(CartItem)
        .filter(CartItem.user_id == current_user["id"], CartItem.product_id == product_id)
        .first()
    )

    if not cart_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

    cart_item.quantity = payload.quantity
    db.commit()

    return build_cart_response(db, current_user["id"])


@router.delete("/cart/items/{product_id}")
def remove_cart_item(
    product_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_cart_rate_limit(request)

    _get_user_or_404(db, current_user["id"])
    cart_item = (
        db.query(CartItem)
        .filter(CartItem.user_id == current_user["id"], CartItem.product_id == product_id)
        .first()
    )

    if not cart_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

    db.delete(cart_item)
    db.commit()

    return build_cart_response(db, current_user["id"])


@router.post("/checkout")
def checkout(
    payload: CheckoutRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_cart_rate_limit(request)

    user = _get_user_or_404(db, current_user["id"])
    cart_payload = build_cart_response(db, user.id)

    if not cart_payload["items"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")

    shipping_address = " ".join(payload.shipping_address.split())
    if not ADDRESS_PATTERN.fullmatch(shipping_address):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid shipping address")

    order = Order(
        user_id=user.id,
        total_amount=cart_payload["summary"]["total"],
        shipping_address=shipping_address,
        status="confirmed",
        created_at=datetime.utcnow(),
    )
    db.add(order)
    db.flush()

    product_ids = []
    for item in cart_payload["items"]:
        product_ids.append(item["product_id"])
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item["product_id"],
                quantity=item["quantity"],
                price=item["price"],
            )
        )

    record_purchase_batch(db=db, user_id=user.id, product_ids=product_ids)

    db.query(CartItem).filter(CartItem.user_id == user.id).delete()
    db.commit()

    return {
        "message": "Order placed successfully",
        "order": {
            "order_id": order.id,
            "user_id": user.id,
            "shipping_address": shipping_address,
            "items": cart_payload["items"],
            "total": cart_payload["summary"]["total"],
            "created_at": order.created_at.isoformat(),
            "status": order.status,
        },
    }
