"""Conservative extraction of explicit manufacturer/brand evidence.

This module intentionally does not infer a manufacturer from an awardee,
product family, model number, or market knowledge. Only explicitly labelled
manufacturer/brand/make values are accepted.
"""

from __future__ import annotations

import re
from html import unescape


def _plain_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" \t\r\n:;-|,.")


def _label_values(text: str, labels: tuple[str, ...]) -> list[str]:
    if not text:
        return []
    label = "|".join(re.escape(item) for item in labels)
    pattern = rf"(?:^|[;\n|])\s*(?:{label})\s*[:\-]\s*([^;\n|]+)"
    return [_clean(match.group(1)) for match in re.finditer(pattern, text, re.I) if _clean(match.group(1))]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = re.sub(r"\s+", " ", value.casefold()).strip()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def extract_explicit_manufacturer_brand(record: dict[str, object] | None = None, notice_text: str = "") -> tuple[str, str, str]:
    """Return (manufacturer, brand, evidence_status).

    Status values are EXPLICIT when one unambiguous labelled value exists,
    AMBIGUOUS when conflicting labelled values exist, and NONE otherwise.
    """
    record = record or {}
    text = _plain_text(notice_text)

    manufacturer_values: list[str] = []
    brand_values: list[str] = []
    for key in ("manufacturer_name", "manufacturer"):
        value = str(record.get(key) or "").strip()
        if value:
            manufacturer_values.append(value)
    for key in ("brand_name", "brand", "make", "make_name"):
        value = str(record.get(key) or "").strip()
        if value:
            brand_values.append(value)

    manufacturer_values.extend(_label_values(text, ("Manufacturer", "Manufacturer Name")))
    brand_values.extend(_label_values(text, ("Brand", "Brand Name", "Make")))
    manufacturer_values = _unique(manufacturer_values)
    brand_values = _unique(brand_values)

    if len(manufacturer_values) > 1 or len(brand_values) > 1:
        return "", "", "AMBIGUOUS"
    manufacturer = manufacturer_values[0] if manufacturer_values else ""
    brand = brand_values[0] if brand_values else ""
    if manufacturer or brand:
        return manufacturer, brand, "EXPLICIT"
    return "", "", "NONE"
