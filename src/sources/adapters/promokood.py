from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from src.sources.base import RawOffer
from src.sources.http import HttpClient
from src.core.validity import extract_valid_until

_PERCENT_RE = re.compile(r"(?:скидк\w*\s*)?(?:до\s*)?(\d{1,3})\s*%", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"(\d[\d\s]{0,8})\s*(?:₽|руб(?:\.|лей)?)", re.IGNORECASE)
_OFFER_WORD_RE = re.compile(r"скидк|промокод|кэшб|кешб|бонус|бесплатно", re.IGNORECASE)
_BENEFIT_START_RE = re.compile(r"\b(?:доп\.?\s*)?(?:скидк\w*|бонус|кэшб\w*|кешб\w*|бесплатно)\b", re.IGNORECASE)
_ACTION_SUFFIX_RE = re.compile(r"\s+(?:активировать|получить|применить|использовать)\s+промокод.*$", re.IGNORECASE)
_CODE_RE = re.compile(r"(?:промокод|код)\s*[:\-–—]?\s*([A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9_-]{3,24})", re.IGNORECASE)
_DETAIL_CODE_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_-]{1,39}$")
_DETAIL_DESCRIPTOR_RE = re.compile(r"^промокод\b", re.IGNORECASE)
_DETAIL_DATE_RE = re.compile(r"^(?:до\s+)?\d{1,2}\.\d{1,2}\.\d{4}$", re.IGNORECASE)
_DETAIL_STOP_RE = re.compile(r"^(?:о сервисе|ключев\w+ преимуществ\w*|mcc-коды|похожие предложения|реклама\.)", re.IGNORECASE)
_DETAIL_CTA_RE = re.compile(r"^(?:активировать|получить|применить|использовать)\s+промокод$", re.IGNORECASE)


