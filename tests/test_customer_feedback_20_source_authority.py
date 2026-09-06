from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.customer_feedback_20 import _is_stale_promokood_review_artifact
from src.modules.offers.models import Offer, OfferSourceObservation
from src.sources.adapters.promokood import PromokoodAdapter
from src.sources.base import RawOffer
from src.sources.config import SourceConfig
from src.sources.parity_runtime import ObservedProductionSourceRuntime
from src.sources.parity_telemetry import RetirementMode, SourceParityState


def test_promokood_detail_page_fans_out_real_codes_and_ignores_related_cards() -> None:
    html = """
    <main>
      <h1>Отелло</h1>
      <div>отели</div>
      <button>Активировать промокод</button>

      <div>ALLVSNTPO</div>
      <div>промокод на скидку 7% (не более 3500 ₽)</div>
      <div>на любое по счету бронирование отеля</div>
      <div>до 31.05.2027</div>

      <div>SHER8</div>
      <div>промокод на скидку 15% (не более 1500 ₽)</div>
      <div>на первое бронирование в приложении</div>
      <div>до 31.12.2027</div>

      <div>2K25</div>
      <div>промокод на скидку 2000 ₽</div>
      <div>на бронирование отеля от 20000 ₽</div>
      <div>до 31.12.2027</div>

      <h2>О сервисе:</h2>
      <p>Описание сервиса.</p>
      <h2>Похожие предложения</h2>
      <a href="/o/level-travel">Level.Travel Отели туры / отели Скидка 4000 ₽ Открыть</a>
      <a href="/o/yandex-travel">Яндекс Путешествия отели / авиа / жд / туры Скидка 20% Открыть</a>
      <a href="/o/trip-com">Trip.com отели / авиа / жд / трансферы Скидка 8% Открыть</a>
    </main>
    """

    offers = PromokoodAdapter("https://promokood.ru/o/otello").parse(html)

    assert [offer.promo_code for offer in offers] == ["ALLVSNTPO", "SHER8", "2K25"]
    assert all(offer.merchant == "Отелло" for offer in offers)
    assert offers[0].discount_percent == Decimal("7")
    assert offers[1].discount_percent == Decimal("15")
    assert offers[2].discount_amount == Decimal("2000")
    assert all("Открыть" not in (offer.description or "") for offer in offers)


def test_promokood_root_navigation_cards_are_discovery_only() -> None:
    html = """
    <main>
      <a href="/o/level-travel">Level.Travel Отели туры / отели Скидка 4000 ₽ Открыть</a>
      <a href="/o/yandex-travel">Яндекс Путешествия отели / авиа / жд / туры Скидка 20% Открыть</a>
      <a href="/o/trip-com">Trip.com отели / авиа / жд / трансферы Скидка 8% Открыть</a>
    </main>
    """

    offers = PromokoodAdapter("https://promokood.ru/").parse(html)

    assert offers == []


class _FakeAcquisition:
    def __init__(self, html: str, url: str) -> None:
        self.html = html
        self.url = url

    def acquire(self, request):
        assert request.url == self.url
        return SimpleNamespace(asset=SimpleNamespace(html=self.html, source_url=self.url))


class _Adapter:
    def __init__(self, config: SourceConfig) -> None:
        self.config = config

    def parse(self, html: str) -> list[RawOffer]:
        assert "SAVE20" in html
        return [
            RawOffer(
                source_key=self.config.key,
                external_id=f"{self.config.key}:real",
                title="Реальный промокод",
                source_url=self.config.base_url,
                promo_code="SAVE20",
                discount_percent=Decimal("20"),
            )
        ]


class _BombGenericDecoder:
    def decode(self, *args, **kwargs):
        raise AssertionError("generic decoder must not run for customer source adapters")


@pytest.mark.parametrize(
    "source_key",
    ["promokood", "promokodik", "berikod", "promokodi_net_ru", "promko"],
)
def test_persisted_generic_primary_cannot_bypass_customer_source_adapter(source_key: str) -> None:
    url = "https://example.test/merchant"
    config = SourceConfig(
        source_key,
        source_key,
        source_key,
        "https://example.test/",
        runtime_mode="hybrid",
    )
    runtime = ObservedProductionSourceRuntime(
        config,
        state=SourceParityState(
            source_key=source_key,
            mode=RetirementMode.GENERIC_PRIMARY,
        ),
        adapter_factory=_Adapter,
    )
    runtime.acquisition = _FakeAcquisition("<main>SAVE20 скидка 20%</main>", url)
    runtime.generic_decoder = _BombGenericDecoder()

    offers, decoded_pages, warnings, generic_pages, adapter_pages, parity_failures = (
        runtime._decode_selected((url,), ())
    )

    assert [offer.promo_code for offer in offers] == ["SAVE20"]
    assert decoded_pages == 1
    assert generic_pages == 0
    assert adapter_pages == 1
    assert parity_failures == 0
    assert f"source_adapter_authoritative:{source_key}" in warnings
    assert offers[0].raw_payload["dp_engine"]["decoder"] == "source_adapter_authoritative"


def test_old_promokood_generic_navigation_row_is_marked_as_stale_artifact() -> None:
    offer = Offer(
        title="Яндекс Путешествия отели / авиа / жд / туры Скидка 20% Открыть",
        description="Яндекс Путешествия отели / авиа / жд / туры Скидка 20% Открыть",
        promo_code=None,
        status="needs_review",
    )
    observation = OfferSourceObservation(
        offer_id=1,
        source_id=1,
        source_url="https://promokood.ru/o/otello",
        raw_payload_json=json.dumps(
            {"dp_engine": {"decoder": "generic_multi_record_direct"}},
            ensure_ascii=False,
        ),
    )

    assert _is_stale_promokood_review_artifact(offer, observation) is True

    offer.promo_code = "YAVIBRAL"
    assert _is_stale_promokood_review_artifact(offer, observation) is False
