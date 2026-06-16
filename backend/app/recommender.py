from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import CartItem, Order, OrderItem, Product, RecommendationEvent
from .store import normalize_text, product_to_payload

EVENT_WEIGHTS = {
    "view": 1.0,
    "cart": 2.7,
    "purchase": 4.3,
}


def _token_set(product: Product) -> set[str]:
    raw = f"{product.name} {product.brand} {product.category} {product.description}"
    return set(normalize_text(raw).split())


def _token_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a.intersection(tokens_b))
    union = len(tokens_a.union(tokens_b))
    if union == 0:
        return 0.0
    return intersection / union


def _price_similarity(price_a: float, price_b: float) -> float:
    high = max(price_a, price_b, 1.0)
    diff_ratio = abs(price_a - price_b) / high
    return max(0.0, 1.0 - diff_ratio)


def _content_similarity(a: Product, b: Product, tokens_by_id: dict[int, set[str]]) -> float:
    score = 0.0
    if a.category == b.category:
        score += 0.34
    if a.brand == b.brand:
        score += 0.24

    score += 0.24 * _token_similarity(tokens_by_id[a.id], tokens_by_id[b.id])
    score += 0.18 * _price_similarity(float(a.price), float(b.price))
    return score


def _pair_signals_from_orders(db: Session, since: datetime) -> dict[int, dict[int, float]]:
    matrix: dict[int, dict[int, float]] = defaultdict(dict)

    recent_orders = (
        db.query(Order)
        .filter(Order.created_at >= since)
        .order_by(Order.created_at.desc())
        .limit(1000)
        .all()
    )

    for order in recent_orders:
        product_ids = [item.product_id for item in order.order_items]
        unique_ids = list(dict.fromkeys(product_ids))
        for left_index, left_id in enumerate(unique_ids):
            for right_id in unique_ids[left_index + 1 :]:
                matrix[left_id][right_id] = matrix[left_id].get(right_id, 0.0) + 6.0
                matrix[right_id][left_id] = matrix[right_id].get(left_id, 0.0) + 6.0

    return matrix


def _pair_signals_from_events(db: Session, since: datetime) -> dict[int, dict[int, float]]:
    matrix: dict[int, dict[int, float]] = defaultdict(dict)

    events = (
        db.query(RecommendationEvent)
        .filter(RecommendationEvent.created_at >= since)
        .filter(RecommendationEvent.user_id.isnot(None))
        .order_by(RecommendationEvent.created_at.asc())
        .limit(5000)
        .all()
    )

    actor_histories: dict[str, deque[tuple[int, str]]] = defaultdict(deque)

    for event in events:
        actor_id = f"u:{event.user_id}"
        history = actor_histories[actor_id]

        for index, (other_id, other_event) in enumerate(reversed(history), start=1):
            if other_id == event.product_id:
                continue

            decay = 1.0 / (1.0 + (index * 0.22))
            signal = EVENT_WEIGHTS.get(event.event_type, 1.0) * EVENT_WEIGHTS.get(other_event, 1.0) * decay

            matrix[other_id][event.product_id] = matrix[other_id].get(event.product_id, 0.0) + signal
            matrix[event.product_id][other_id] = matrix[event.product_id].get(other_id, 0.0) + signal

        history.append((event.product_id, event.event_type))
        while len(history) > 25:
            history.popleft()

    return matrix


def _merge_pair_matrices(*matrices: dict[int, dict[int, float]]) -> dict[int, dict[int, float]]:
    merged: dict[int, dict[int, float]] = defaultdict(dict)
    for matrix in matrices:
        for left_id, neighbors in matrix.items():
            for right_id, value in neighbors.items():
                merged[left_id][right_id] = merged[left_id].get(right_id, 0.0) + value
    return merged


def _normalized_collab(pair_signals: dict[int, dict[int, float]], seed_id: int, candidate_id: int) -> float:
    raw = pair_signals.get(seed_id, {}).get(candidate_id, 0.0)
    return raw / (10.0 + raw)


def record_interaction(
    db: Session,
    product_id: int,
    event_type: str,
    user_id: Optional[int] = None,
    session_id: Optional[str] = None,
) -> None:
    if event_type not in EVENT_WEIGHTS:
        return

    event = RecommendationEvent(
        user_id=user_id,
        session_id=session_id,
        product_id=product_id,
        event_type=event_type,
    )
    db.add(event)


def record_purchase_batch(db: Session, user_id: int, product_ids: list[int]) -> None:
    unique_ids = list(dict.fromkeys([product_id for product_id in product_ids if product_id]))
    for product_id in unique_ids:
        record_interaction(db=db, product_id=product_id, event_type="purchase", user_id=user_id)


def track_view_event(db: Session, product_id: int, user_id: Optional[int], session_id: Optional[str]) -> None:
    record_interaction(db=db, product_id=product_id, event_type="view", user_id=user_id, session_id=session_id)


def track_cart_event(db: Session, product_id: int, user_id: int) -> None:
    record_interaction(db=db, product_id=product_id, event_type="cart", user_id=user_id)


