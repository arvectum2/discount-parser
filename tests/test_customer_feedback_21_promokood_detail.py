from __future__ import annotations

from decimal import Decimal

from src.sources.adapters.promokood import PromokoodAdapter


def test_promokood_detail_page_yields_one_offer_per_actual_code() -> None:
    html = """
    <main>
      <h1>Отелло</h1>
      <div>отели</div>
      <button>Активировать промокод</button>
      <section>
        <div>ALLVSNTPO</div>
        <div>промокод на скидку 7% (не более 3500 ₽)</div>
        <div>на любое по счету бронирование отеля</div>
        <div>до 31.12.2026</div>
      </section>
      <section>
        <div>SHER8</div>
        <div>промокод на скидку 15% (не более 1500 ₽)</div>
        <div>на первое бронирование в приложении</div>
        <div>до 31.12.2026</div>
      </section>
      <section>
        <div>ALLVSNTPO</div>
        <div>промокод на скидку 7% (не более 3500 ₽)</div>
        <div>на первое бронирование отеля</div>
        <div>до 31.12.2026</div>
      </section>
      <section>
        <div>2K25</div>
        <div>промокод на скидку 2000 ₽</div>
        <div>на бронирование отеля от 20000 ₽</div>
        <div>до 31.12.2026</div>
      </section>
      <h2>О сервисе:</h2>
      <p>Описание сервиса.</p>
      <h2>Похожие предложения</h2>
      <article><h3>Level.Travel</h3><div>туры / отели</div><div>Скидка 4000 ₽</div><a href="/o/level-travel">Открыть</a></article>
      <article><h3>Яндекс Путешествия</h3><div>Скидка 20%</div><a href="/o/yandex-travel">Открыть</a></article>
    </main>
    """

    offers = PromokoodAdapter("https://promokood.ru/o/otello").parse(html)

    assert len(offers) == 4
    assert [offer.promo_code for offer in offers] == ["ALLVSNTPO", "SHER8", "ALLVSNTPO", "2K25"]
    assert all(offer.merchant == "Отелло" for offer in offers)
    assert offers[0].discount_percent == Decimal("7")
    assert offers[1].discount_percent == Decimal("15")
    assert offers[3].discount_amount == Decimal("2000")
    assert "на любое по счету бронирование" in (offers[0].conditions or "")
    assert "на первое бронирование" in (offers[2].conditions or "")
    assert all("Level.Travel" not in (offer.description or "") for offer in offers)
    assert all((offer.raw_payload or {}).get("record_kind") == "promokood_detail_promo" for offer in offers)


def test_promokood_detail_deduplicates_exact_repeated_render_but_keeps_same_code_with_new_conditions() -> None:
    html = """
    <h1>Тестовый магазин</h1>
    <button>Активировать промокод</button>
    <div>SALE10</div><div>промокод на скидку 10%</div><div>на первый заказ</div><div>до 31.12.2026</div>
    <div>SALE10</div><div>промокод на скидку 10%</div><div>на первый заказ</div><div>до 31.12.2026</div>
    <div>SALE10</div><div>промокод на скидку 10%</div><div>на повторный заказ</div><div>до 31.12.2026</div>
    """

    offers = PromokoodAdapter("https://promokood.ru/o/test").parse(html)

    assert len(offers) == 2
    assert [offer.promo_code for offer in offers] == ["SALE10", "SALE10"]
    assert "первый заказ" in (offers[0].conditions or "")
    assert "повторный заказ" in (offers[1].conditions or "")
