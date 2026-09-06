from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.core.validity import extract_valid_until
from src.modules.source_registry.promko_reveal import PromkoRevealError, reveal_promko_code
from src.sources.adapters.common import compact_text, external_id, image_url, parse_percent
from src.sources.base import RawOffer
from src.sources.http import HttpClient

_SUMMARY_RE = re.compile(r"^(.+?)\s*до\s*(\d{1,3})\s*%$", re.IGNORECASE)


class PromkoAdapter:
    key = "promko"

    def __init__(self, base_url: str, client: HttpClient | None = None) -> None:
        self.base_url = base_url
        self.client = client or HttpClient()

    def collect(self) -> list[RawOffer]:
        offers = self.parse(self.client.get_text(self.base_url))
        for offer in offers:
            payload = dict(offer.raw_payload or {})
            coupon_id = str(payload.get("promko_coupon_id") or "").strip()
            if offer.promo_code or not coupon_id or not payload.get("needs_reveal"):
                continue
            try:
                offer.promo_code = reveal_promko_code(
                    coupon_id,
                    referer=offer.source_url or self.base_url,
                    route=self.client.network_policy,
                    timeout=self.client.timeout_seconds,
                )
                payload["needs_reveal"] = False
                payload["reveal_status"] = "success"
            except (PromkoRevealError, Exception) as exc:
                # A single upstream reveal failure must not discard the rest of the page.
                payload["reveal_status"] = "failed"
                payload["reveal_error"] = f"{type(exc).__name__}: {exc}"[:500]
            offer.raw_payload = payload
        return offers

    @staticmethod
    def _coupon_id(card: Tag) -> str | None:
        node = card.find(attrs={"data-coupon-id": True})
        value = str(node.get("data-coupon-id") or "").strip() if node else ""
        return value if value.isdigit() else None

    @staticmethod
    def _card(node: Tag) -> Tag:
        for parent in node.parents:
            if isinstance(parent, Tag) and parent.name in {"article", "li"}:
                return parent
        return node.parent if isinstance(node.parent, Tag) else node

    def parse(self, html: str) -> list[RawOffer]:
        soup = BeautifulSoup(html, "html.parser")
        offers: list[RawOffer] = []
        seen: set[str] = set()
        actions = soup.find_all(attrs={"data-coupon-id": True})
        for node in actions:
            card = self._card(node)
            text = compact_text(card)
            coupon_id = self._coupon_id(card)
            code = str(node.get("data-promocode") or node.get("data-promo-code") or "").strip() or None
            if code and re.fullmatch(r"[•*\s]+", code):
                code = None
            heading = card.find(["h1", "h2", "h3", "h4"])
            title = compact_text(heading) if heading else text[:300]
            link = card.find("a", href=True)
            source_url = urljoin(self.base_url, str(link.get("href"))) if link else self.base_url
            offer_id = f"promko-coupon:{coupon_id}" if coupon_id else external_id(source_url, title, text)
            if not text or offer_id in seen:
                continue
            seen.add(offer_id)
            offers.append(RawOffer(source_key=self.key, external_id=offer_id, title=title, source_url=source_url,
                description=text[:2000], promo_code=code, discount_percent=parse_percent(text), image_url=image_url(card, self.base_url),
                valid_until=extract_valid_until(text), raw_payload={"text": text, "promko_coupon_id": coupon_id, "needs_reveal": bool(coupon_id and not code)}))
        if offers:
            return offers
        for anchor in soup.find_all("a", href=True):
            text = compact_text(anchor); match = _SUMMARY_RE.match(text)
            if not match:
                continue
            merchant = match.group(1).strip(" :-—"); percent = parse_percent(text)
            if not merchant or percent is None:
                continue
            source_url = urljoin(self.base_url, str(anchor.get("href"))); ext_id = external_id(source_url, merchant, str(percent))
            if ext_id in seen:
                continue
            seen.add(ext_id)
            offers.append(RawOffer(source_key=self.key, external_id=ext_id, title=f"Скидка до {int(percent)}% в {merchant}", source_url=source_url, merchant=merchant, description=text, discount_percent=percent, raw_payload={"text": text, "summary": True, "promko_coupon_id": None, "needs_reveal": False}))
        return offers
