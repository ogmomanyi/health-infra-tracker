# Platform Roadmap — Current Execution Plan

This document reflects the platform's current state on `main` and the next product-development sequence.

## 1. Data foundation
Status: complete.

IATI activity ingestion, normalized activities, budgets, planned disbursements, transactions, countries and organisations are implemented.

## 2. Intelligence foundation
Status: complete.

Market overview, procurement-language detection, equipment demand signals, opportunity identification and baseline scoring are implemented.

## 3. Entity and relationship intelligence
Status: complete.

Organisation normalization, canonical entities and aliases, entity resolution, organisation groups, opportunity-to-organisation resolution and donor intelligence are implemented with canonical guardrails.

## 4. Commercial intelligence
Status: complete.

Commercial opportunity scoring, target accounts, recommended actions, engagement intelligence, CRM notes, account prioritisation, action queues and project-level opportunity detail are implemented.

## 5. Predictive and product intelligence
Status: production foundation complete.

Equipment/product intelligence, tender probability and stage, procurement timing windows, procurement-product matching, manufacturer entities and tender-prediction validation are implemented.

Calibration remains dependent on accumulated external observations.

## 6. External procurement intelligence
Status: complete.

External procurement-source ingestion, World Bank notices and the procurement-intelligence pipeline are operational.

## 7. Buyer, donor and competitive intelligence
Status: substantially complete.

Buyer intelligence, donor intelligence and baseline competitive signals are integrated into the platform. Supplier-level competitive intelligence remains the next consolidation step.

## 8. Commercial execution and CRM
Status: complete.

Opportunity workspace, execution workspace, CRM persistence, local API, validation, work management, account workspace and management dashboard are integrated.

## 9. Execution completeness
Status: complete.

Persistent execution completeness, API coverage and opportunity-workspace UI integration are in `main`.

## 10. Faram catalogue intelligence
Status: initial production layer complete.

Controlled catalogue validation, required-field checks, duplicate commercial-record detection, manufacturer coverage and active-product counts are implemented.

The catalogue remains a Faram-side source of truth; procurement notices do not automatically create catalogue records.

## 11. Manufacturer and brand intelligence
Status: consolidation required.

Manufacturer extraction, canonical manufacturer intelligence and related tests exist in historical branches and in the mainline history, but the surviving branches contain overlapping historical implementations. The next task is to establish one canonical implementation on current `main`.

## 12. Supplier entity resolution
Status: next integration.

Deterministic supplier entity resolution, aliases, canonical supplier IDs, supplier-history aggregation and related tests exist on a stale branch. The useful functionality should be rebuilt cleanly against current `main` rather than merging the stale branch wholesale.

## 13. Supplier competitive intelligence
Status: next integration.

Supplier competitive intelligence exists on a stale branch. It should be integrated only after supplier entity resolution is established as the canonical identity layer.

## 14. Specification-level product matching
Status: next major product milestone.

Move from product-family matching toward structured tender-requirement extraction and specification-level matching against Faram products and principals.

Target output:
- tender requirement set
- normalized specifications
- candidate Faram products
- requirement-by-requirement fit score
- evidence and exceptions

## 15. Faram catalogue, principal and authorization linkage
Status: next major commercial milestone.

Link procurement demand and specification-level fit to Faram's actual catalogue, principal/manufacturer representation and territory authorization status.

The system should distinguish:
- product fit
- manufacturer fit
- commercial authorization
- current Faram representation

## 16. Award and competitor validation
Status: planned validation layer.

Validate supplier, manufacturer and product matches against awarded tenders and publicly available supplier information where reliable evidence exists.

## 17. Product and competitor intelligence UX
Status: planned.

Add dashboard views for:
- product family
- product/specification fit
- manufacturer
- supplier
- validation performance
- competitor signals
- Faram coverage and authorization

## Strategic end-state

The platform should answer, for each relevant opportunity:

> What is being procured, who is buying, when they are likely to buy, which Faram product/principal can satisfy the requirement, whether Faram is authorized to supply it, who the relevant competitors are, what evidence supports the assessment, and what Faram should do next.

## Development principle

Prefer clean integration on current `main` over merging stale feature branches. Historical branches are evidence sources, not automatically valid integration targets.
