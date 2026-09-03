# Faram Product Matching

## Purpose

`procurement_intelligence.faram_product_matching` connects external procurement demand to Faram's controlled product catalogue.

The catalogue is the commercial source of truth for Faram product/principal coverage. Market intelligence alone must never be used to infer that Faram represents a manufacturer.

## Flow

```text
External tender
  -> procurement product match
  -> product family/category alignment
  -> Faram catalogue candidates
  -> keyword evidence
  -> exclusion check
  -> principal status
  -> territory fit
  -> actionable Faram match
```

## Matching rules

1. Product family or controlled equipment category must align.
2. If a catalogue record has `keywords`, at least one approved keyword must be explicitly present in the procurement match text.
3. `exclusion_keywords` always override positive keyword evidence.
4. Only `ACTIVE`, `APPROVED` or `CURRENT` principal statuses are considered active for commercial action.
5. Territory must include the procurement country before a match is actionable.
6. Missing or unrecognised country/territory information produces `REQUIRES_TERRITORY_REVIEW`, not a positive match.
7. Multiple qualifying catalogue records are retained; the matcher does not arbitrarily select one product.
8. An empty catalogue is valid and produces no candidates.

## Match statuses

| Status | Meaning |
| --- | --- |
| `FARAM_MATCH` | Controlled product, active principal and compatible territory are evidenced. |
| `REQUIRES_TERRITORY_REVIEW` | Product evidence exists, but territory cannot be confirmed. |
| `NOT_ACTIONABLE_WRONG_TERRITORY` | Product evidence exists, but the catalogue territory excludes the tender country. |
| `NOT_ACTIONABLE_INACTIVE_PRINCIPAL` | Product evidence exists, but principal status is not current. |
| `BLOCKED_BY_EXCLUSION` | A catalogue exclusion keyword overrides the positive evidence. |

## Output

The generated `data/faram_product_matches.csv` contains one row per catalogue candidate and includes the procurement event, Faram product, principal, territory result, keyword/exclusion evidence, confidence and recommended action.

Because the current catalogue is a controlled template rather than an asserted list of Faram principals, the pipeline will initially produce zero candidates. Populate `data/faram_product_catalogue.csv` from an authoritative Faram product/principal source before treating `FARAM_MATCH` records as commercial opportunities.
