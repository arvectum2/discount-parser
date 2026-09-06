from __future__ import annotations

import json
import re
from dataclasses import replace
from urllib.parse import urlparse

from sqlalchemy import select

from arvectum_data.acquisition import AcquisitionRequest, RenderMode
from arvectum_data.crawl import TargetPageAssessment
from src.modules.offers.models import Offer, OfferSourceObservation, Source
from src.modules.offers.repository import OfferRepository
from src.shared.db import session_scope
from src.sources import runner as _sources_runner
from src.sources.adapters.promokood import PromokoodAdapter
from src.sources.base import RawOffer
from src.sources.engine_runtime import ProductionSourceRuntime, _diagnostic
from src.sources.parity_runtime import ObservedProductionSourceRuntime
from src.sources.parity_telemetry import ParityRunTelemetry


_PATCHED = False

# The customer product ships dedicated adapters for these sources. DP Engine is
# still responsible for crawling/target-page discovery, but the source adapter is
# the production decoder. A persisted generic-primary experiment must never
# bypass a site adapter in the customer path.
_SOURCE_ADAPTER_KEYS = frozenset(
    {
        "promokood",
        "promokodik",
        "berikod",
        "promokodi_net_ru",
        "promko",
    }
)

_NAVIGATION_CTA_RE = re.compile(
    r"(?:\bоткрыть\b|\bподробнее\b|\bактивировать\s+промокод\b)\s*$",
    re.IGNORECASE,
)

_ORIGINAL_PRODUCTION_DECODE = ProductionSourceRuntime._decode_selected
_ORIGINAL_OBSERVED_DECODE = ObservedProductionSourceRuntime._decode_selected
_ORIGINAL_PROMOKOOD_PARSE = PromokoodAdapter.parse
_ORIGINAL_RUN_SOURCE = _sources_runner.run_source


def _normalized_url(value: str) -> str:
    parsed = urlparse(value)
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(path=path, fragment="", query="").geturl()


def _is_promokood_detail_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    return host == "promokood.ru" and parsed.path.casefold().startswith("/o/")


def _promokood_parse_v20(self: PromokoodAdapter, html: str) -> list[RawOffer]:
    """Keep business records and discard internal navigation cards.

    Promokood merchant pages contain the actual N promo-code records followed by
    "Похожие предложения". The latter are links to other /o/... pages and must
    be discovery targets, not offers. The same rule also removes code-less
    overview cards from the home page while preserving real structured discount
    rows and all promo-code records returned by the DP-CUST-014 block parser.
    """

    parsed = list(_ORIGINAL_PROMOKOOD_PARSE(self, html))
    page_url = _normalized_url(self.base_url)
    page_path = urlparse(page_url).path.rstrip("/") or "/"
    page_is_root = page_path == "/"
    page_is_detail = _is_promokood_detail_url(page_url)

    result: list[RawOffer] = []
    for offer in parsed:
        if offer.promo_code:
            result.append(offer)
            continue

        offer_url = _normalized_url(offer.source_url or self.base_url)
        text = " ".join(
            part for part in (offer.title, offer.description, offer.conditions) if part
        ).strip()

        # A code-less card pointing to another Promokood merchant page is only a
        # crawler/discovery link. This catches category-page duplicate cards.
        if _is_promokood_detail_url(offer_url) and offer_url != page_url:
            continue

        # The root page is an overview. Its code-less cards ("... Открыть") are
        # not final business records; the runtime follows discovered /o/ pages.
        if page_is_root:
            continue

        # On a merchant detail page, a code-less CTA ending in Открыть/Подробнее
        # belongs to "Похожие предложения" (or is an incomplete promo parse).
        if page_is_detail and _NAVIGATION_CTA_RE.search(text):
            continue

        result.append(offer)

    return result


def _decode_source_adapter_authoritative(
    self: ProductionSourceRuntime,
    selected: tuple[str, ...],
    assessments: tuple[TargetPageAssessment, ...],
) -> tuple[list[RawOffer], int, list[str], int, int, int]:
    by_url = {item.url: item for item in assessments}
    offers: list[RawOffer] = []
    warnings: list[str] = [f"source_adapter_authoritative:{self.config.key}"]
    seen: set[tuple[str, str]] = set()
    decoded_pages = 0
    adapter_pages = 0

    for page_url in selected:
        try:
            acquired = self.acquisition.acquire(
                AcquisitionRequest(
                    url=page_url,
                    timeout_s=self.policy.timeout_s,
                    max_bytes=self.policy.max_bytes,
                    render_mode=RenderMode.AUTO,
                )
            )
            html = acquired.asset.html
            if not html:
                continue

            effective_url = acquired.asset.source_url or page_url
            page_config = replace(
                self.config,
                base_url=effective_url,
                runtime_mode="legacy",
            )
            adapter = self.adapter_factory(page_config)
            parser = getattr(adapter, "parse", None)
            if not callable(parser):
                warnings.append(f"decoder_missing:{page_url}")
                continue

            decoded = list(parser(html))
            decoded_pages += 1
            adapter_pages += 1
            assessment = by_url.get(page_url)

            for raw in decoded:
                identity = (raw.source_key, raw.external_id)
                if identity in seen:
                    continue
                seen.add(identity)
                offers.append(
                    self._with_engine_provenance(
                        raw,
                        page_url,
                        assessment,
                        decoder="source_adapter_authoritative",
                        parity=None,
                    )
                )
        except Exception as exc:
            warnings.append(f"page_decode_failed:{_diagnostic(exc)}")

    # Tuple contract: offers, decoded_pages, warnings, generic_pages,
    # legacy/adapter_pages, parity_failures.
    return offers, decoded_pages, warnings, 0, adapter_pages, 0


