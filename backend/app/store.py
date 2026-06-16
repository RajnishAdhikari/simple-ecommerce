from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher

from .models import Product, User

_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9 ]")
_MULTI_SPACE_PATTERN = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    lowered = value.lower().strip()
    cleaned = _NON_ALNUM_PATTERN.sub(" ", lowered)
    return _MULTI_SPACE_PATTERN.sub(" ", cleaned).strip()


def safe_user_profile(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
    }


def product_to_payload(product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "brand": product.brand,
        "description": product.description,
        "price": product.price,
        "original_price": product.original_price,
        "rating": product.rating,
        "reviews": product.reviews,
        "category": product.category,
        "badge": product.badge,
        "is_new": product.is_new,
        "colors": product.colors or [],
        "sizes": product.sizes or [],
        "image": product.image,
    }


def apply_sort(items: list[dict], sort: str) -> list[dict]:
    if sort == "price_asc":
        return sorted(items, key=lambda item: item["price"])
    if sort == "price_desc":
        return sorted(items, key=lambda item: item["price"], reverse=True)
    if sort == "rating":
        return sorted(items, key=lambda item: item["rating"], reverse=True)
    if sort == "newest":
        return sorted(items, key=lambda item: (item["is_new"], item["id"]), reverse=True)
    return sorted(items, key=lambda item: (item["reviews"], item["rating"]), reverse=True)


def _prepare_search(products: list[dict]):
    records: dict[int, dict] = {}
    prefix_index: dict[str, set[int]] = defaultdict(set)
    trigram_index: dict[str, set[int]] = defaultdict(set)
    products_map: dict[int, dict] = {}

    for product in products:
        product_id = product["id"]
        products_map[product_id] = product

        name_norm = normalize_text(product["name"])
        brand_norm = normalize_text(product["brand"])
        category_norm = normalize_text(product["category"])
        description_norm = normalize_text(product["description"])

        combined = f"{name_norm} {brand_norm} {category_norm} {description_norm}".strip()
        tokens = set(combined.split())

        records[product_id] = {
            "name": name_norm,
            "brand": brand_norm,
            "category": category_norm,
            "description": description_norm,
            "tokens": tokens,
        }

        for token in tokens:
            if len(token) < 2:
                continue
            for length in range(2, min(len(token), 5) + 1):
                prefix_index[token[:length]].add(product_id)

        trigram_source = f"{name_norm} {brand_norm}".strip()
        if len(trigram_source) >= 3:
            for index in range(len(trigram_source) - 2):
                trigram = trigram_source[index : index + 3]
                if " " not in trigram:
                    trigram_index[trigram].add(product_id)

    return records, prefix_index, trigram_index, products_map


def _search_score(record: dict, query_norm: str, query_tokens: list[str]) -> int:
    score = 0

    name = record["name"]
    brand = record["brand"]
    category = record["category"]

    if query_norm == name:
        score += 280
    if name.startswith(query_norm):
        score += 180
    if query_norm in name:
        score += 140
    if query_norm in brand:
        score += 85
    if query_norm in category:
        score += 55

    token_hits = sum(1 for token in query_tokens if token in record["tokens"])
    score += token_hits * 36

    if query_tokens and all(token in record["tokens"] for token in query_tokens):
        score += 80

    for token in query_tokens:
        if any(indexed_token.startswith(token) for indexed_token in record["tokens"]):
            score += 12

    score += int(SequenceMatcher(None, query_norm, name).ratio() * 65)
    return score


def search_products(products: list[dict], query: str = "", category: str = "", limit: int = 60) -> list[dict]:
    query_norm = normalize_text(query)
    category_norm = normalize_text(category)
    category_filter = category_norm if category_norm and category_norm != "all" else ""

    if limit <= 0:
        return []

    if not query_norm:
        filtered = products
        if category_filter:
            filtered = [item for item in filtered if normalize_text(item["category"]) == category_filter]
        return apply_sort(filtered, "trending")[:limit]

    records, prefix_index, trigram_index, products_map = _prepare_search(products)

    candidates: set[int] = set()
    token_sets: list[set[int]] = []

    for token in query_norm.split():
        if len(token) < 2:
            continue

        token_ids = set()
        for prefix_size in range(min(len(token), 5), 1, -1):
            prefix = token[:prefix_size]
            indexed = prefix_index.get(prefix)
            if indexed:
                token_ids.update(indexed)
                break

        if token_ids:
            token_sets.append(token_ids)

    if token_sets:
        candidates.update(set.intersection(*token_sets))
        for token_set in token_sets:
            candidates.update(token_set)

    if len(query_norm) >= 3:
        trigrams = [query_norm[i : i + 3] for i in range(len(query_norm) - 2) if " " not in query_norm[i : i + 3]]
        scored_candidates: dict[int, int] = defaultdict(int)

        for trigram in trigrams:
            for product_id in trigram_index.get(trigram, set()):
                scored_candidates[product_id] += 1

        threshold = max(1, len(trigrams) // 4)
        candidates.update(product_id for product_id, score in scored_candidates.items() if score >= threshold)

    if not candidates:
        candidates = set(products_map.keys())

    query_tokens = [token for token in query_norm.split() if token]
    ranked = []

    for product_id in candidates:
        product = products_map[product_id]
        if category_filter and normalize_text(product["category"]) != category_filter:
            continue

        score = _search_score(records[product_id], query_norm, query_tokens)
        if score <= 0:
            continue

        ranked.append((score, product["reviews"], product["rating"], product_id))

    ranked.sort(key=lambda row: (row[0], row[1], row[2], row[3]), reverse=True)
    return [products_map[row[3]] for row in ranked[:limit]]
