from __future__ import annotations

from src.sources.adapters.common import extract_revealed_promo_code
from src.sources.adapters.promokodik import PromokodikAdapter
from src.sources.adapters.promokodi_net_ru import PromokodiNetRuAdapter


class _Client:
    network_policy = "direct"
    timeout_seconds = 1.0

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get_text(self, url: str) -> str:
        self.calls.append(url)
        return self.pages[url]


def test_extract_revealed_promo_code_from_common_server_rendered_shapes() -> None:
    assert extract_revealed_promo_code('<button data-promocode="SAVE20">copy</button>') == "SAVE20"
    assert extract_revealed_promo_code('<script>{"promocode":"HELLO15"}</script>') == "HELLO15"
    assert extract_revealed_promo_code('<div>Промокод: WELCOME7</div>') == "WELCOME7"
    assert extract_revealed_promo_code('<div>Показать промокод Скидка 20%</div>') is None


def test_promokodik_collect_follows_offer_url_and_enriches_code() -> None:
    root = "https://promokodik.ru/shop"
    detail = "https://promokodik.ru/shop?offer_id=42"
    client = _Client({
        root: '<article><h3>Скидка 17% на заказ</h3><div>Срок действия: до 31.12.2027</div><a href="?offer_id=42">Показать промокод</a></article>',
        detail: '<div class="modal"><input name="promocode" value="ORDER17"></div>',
    })
    offers = PromokodikAdapter(root, client=client).collect()
    assert len(offers) == 1
    assert offers[0].promo_code == "ORDER17"
    assert offers[0].raw_payload["reveal_status"] == "success"
    assert client.calls == [root, detail]


def test_promokodi_net_ru_collect_follows_offer_url_and_enriches_code() -> None:
    root = "https://promokodi.net.ru/shop"
    detail = "https://promokodi.net.ru/coupon/77"
    client = _Client({
        root: '<article><h3>Скидка 10% по промокоду</h3><a href="/coupon/77">Открыть промокод</a></article>',
        detail: '<div data-clipboard-text="NET10">Скопировать</div>',
    })
    offers = PromokodiNetRuAdapter(root, client=client).collect()
    assert len(offers) == 1
    assert offers[0].promo_code == "NET10"
    assert offers[0].raw_payload["reveal_status"] == "success"
    assert client.calls == [root, detail]
