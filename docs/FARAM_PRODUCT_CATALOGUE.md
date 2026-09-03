# Faram Product Catalogue

The procurement intelligence layer separates **market demand** from **Faram supply capability**.

`data/faram_product_catalogue.csv` is the controlled source for Faram's actual products, principals and territory coverage. It must not be populated by inference from IATI activity text or external tender notices.

## Required fields

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

## Matching rules

1. External notices are first classified into a product family using explicit tender evidence.
2. A Faram product match is allowed only when the catalogue contains an active product whose family/category and approved keywords support the notice.
3. Manufacturer/principal coverage is never inferred from generic market knowledge.
4. Territory must be compatible before a product is considered commercially actionable.
5. Exclusion keywords override positive keyword matches.
6. When multiple products remain plausible, return all candidates with confidence/evidence rather than selecting one arbitrarily.
7. No catalogue record should be created automatically from an external notice.

## Intended output

The eventual commercial match should answer:

`Tender -> product family -> Faram product candidate(s) -> principal -> territory fit -> evidence -> confidence -> recommended action`

This allows procurement intelligence to support actual tender pursuit without confusing market demand with Faram's contractual product rights.