def _production_decode_v20(
    self: ProductionSourceRuntime,
    selected: tuple[str, ...],
    assessments: tuple[TargetPageAssessment, ...],
):
    if self.config.key in _SOURCE_ADAPTER_KEYS:
        return _decode_source_adapter_authoritative(self, selected, assessments)
    return _ORIGINAL_PRODUCTION_DECODE(self, selected, assessments)


def _observed_decode_v20(
    self: ObservedProductionSourceRuntime,
    selected: tuple[str, ...],
    assessments: tuple[TargetPageAssessment, ...],
):
    if self.config.key in _SOURCE_ADAPTER_KEYS:
        result = _decode_source_adapter_authoritative(self, selected, assessments)
        self.last_telemetry = ParityRunTelemetry(
            source_key=self.config.key,
            mode_before=self.parity_state.mode,
        )
        return result
    return _ORIGINAL_OBSERVED_DECODE(self, selected, assessments)


def _raw_decoder(observation: OfferSourceObservation) -> str:
    try:
        payload = json.loads(observation.raw_payload_json or "{}")
    except (TypeError, ValueError):
        return ""
    engine = payload.get("dp_engine")
    if not isinstance(engine, dict):
        return ""
    return str(engine.get("decoder") or "")


def _is_stale_promokood_review_artifact(
    offer: Offer,
    observation: OfferSourceObservation,
) -> bool:
    """Identify old code-less navigation/generic rows safe to hide from review."""

    if offer.promo_code:
        return False

    text = " ".join(
        part for part in (offer.title, offer.description, offer.conditions) if part
    ).strip()
    if _NAVIGATION_CTA_RE.search(text):
        return True

    decoder = _raw_decoder(observation)
    if decoder.startswith("generic_multi_record") and _is_promokood_detail_url(
        observation.source_url
    ):
        return True

    return False


def _retire_stale_promokood_review_artifacts() -> int:
    retired = 0
    with session_scope() as session:
        sources = list(
            session.scalars(
                select(Source).where(
                    Source.key.in_(("promokood", "registry:promokood"))
                )
            ).all()
        )
        if not sources:
            return 0

        source_ids = [source.id for source in sources if source.id is not None]
        rows = session.execute(
            select(Offer, OfferSourceObservation)
            .join(
                OfferSourceObservation,
                OfferSourceObservation.offer_id == Offer.id,
            )
            .where(
                OfferSourceObservation.source_id.in_(source_ids),
                Offer.status.in_(("new", "needs_review")),
                Offer.promo_code.is_(None),
            )
            .order_by(OfferSourceObservation.observed_at.desc())
        ).all()

        repo = OfferRepository(session)
        seen_offer_ids: set[int] = set()
        for offer, observation in rows:
            if offer.id is None or offer.id in seen_offer_ids:
                continue
            seen_offer_ids.add(offer.id)
            if not _is_stale_promokood_review_artifact(offer, observation):
                continue
            # OfferRepository.update respects a manual status override, so an
            # operator-approved decision can never be silently overwritten.
            repo.update(offer, {"status": "rejected"})
            retired += 1
    return retired


def _run_source_v20(config, *args, **kwargs):
    result = _ORIGINAL_RUN_SOURCE(config, *args, **kwargs)
    if config.key != "promokood":
        return result

    retired = _retire_stale_promokood_review_artifacts()
    if retired:
        result.runtime_warnings = (
            *result.runtime_warnings,
            f"dp_cust_020_retired_navigation_artifacts:{retired}",
        )
    return result


def install_customer_feedback_20() -> None:
    global _PATCHED
    if _PATCHED:
        return

    ProductionSourceRuntime._decode_selected = _production_decode_v20
    ObservedProductionSourceRuntime._decode_selected = _observed_decode_v20
    PromokoodAdapter.parse = _promokood_parse_v20
    _sources_runner.run_source = _run_source_v20
    _PATCHED = True
