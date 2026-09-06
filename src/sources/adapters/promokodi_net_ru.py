from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.sources.adapters.common import closest_card, compact_text, external_id, extract_revealed_promo_code, image_url, parse_amount, parse_percent
from src.sources.base import RawOffer
from src.sources.http import HttpClient

_ACTION_RE = re.compile(r"открыть\s+промокод", re.IGNORECASE)
_TITLE_RE = re.compile(r"скид|подар|бесплат|промокод|сертификат", re.IGNORECASE)


class PromokodiNetRuAdapter:
    key = "promokodi_net_ru"

    def __init__(self, base_url: str, client: HttpClient | None = None) -> None:
        self.base_url = base_url
        self.client = client or HttpClient()

    def collect(self) -> list[RawOffer]:
        offers = self.parse(self.client.get_text(self.base_url))
        page_cache: dict[str, str | None] = {}
        for offer in offers:
            if offer.promo_code or not offer.source_url or offer.source_url == self.base_url:
                continue
            if offer.source_url not in page_cache:
                try:
                    detail_html = self.client.get_text(offer.source_url)
                    page_cache[offer.source_url] = extract_revealed_promo_code(detail_html)
                except Exception:
                    page_cache[offer.source_url] = None
            offer.promo_code = page_cache[offer.source_url]
            payload = dict(offer.raw_payload or {})
            payload["detail_followed"] = True
            payload["reveal_status"] = "success" if offer.promo_code else "not_found"
            offer.raw_payload = payload
        return offers

    def parse(self, html: str) -> list[RawOffer]:
        soup = BeautifulSoup(html, "html.parser")
        offers: list[RawOffer] = []
        seen: set[str] = set()
        for action in soup.find_all(["a", "button"]):
            action_text = action.get_text(" ", strip=True)
            if not _ACTION_RE.search(action_text):
                continue
            card = closest_card(action, max_chars=1800)
            text = compact_text(card)
            title = self._title(card, text)
            if not title:
                continue
            href = action.get("href") if isinstance(action, Tag) else None
            source_url = urljoin(self.base_url, href) if href else self.base_url
            merchant = self._merchant(card, text)
            ext_id = external_id(source_url, merchant, title)
            if ext_id in seen:
                continue
            seen.add(ext_id)
            percent = parse_percent(text)
            amount = None if percent is not None else parse_amount(text)
            offers.append(
                RawOffer(
                    source_key=self.key,
                    external_id=ext_id,
                    title=title[:300],
                    source_url=source_url,
                    merchant=merchant,
                    description=text[:2000],
                    discount_percent=percent,
                    discount_amount=amount,
                    image_url=image_url(card, self.base_url),
                    raw_payload={"text": text},
                )
            )
        return offers

    def _title(self, card: Tag, text: str) -> str | None:
        for heading in card.find_all(["h2", "h3", "h4"]):
            value = heading.get_text(" ", strip=True)
            if _TITLE_RE.search(value) and "недавно" not in value.lower():
                return value
        candidates = [part.strip() for part in re.split(r"\s{2,}|[|]", text) if part.strip()]
        for value in candidates:
            if _TITLE_RE.search(value) and "открыть промокод" not in value.lower():
                return value
        return None

    def _merchant(self, card: Tag, text: str) -> str | None:
        for node in card.find_all(["strong", "b"]):
            value = node.get_text(" ", strip=True)
            match = re.search(r"(?:от|для)\s+(.+)$", value, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:120]
        match = re.search(r"\bот\s+([A-Za-zА-Яа-я0-9. -]{2,50})", text, re.IGNORECASE)
        return match.group(1).strip(" .-—")[:120] if match else None
