from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from src.modules.offers.models import Offer
from src.modules.source_registry.collectors import CollectorError, TelegramPublicCollector, normalize_telegram_channel
from src.modules.source_registry.models import RegisteredSource, SourceItem
from src.modules.source_registry.runner import collect_registered_source
from src.shared.config import get_settings
from src.shared.db import Base, create_session, get_engine, reset_db_runtime


@pytest.mark.parametrize(("value", "expected"), [
    ("@skidia", "skidia"), ("skidia", "skidia"), ("https://t.me/skidia", "skidia"),
    ("https://t.me/s/skidia", "skidia"), ("http://telegram.me/skidia", "skidia"),
])
def test_normalize_public_channel(value: str, expected: str) -> None:
    assert normalize_telegram_channel(value) == expected


def test_telegram_html_contract_and_network_router(monkeypatch: pytest.MonkeyPatch) -> None:
    html = '''<div class="tgme_channel_history"><div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="skidia/123"></div><div class="tgme_widget_message_text">Промокод TEST20<br>Скидка 20%</div><a class="tgme_widget_message_date"><time datetime="2026-08-08T10:00:00Z"></time></a></div><div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="skidia/124"></div></div></div>'''
    source = RegisteredSource(key="tg", name="tg", platform="telegram", source_type="discount_channel", url="@skidia", external_id=None, collector_type="telegram_public", network_policy="auto", enabled=True, status="unknown", trust_level="community", priority=50, check_interval_minutes=120)
    collector = TelegramPublicCollector(); calls = []
    monkeypatch.setattr(collector, "_get", lambda url, **kwargs: calls.append((url, kwargs["route"])) or httpx.Response(200, text=html, request=httpx.Request("GET", url)))
    items = collector.collect(source)
    assert calls == [("https://t.me/s/skidia", "auto")]
    assert len(items) == 1 and items[0].external_id == "telegram:skidia:123"
    assert items[0].url == "https://t.me/skidia/123" and items[0].published_at is not None


def test_telegram_preview_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    source = RegisteredSource(key="tg", name="tg", platform="telegram", source_type="discount_channel", url="skidia", collector_type="telegram_public", network_policy="direct", enabled=True, status="unknown", trust_level="community", priority=50, check_interval_minutes=120)
    collector = TelegramPublicCollector()
    monkeypatch.setattr(collector, "_get", lambda url, **kwargs: httpx.Response(200, text="<html>challenge</html>", request=httpx.Request("GET", url)))
    with pytest.raises(CollectorError, match="no channel history"):
        collector.collect(source)


@pytest.fixture
def telegram_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DP_DATABASE_URL", f"sqlite:///{tmp_path / 'telegram.db'}")
    get_settings.cache_clear(); reset_db_runtime(); Base.metadata.create_all(get_engine())
    try: yield
    finally: reset_db_runtime(); get_settings.cache_clear()


def test_telegram_pipeline_is_idempotent_and_parses_expiry(telegram_db, monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the fixture in the future so the test validates expiry parsing rather
    # than becoming a calendar-dependent expired-offer test.
    html = '''<div class="tgme_channel_history"><div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="skidia/123"></div><div class="tgme_widget_message_text">Промокод TEST20 — скидка 20%. Работает до 31.12.2099.</div><a class="tgme_widget_message_date"><time datetime="2026-08-08T10:00:00Z"></time></a></div></div>'''
    with create_session() as session:
        source = RegisteredSource(key="tg", name="tg", platform="telegram", source_type="discount_channel", url="https://t.me/skidia", collector_type="telegram_public", network_policy="auto", enabled=True, status="unknown", trust_level="community", priority=50, check_interval_minutes=120)
        session.add(source); session.commit(); source_id = source.id
    monkeypatch.setattr(TelegramPublicCollector, "_get", lambda self, url, **kwargs: httpx.Response(200, text=html, request=httpx.Request("GET", url)))
    first, second = collect_registered_source(source_id), collect_registered_source(source_id)
    with create_session() as session:
        offer = session.scalar(select(Offer)); items = session.scalars(select(SourceItem)).all()
    assert first.items_created == 1 and first.offers_created == 1 and second.items_created == 0
    assert len(items) == 1 and offer.valid_until is not None
