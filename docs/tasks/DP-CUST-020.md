# DP-CUST-020 — source-authoritative promo-code extraction after 2026-09-06 customer feedback

Status: `In implementation`
Baseline: `e6b3bf81909e60d6d7ddae98dab0225bba3b8190`
Customer feedback date: `2026-09-06`

## Customer-visible defect

The review queue contains Promokood rows such as Level.Travel, Яндекс Путешествия and Trip.com with a discount value and an `Открыть` link but without the actual promo code. The operator would have to open each merchant link manually and copy promo codes. A merchant detail page can contain several independent promo codes, so one overview/navigation card cannot represent the required output.

Live Promokood merchant pages confirm the required 1:N model: a single `/o/<merchant>` page contains several code/benefit/conditions/validity blocks and is followed by `Похожие предложения` navigation cards. Those related cards are discovery links, not final offers.

## Product decision

For the customer delivery path, stop treating the generic decoder as a candidate production authority for the five shipped aggregator sources. Keep DP Engine for acquisition, crawl and target-page discovery, but use the existing dedicated source adapter as the authoritative decoder for:

- `promokood`;
- `promokodik`;
- `berikod`;
- `promokodi_net_ru`;
- `promko`.

This is intentionally source-specific. The customer does not need to configure CSS/XPath manually; source knowledge is shipped in the application adapter/profile.

## Implementation

### Adapter-authoritative runtime

- A persisted `generic_primary` parity state is ignored for the five customer sources.
- Selected target pages are decoded only by their source adapter.
- Generic extraction cannot silently replace a source-adapter result on those sources.
- DP Engine provenance records `source_adapter_authoritative`.
- Unknown/future sources retain the previous generic/parity behavior.

### Promokood navigation vs. business records

- `/o/<merchant>` promo-code blocks remain 1:N records: each code becomes its own `RawOffer`.
- Code-less internal links to another `/o/...` page are treated as discovery/navigation only.
- Code-less root overview cards are not persisted as offers.
- Code-less `Открыть` / `Подробнее` / incomplete `Активировать промокод` rows on merchant detail pages are suppressed.
- Real code-bearing records are preserved.

### Existing customer database remediation

After a Promokood run, old `new` / `needs_review` code-less navigation artifacts are moved to `rejected`. Manual status overrides remain protected by `OfferRepository.update` and are not overwritten.

## Acceptance criteria

1. A Promokood merchant page with N promo-code blocks yields N offers with populated `promo_code`.
2. Related-offer cards such as `... Скидка 20% Открыть` do not become offers.
3. Root overview cards without codes do not enter the review queue.
4. A stored `generic_primary` state cannot bypass any of the five shipped source adapters.
5. Existing code-less Promokood navigation artifacts are removed from the default review queue without changing manually overridden statuses.
6. Unknown/non-customer sources keep the previous hybrid/parity behavior.
7. Targeted regression tests pass.
8. Full CI passes before merge.
9. Live acceptance must verify at least one multi-code merchant page and confirm the review UI shows actual codes, not related-navigation cards.

## Follow-up before customer delivery

DP-CUST-020 is the first correction from the 2026-09-06 feedback. After merge, run live source-by-source acceptance and remediate any remaining adapter-specific field/reveal defects. The delivery gate is business completeness (actual promo code/conditions/merchant per offer), not merely zero collection errors.
