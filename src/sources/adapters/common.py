from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

_PERCENT_RE = re.compile(r"(?:до\s*)?[-−]?\s*(\d{1,3})\s*%", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"[-−]?\s*(\d[\d\s]{0,8})\s*(?:₽|руб(?:\.|лей)?)", re.IGNORECASE)
_DATE_RE = re.compile(r"(?:до\s*)?(\d{2})\.(\d{2})\.(\d{4})")
_CODE_TOKEN_RE = re.compile(r"^[A-Za-zА-Яа-я0-9_-]{4,40}$")
_CODE_LABEL_RE = re.compile(
    r"(?:промо(?:код|\s*код)|promo\s*code|coupon\s*code|код)\s*[:—-]?\s*"
    r"([A-Za-zА-Яа-я0-9_-]{4,40})",
    re.IGNORECASE,
)
_JSON_CODE_RE = re.compile(
    r'["\'](?:promocode|promo_code|promoCode|coupon_code|couponCode|code)["\']\s*:\s*'
    r'["\']([A-Za-zА-Яа-я0-9_-]{4,40})["\']',
    re.IGNORECASE,
)
_STOP_CODES = {
    "PROMO", "PROMOCODE", "PROMO_CODE", "COUPON", "CODE", "ПРОМО", "ПРОМОКОД",
    "ПРОМОКОДЫ", "СКИДКА", "ПОКАЗАТЬ", "ОТКРЫТЬ", "COPY", "COPIED",
}


def compact_text(node: Tag) -> str:
    return re.sub(r"\s+", " ", " ".join(node.stripped_strings)).strip()


def closest_card(node: Tag, *, marker: str | None = None, max_chars: int = 1600) -> Tag:
    fallback = node
    for parent in node.parents:
        if not isinstance(parent, Tag):
            continue
        text = compact_text(parent)
        if len(text) > max_chars:
            continue
        fallback = parent
        if parent.name in {"article", "li"}:
            return parent
        if marker and marker.lower() in text.lower() and len(text) >= 20:
            return parent
    return fallback


def parse_percent(text: str) -> Decimal | None:
    match = _PERCENT_RE.search(text)
    if not match:
        return None
    value = int(match.group(1))
    return Decimal(value) if 0 < value <= 100 else None


def parse_amount(text: str) -> Decimal | None:
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    return Decimal(match.group(1).replace(" ", ""))


def parse_valid_until(text: str) -> datetime | None:
    match = _DATE_RE.search(text)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    try:
        return datetime(year, month, day, 23, 59, 59, tzinfo=UTC)
    except ValueError:
        return None


def image_url(card: Tag, base_url: str) -> str | None:
    image = card.find("img")
    if not image:
        return None
    src = image.get("src") or image.get("data-src") or image.get("data-lazy-src")
    return urljoin(base_url, src) if src else None


def external_id(*parts: str | None) -> str:
    payload = "|".join(part or "" for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _valid_code(value: object) -> str | None:
    code = str(value or "").strip().strip('"\'` ')
    if not _CODE_TOKEN_RE.fullmatch(code):
        return None
    if code.upper() in _STOP_CODES:
        return None
    # Ordinary words are too risky unless the site explicitly labels them as a code.
    return code


def extract_revealed_promo_code(html: str) -> str | None:
    """Extract a code from a page/modal returned after a site's reveal action.

    Site integrations use this only on the concrete offer URL, never on a catalogue
    page, so labelled/attribute candidates are authoritative while generic words are
    deliberately ignored.
    """
    soup = BeautifulSoup(html, "html.parser")
    attribute_names = (
        "data-promocode", "data-promo-code", "data-coupon-code", "data-code",
        "data-clipboard-text", "data-copy", "data-copy-text",
    )
    for node in soup.find_all(True):
        for name in attribute_names:
            if node.has_attr(name):
                code = _valid_code(node.get(name))
                if code:
                    return code
        if node.name == "input":
            marker = " ".join(
                str(node.get(name) or "") for name in ("name", "id", "class", "placeholder")
            ).casefold()
            if "promo" in marker or "coupon" in marker or "промо" in marker or "code" in marker:
                code = _valid_code(node.get("value"))
                if code:
                    return code

    raw = str(html)
    match = _JSON_CODE_RE.search(raw)
    if match:
        code = _valid_code(match.group(1))
        if code:
            return code

    text = soup.get_text(" ", strip=True)
    match = _CODE_LABEL_RE.search(text)
    if match:
        return _valid_code(match.group(1))
    return None