def _collect_seed_weights(db: Session, user_id: Optional[int], session_id: Optional[str]) -> Counter[int]:
    seed_weights: Counter[int] = Counter()
    now = datetime.utcnow()

    if user_id is not None:
        cart_items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
        for item in cart_items:
            seed_weights[item.product_id] += 2.8 * max(1, item.quantity)

        recent_orders = (
            db.query(Order)
            .filter(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .limit(8)
            .all()
        )
        for order in recent_orders:
            for item in order.order_items:
                seed_weights[item.product_id] += 3.0

    event_query = db.query(RecommendationEvent).order_by(RecommendationEvent.created_at.desc())
    if user_id is not None:
        event_query = event_query.filter(RecommendationEvent.user_id == user_id)
    elif session_id:
        event_query = event_query.filter(RecommendationEvent.session_id == session_id)
    else:
        return seed_weights

    events = event_query.limit(60).all()
    for index, event in enumerate(events):
        age_minutes = max(0.0, (now - event.created_at).total_seconds() / 60.0)
        recency_decay = 1.0 / (1.0 + (age_minutes / 120.0))
        rank_decay = 1.0 / (1.0 + (index * 0.08))
        seed_weights[event.product_id] += EVENT_WEIGHTS.get(event.event_type, 1.0) * recency_decay * rank_decay

    return seed_weights


def _popularity_scores(products: list[Product], db: Session, since: datetime) -> dict[int, float]:
    popularity: dict[int, float] = {}

    purchase_counts = dict(
        db.query(OrderItem.product_id, func.count(OrderItem.id))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.created_at >= since)
        .group_by(OrderItem.product_id)
        .all()
    )

    event_counts = dict(
        db.query(RecommendationEvent.product_id, func.count(RecommendationEvent.id))
        .filter(RecommendationEvent.created_at >= since)
        .filter(RecommendationEvent.user_id.isnot(None))
        .group_by(RecommendationEvent.product_id)
        .all()
    )

    for product in products:
        base = (float(product.reviews) / 180.0) + (float(product.rating) * 1.8)
        if product.is_new:
            base += 1.5
        base += 0.7 * float(purchase_counts.get(product.id, 0))
        base += 0.2 * float(event_counts.get(product.id, 0))
        popularity[product.id] = max(1.0, base)

    max_popularity = max(popularity.values()) if popularity else 1.0
    for product_id in list(popularity.keys()):
        popularity[product_id] = popularity[product_id] / max_popularity

    return popularity


def get_recommendations(
    db: Session,
    user_id: Optional[int] = None,
    session_id: Optional[str] = None,
    context_product_id: Optional[int] = None,
    limit: int = 12,
) -> list[dict]:
    limit = max(1, min(limit, 40))
    products = db.query(Product).filter(Product.is_active.is_(True)).all()
    if not products:
        return []

    products_by_id = {product.id: product for product in products}
    tokens_by_id = {product.id: _token_set(product) for product in products}

    since = datetime.utcnow() - timedelta(days=120)
    pair_signals = _merge_pair_matrices(
        _pair_signals_from_orders(db, since),
        _pair_signals_from_events(db, since),
    )

    seed_weights = _collect_seed_weights(db, user_id=user_id, session_id=session_id)
    if context_product_id in products_by_id:
        seed_weights[context_product_id] += 3.6

    seen_ids = set(seed_weights.keys())
    popularity = _popularity_scores(products, db, since)

    scored: list[tuple[float, int, float, int]] = []
    for candidate in products:
        if candidate.id in seen_ids:
            continue

        score = 0.0
        for seed_id, seed_weight in seed_weights.items():
            seed_product = products_by_id.get(seed_id)
            if seed_product is None:
                continue

            content = _content_similarity(seed_product, candidate, tokens_by_id)
            collab = _normalized_collab(pair_signals, seed_id, candidate.id)
            score += seed_weight * ((0.56 * collab) + (0.34 * content))

        if context_product_id and context_product_id in products_by_id:
            context_product = products_by_id[context_product_id]
            score += 1.8 * _content_similarity(context_product, candidate, tokens_by_id)
            score += 2.2 * _normalized_collab(pair_signals, context_product_id, candidate.id)

        score += 0.9 * popularity.get(candidate.id, 0.0)
        score += 0.08 * float(candidate.rating)

        scored.append((score, int(candidate.reviews), float(candidate.rating), candidate.id))

    scored.sort(key=lambda row: (row[0], row[1], row[2], row[3]), reverse=True)

    if not scored:
        fallback = sorted(products, key=lambda product: (popularity.get(product.id, 0.0), product.reviews, product.rating), reverse=True)
        return [product_to_payload(product) for product in fallback[:limit]]

    top_ids = [row[3] for row in scored[:limit]]
    return [product_to_payload(products_by_id[product_id]) for product_id in top_ids]


def get_similar_products(db: Session, product_id: int, limit: int = 8) -> list[dict]:
    limit = max(1, min(limit, 24))
    products = db.query(Product).filter(Product.is_active.is_(True)).all()
    products_by_id = {product.id: product for product in products}

    anchor = products_by_id.get(product_id)
    if anchor is None:
        return []

    tokens_by_id = {product.id: _token_set(product) for product in products}
    since = datetime.utcnow() - timedelta(days=120)
    pair_signals = _merge_pair_matrices(
        _pair_signals_from_orders(db, since),
        _pair_signals_from_events(db, since),
    )
    popularity = _popularity_scores(products, db, since)

    scored: list[tuple[float, int, float, int]] = []
    for candidate in products:
        if candidate.id == product_id:
            continue

        content = _content_similarity(anchor, candidate, tokens_by_id)
        collab = _normalized_collab(pair_signals, product_id, candidate.id)
        pop = popularity.get(candidate.id, 0.0)
        score = (0.58 * content) + (0.32 * collab) + (0.10 * pop)
        scored.append((score, int(candidate.reviews), float(candidate.rating), candidate.id))

    scored.sort(key=lambda row: (row[0], row[1], row[2], row[3]), reverse=True)
    return [product_to_payload(products_by_id[row[3]]) for row in scored[:limit]]


def reset_recommendation_state() -> None:
    # DB-backed recommendation state is persisted and doesn't use in-memory caches.
    return
