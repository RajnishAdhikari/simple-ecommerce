from __future__ import annotations

import re
from typing import Any

CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "NPR": "NPR ",
}

DETAIL_FIELD_LABELS = [
    ("category", "Category"),
    ("product_type", "Product Type"),
    ("brand", "Brand"),
    ("material", "Material"),
    ("pattern", "Pattern"),
    ("condition", "Condition"),
    ("age_group", "Age Group"),
    ("gender", "Gender"),
    ("size_type", "Size Type"),
    ("size_system", "Size System"),
    ("dimensions", "Dimensions"),
    ("weight", "Weight"),
    ("origin", "Origin"),
    ("ingredients", "Ingredients"),
    ("dietary_info", "Dietary Info"),
    ("shelf_life", "Shelf Life"),
    ("storage_instructions", "Storage"),
    ("fit", "Fit"),
    ("care_instructions", "Care"),
    ("craft_method", "Craft Method"),
    ("warranty", "Warranty"),
    ("compatibility", "Compatibility"),
    ("usage", "Best For"),
    ("availability", "Availability"),
]

HASHTAG_PATTERN = re.compile(r"[^A-Za-z0-9]")


def _value(payload: dict[str, Any], key: str):
    value = payload.get(key)
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return value


def _list_value(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key) or []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _money(value: float | None, currency: str) -> str | None:
    if value is None:
        return None
    symbol = CURRENCY_SYMBOLS.get(currency, f"{currency} ")
    return f"{symbol}{float(value):,.2f}"


def _join_list(items: list[str]) -> str | None:
    if not items:
        return None
    return ", ".join(items)


def _detail_lines(payload: dict[str, Any]) -> list[str]:
    currency = _value(payload, "currency") or "USD"
    lines: list[str] = []

    price = _money(_value(payload, "price"), currency)
    original_price = _money(_value(payload, "original_price"), currency)
    if price:
        label = "Offer Price" if original_price and original_price != price else "Price"
        lines.append(f"{label}: {price}")
    if original_price and original_price != price:
        lines.append(f"Regular Price: {original_price}")

    for key, label in DETAIL_FIELD_LABELS:
        value = _value(payload, key)
        if value is not None:
            lines.append(f"{label}: {value}")

    colors = _join_list(_list_value(payload, "colors"))
    if colors:
        lines.append(f"Colors: {colors}")

    sizes = _join_list(_list_value(payload, "sizes"))
    if sizes:
        lines.append(f"Sizes: {sizes}")

    package_contents = _join_list(_list_value(payload, "package_contents"))
    if package_contents:
        lines.append(f"Package Includes: {package_contents}")

    features = _join_list(_list_value(payload, "features"))
    if features:
        lines.append(f"Highlights: {features}")

    handmade = payload.get("handmade")
    if handmade is not None:
        lines.append(f"Handmade: {'Yes' if handmade else 'No'}")

    details = payload.get("details") or {}
    for key, value in details.items():
        if value:
            lines.append(f"{key}: {value}")

    return lines


def _description_from_payload(payload: dict[str, Any]) -> str:
    custom_description = _value(payload, "description")
    if custom_description:
        return custom_description

    name = _value(payload, "name") or "This product"
    product_type = _value(payload, "product_type")
    category = _value(payload, "category")
    brand = _value(payload, "brand")
    material = _value(payload, "material")
    usage = _value(payload, "usage")
    features = _list_value(payload, "features")

    identity_parts = [name]
    if brand:
        identity_parts.append(f"by {brand}")
    identity = " ".join(identity_parts)

    type_phrase = product_type or category or "product"
    first_sentence = f"{identity} is a practical {type_phrase.lower()} option made for everyday use."

    supporting_parts = []
    if material:
        supporting_parts.append(f"made with {material}")
    if usage:
        supporting_parts.append(f"suited for {usage}")
    if features:
        supporting_parts.append(f"featuring {', '.join(features[:3])}")

    if supporting_parts:
        second_sentence = "It is " + ", ".join(supporting_parts) + "."
    else:
        second_sentence = "It keeps the product information clear so customers can quickly understand what is being offered."

    details = _detail_lines(payload)
    if details:
        return f"{first_sentence} {second_sentence} Key details: {'; '.join(details)}."

    return f"{first_sentence} {second_sentence}"


def _hashtags(payload: dict[str, Any]) -> list[str]:
    source_values: list[str] = []
    for key in ("name", "category", "product_type", "brand"):
        value = _value(payload, key)
        if value:
            source_values.append(value)
    source_values.extend(_list_value(payload, "tags"))

    tags: list[str] = []
    seen = set()
    for value in source_values:
        for part in value.split():
            cleaned = HASHTAG_PATTERN.sub("", part).strip()
            if len(cleaned) < 3:
                continue
            tag = f"#{cleaned[:40]}"
            key = tag.lower()
            if key not in seen:
                tags.append(tag)
                seen.add(key)
            if len(tags) >= 12:
                return tags

    fallback_tags = ["#NewArrival", "#ShopNow"]
    for tag in fallback_tags:
        if tag.lower() not in seen:
            tags.append(tag)
    return tags[:12]


def build_product_content(payload: dict[str, Any]) -> dict[str, Any]:
    name = _value(payload, "name") or "Product"
    description = _description_from_payload(payload)
    detail_lines = _detail_lines(payload)
    hashtags = _hashtags(payload)

    detail_block = "\n".join(f"- {line}" for line in detail_lines)
    detail_section = f"\n\nDetails:\n{detail_block}" if detail_block else ""
    hashtag_line = " ".join(hashtags)

    short_caption = f"{name}\n\n{description}{detail_section}\n\nOrder or message us for availability.\n{hashtag_line}".strip()

    facebook_post = (
        f"New product update: {name}\n\n"
        f"{description}"
        f"{detail_section}\n\n"
        "For orders, questions, or availability, contact us directly."
    ).strip()

    whatsapp_message = (
        f"{name}\n"
        f"{description}"
        f"{detail_section}\n\n"
        "Reply here to order or ask for more details."
    ).strip()

    video_script_parts = [
        f"Hook: Introducing {name}.",
        "Shot 1: Show the full product clearly.",
        "Shot 2: Show the most important details customers should see.",
    ]
    if detail_lines:
        video_script_parts.append(f"On-screen text: {' | '.join(detail_lines[:4])}.")
    video_script_parts.append("CTA: Message or order now.")

    return {
        "description": description,
        "detail_lines": detail_lines,
        "social_media_formats": {
            "instagram_caption": short_caption,
            "facebook_post": facebook_post,
            "whatsapp_message": whatsapp_message,
            "short_video_script": "\n".join(video_script_parts),
            "hashtags": hashtags,
        },
    }
