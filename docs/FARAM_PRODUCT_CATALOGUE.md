# Faram Product Catalogue

The procurement intelligence layer separates **market demand** from **Faram supply capability**.

`data/faram_product_catalogue.csv` is the controlled source for Faram's actual products, principals and territory coverage. It must not be populated by inference from IATI activity text or external tender notices.

## Required product fields

- `faram_product_id` — stable internal product identifier.
- `product_name` — Faram's commercial product name.
- `manufacturer_name` — principal/manufacturer represented by Faram.
- `product_family` — canonical family used by procurement matching.
- `equipment_category` — canonical equipment category.
- `model` — model or series where applicable.
- `keywords` — approved tender-language aliases for matching.
- `exclusion_keywords` — terms that should prevent an unsafe match.
- `principal_status` — current relationship status, e.g. `ACTIVE`, `INACTIVE`, `PROSPECT`.
- `territory` — geographic coverage of the relationship.
- `source` — authoritative internal source for the catalogue record.
- `notes` — controlled commercial notes.

## Technical specification evidence

Technical specifications are maintained separately in `data/faram_product_specifications.csv`. This prevents product identity records from becoming an unstructured specification store and allows individual specifications to carry their own evidence lifecycle.

Each specification record contains:

- `faram_product_id` — links the specification to a controlled catalogue product.
- `specification_name` — canonical specification label used by deterministic matching.
- `specification_value` — explicitly documented value; no inferred values are permitted.
- `specification_unit` — documented unit, normalized by the specification matching layer where supported.
- `source` — authoritative source type, such as manufacturer datasheet or Faram-held documentation.
- `source_reference` — document/reference identifier sufficient to trace the evidence.
- `verification_status` — `VERIFIED`, `UNVERIFIED`, `EXPIRED` or `DISPUTED`.
- `notes` — controlled evidence notes.

Only `VERIFIED` specifications are eligible for downstream technical matching by default. `UNVERIFIED`, `EXPIRED` and `DISPUTED` records remain available for review but must not silently become positive technical evidence.

## Matching rules

1. External notices are first classified into a product family using explicit tender evidence.
2. A Faram product match is allowed only when the catalogue contains an active product whose family/category and approved keywords support the notice.
3. Manufacturer/principal coverage is never inferred from generic market knowledge.
4. Territory must be compatible before a product is considered commercially actionable.
5. Exclusion keywords override positive keyword matches.
6. Technical compliance is evaluated only from explicit specification evidence.
7. Missing, unverified, expired or disputed technical evidence produces an evidence gap rather than an inferred pass.
8. When multiple products remain plausible, return all candidates with confidence/evidence rather than selecting one arbitrarily.
9. No catalogue or specification record should be created automatically from an external notice.

## Intended output

The eventual commercial match should answer:

`Tender -> product family -> Faram product candidate(s) -> principal -> territory fit -> specification evidence -> technical status -> confidence -> recommended action`

This allows procurement intelligence to support actual tender pursuit without confusing market demand with Faram's contractual product rights or undocumented technical capability.