class PromokoodAdapter:
    key = "promokood"

    def __init__(self, base_url: str, client: HttpClient | None = None) -> None:
        self.base_url = base_url
        self.client = client or HttpClient()

    def collect(self) -> list[RawOffer]:
        return self.parse(self.client.get_text(self.base_url))

    def parse(self, html: str) -> list[RawOffer]:
        soup = BeautifulSoup(html, "html.parser")

        # Promokood merchant pages are authoritative 1:N containers: a single
        # /o/<merchant> page contains several independent promo codes followed
        # by their benefit, conditions and validity. Parse those records before
        # the historical CTA/card fallback so a whole page can never collapse
        # into one code-less review row.
        if self._is_detail_page():
            detail_offers = self._parse_detail_codes(soup)
            if detail_offers:
                return detail_offers

        offers: list[RawOffer] = []
        seen: set[str] = set()

        for action in soup.find_all(["a", "button"]):
            action_text = action.get_text(" ", strip=True)
            if not action_text or not _OFFER_WORD_RE.search(action_text):
                continue
            card = self._find_card(action)
            card_text = re.sub(r"\s+", " ", " ".join(card.stripped_strings)).strip()
            if len(card_text) < 8:
                continue

            href = action.get("href") if isinstance(action, Tag) else None
            source_url = urljoin(self.base_url, href) if href else self.base_url
            merchant = self._merchant(card, action_text)
            title = self._title(card_text, merchant)
            code_match = _CODE_RE.search(card_text)
            promo_code = code_match.group(1) if code_match else None
            external_id = hashlib.sha256(f"{source_url}|{merchant}|{title}|{promo_code or ''}".encode("utf-8")).hexdigest()[:32]
            if external_id in seen:
                continue
            seen.add(external_id)

            discount_percent = self._discount_percent(card_text)
            discount_amount = self._discount_amount(card_text) if discount_percent is None else None
            image_url = self._image_url(card)

            offers.append(
                RawOffer(
                    source_key=self.key,
                    external_id=external_id,
                    title=title,
                    source_url=source_url,
                    merchant=merchant,
                    description=card_text[:2000],
                    conditions=card_text[:2000],
                    promo_code=promo_code,
                    discount_percent=discount_percent,
                    discount_amount=discount_amount,
                    image_url=image_url,
                    valid_until=extract_valid_until(card_text),
                    raw_payload={"text": card_text, "promo_code": promo_code},
                )
            )
        return offers

    def _is_detail_page(self) -> bool:
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").casefold().removeprefix("www.")
        return host == "promokood.ru" and parsed.path.casefold().startswith("/o/")

    def _parse_detail_codes(self, soup: BeautifulSoup) -> list[RawOffer]:
        strings = [re.sub(r"\s+", " ", value).strip() for value in soup.stripped_strings]
        strings = [value for value in strings if value]
        merchant = self._detail_merchant(soup, strings)
        offers: list[RawOffer] = []
        seen: set[str] = set()

        for index in range(len(strings) - 1):
            code = strings[index].strip()
            descriptor = strings[index + 1].strip()
            if not self._looks_like_detail_code(code, descriptor):
                continue

            parts = [descriptor]
            cursor = index + 2
            while cursor < len(strings):
                value = strings[cursor].strip()
                if _DETAIL_STOP_RE.search(value):
                    break
                if cursor + 1 < len(strings) and self._looks_like_detail_code(value, strings[cursor + 1]):
                    break
                if _DETAIL_CTA_RE.match(value):
                    break
                parts.append(value)
                if _DETAIL_DATE_RE.match(value):
                    break
                cursor += 1

            record_text = " ".join(parts).strip()
            if not record_text:
                continue
            title = self._detail_title(parts)
            ext_id = hashlib.sha256(f"{self.base_url}|{merchant or ''}|{code}|{record_text}".encode("utf-8")).hexdigest()[:32]
            if ext_id in seen:
                continue
            seen.add(ext_id)

            percent = self._discount_percent(record_text)
            amount = self._discount_amount(record_text) if percent is None else None
            offers.append(
                RawOffer(
                    source_key=self.key,
                    external_id=ext_id,
                    title=title,
                    source_url=self.base_url,
                    merchant=merchant,
                    description=record_text[:2000],
                    conditions=record_text[:2000],
                    promo_code=code,
                    discount_percent=percent,
                    discount_amount=amount,
                    valid_until=extract_valid_until(record_text),
                    raw_payload={
                        "text": record_text,
                        "promo_code": code,
                        "record_kind": "promokood_detail_promo",
                    },
                )
            )
        return offers

    def _looks_like_detail_code(self, code: str, descriptor: str) -> bool:
        if not _DETAIL_CODE_RE.fullmatch(code):
            return False
        if _DETAIL_CTA_RE.match(code):
            return False
        return bool(_DETAIL_DESCRIPTOR_RE.match(descriptor))

    def _detail_merchant(self, soup: BeautifulSoup, strings: list[str]) -> str | None:
        for node in soup.find_all(["h1", "h2", "h3"]):
            value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
            if value and len(value) <= 120 and not _OFFER_WORD_RE.fullmatch(value):
                return value
        for value in strings[:8]:
            if value and len(value) <= 120 and not _DETAIL_CTA_RE.match(value) and not _DETAIL_DESCRIPTOR_RE.match(value):
                return value
        return None

    def _detail_title(self, parts: list[str]) -> str:
        descriptor = parts[0] if parts else "Промокод"
        title = re.sub(r"^промокод\s+на\s+", "", descriptor, flags=re.IGNORECASE).strip(" :-—")
        if len(parts) > 1 and not _DETAIL_DATE_RE.match(parts[1]) and parts[1].lower().startswith(("на ", "для ", "при ")):
            title = f"{title} {parts[1]}".strip()
        return (title[:300] or "Промокод")

    def _find_card(self, action: Tag) -> Tag:
        action_text = re.sub(r"\s+", " ", action.get_text(" ", strip=True)).strip()
        fallback: Tag = action
        for parent in action.parents:
            if not isinstance(parent, Tag):
                continue
            text = re.sub(r"\s+", " ", " ".join(parent.stripped_strings)).strip()
            if parent.name in {"article", "li"}:
                return parent
            if parent.name == "div" and len(text) <= 800 and len(text) > len(action_text) + 5:
                fallback = parent
        return fallback

    def _merchant(self, card: Tag, action_text: str) -> str | None:
        for selector in ("h2", "h3", "h4", "strong", "b"):
            node = card.find(selector)
            if node:
                value = node.get_text(" ", strip=True)
                if value and value != action_text and len(value) <= 120:
                    return value

        text = re.sub(r"\s+", " ", " ".join(card.stripped_strings)).strip()
        benefit = _BENEFIT_START_RE.search(text)
        if benefit:
            prefix = text[: benefit.start()].strip(" :-—")
            if prefix:
                return prefix[:120]

        parts = [x.strip() for x in card.stripped_strings if x.strip() and x.strip() != action_text]
        return parts[0][:120] if parts else None

    def _title(self, card_text: str, merchant: str | None) -> str:
        text = re.sub(r"\s+", " ", card_text).strip()
        if merchant and text.lower().startswith(merchant.lower()):
            text = text[len(merchant):].strip(" :-—")
        text = _ACTION_SUFFIX_RE.sub("", text).strip(" :-—")
        return text[:300] or merchant or "Предложение"

    def _discount_percent(self, text: str) -> Decimal | None:
        match = _PERCENT_RE.search(text)
        if not match:
            return None
        value = int(match.group(1))
        return Decimal(value) if 0 < value <= 100 else None

    def _discount_amount(self, text: str) -> Decimal | None:
        match = _AMOUNT_RE.search(text)
        if not match:
            return None
        return Decimal(match.group(1).replace(" ", ""))

    def _image_url(self, card: Tag) -> str | None:
        image = card.find("img")
        if not image:
            return None
        src = image.get("src") or image.get("data-src")
        return urljoin(self.base_url, src) if src else None
