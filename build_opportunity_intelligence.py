#!/usr/bin/env python3

import argparse
import sqlite3
from datetime import datetime


def text(value):
    if value is None:
        return ""
    return str(value).strip()


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def has_text(value):
    return bool(text(value))


def procurement_relevance(stage, equipment_signal, category):
    stage = text(stage).upper()
    signal = num(equipment_signal)
    category = text(category).upper()

    if signal and category and stage in {"ACTIVE", "PIPELINE"}:
        return "HIGH"

    if signal or category:
        return "MEDIUM"

    return "LOW"


def likely_procurement_type(category, summary):
    category = text(category).upper()
    summary = text(summary).lower()

    if "DIAGNOSTIC" in category:
        if any(x in summary for x in [
            "laboratory",
            "diagnostic",
            "testing",
            "surveillance",
            "detection",
        ]):
            return "DIAGNOSTIC / LABORATORY EQUIPMENT"

        return "DIAGNOSTIC EQUIPMENT"

    if "MEDICAL DEVICES" in category:
        return "MEDICAL DEVICES / CLINICAL EQUIPMENT"

    if "COLD CHAIN" in category:
        return "COLD CHAIN / STORAGE EQUIPMENT"

    if "IT / HEALTH INFORMATION" in category:
        return "HEALTH IT / INFORMATION SYSTEMS"

    if "FACILITY" in category:
        return "FACILITY / HOSPITAL INFRASTRUCTURE"

    if "VEHICLES" in category:
        return "VEHICLES / TRANSPORT"

    return category or "HEALTH INFRASTRUCTURE / EQUIPMENT"


def build_rationale(row):
    score = num(row["opportunity_score"])
    stage = text(row["procurement_stage"]).upper()
    category = text(row["primary_equipment_category"])
    equipment_signal = num(row["equipment_signal"])

    reasons = []

    if score >= 75:
        reasons.append("very high opportunity score")
    elif score >= 65:
        reasons.append("high opportunity score")
    elif score >= 55:
        reasons.append("moderately strong opportunity score")

    if stage == "ACTIVE":
        reasons.append("activity is currently active")
    elif stage == "PIPELINE":
        reasons.append("activity is in the pipeline")

    if equipment_signal:
        reasons.append("direct equipment signal identified")

    if category:
        reasons.append(f"relevant equipment category: {category}")

    if has_text(row["implementing_partners"]):
        reasons.append("implementing partner information is available")

    if num(row["total_budget_amount"]) > 0:
        reasons.append(
            f"budget data available ({row['total_budget_amount']:,.2f} "
            f"{text(row['budget_currency'])})"
        )

    if not reasons:
        return "Opportunity identified from IATI activity intelligence."

    return "; ".join(reasons).capitalize() + "."


def key_score_factors(row):
    factors = []

    score = num(row["opportunity_score"])

    if score >= 75:
        factors.append("Very high overall score")
    elif score >= 65:
        factors.append("High overall score")
    elif score >= 55:
        factors.append("Moderate overall score")

    for field, label in [
        ("stage_score", "Procurement stage"),
        ("market_fit_score", "Market fit"),
        ("geographic_score", "Geographic fit"),
        ("financial_score", "Financial strength"),
        ("procurement_evidence_score", "Procurement evidence"),
        ("timing_score", "Timing"),
    ]:
        value = num(row[field])
        if value > 0:
            factors.append(f"{label}: {value:g}")

    return "; ".join(factors)


def recommended_action(row):
    score = num(row["opportunity_score"])
    stage = text(row["procurement_stage"]).upper()
    category = text(row["primary_equipment_category"])

    if score >= 75 and stage == "ACTIVE":
        return (
            f"PRIORITY ENGAGEMENT: identify the procurement route, "
            f"decision makers and equipment requirements for {category or 'the identified category'}."
        )

    if score >= 65 and stage == "ACTIVE":
        return (
            f"ENGAGE NOW: validate procurement timing, specifications, "
            f"implementing partners and supplier route for {category or 'the opportunity'}."
        )

    if score >= 65 and stage == "PIPELINE":
        return (
            "EARLY ENGAGEMENT: map donor, implementer and procurement stakeholders "
            "and monitor for movement toward procurement."
        )

    if score >= 55:
        return (
            "MONITOR AND QUALIFY: gather additional procurement and equipment evidence "
            "before committing significant resources."
        )

    return "MONITOR: retain in intelligence pipeline and reassess as new data arrives."


def engagement_urgency(row):
    score = num(row["opportunity_score"])
    stage = text(row["procurement_stage"]).upper()

    if score >= 75 and stage == "ACTIVE":
        return "IMMEDIATE"

    if score >= 65 and stage == "ACTIVE":
        return "HIGH"

    if score >= 65 and stage == "PIPELINE":
        return "MEDIUM-HIGH"

    if score >= 55:
        return "MEDIUM"

    return "LOW"


def intelligence_confidence(row):
    evidence = 0

    if num(row["equipment_signal"]):
        evidence += 1

    if has_text(row["implementing_partners"]):
        evidence += 1

    def has_valid_budget_evidence(row):
        return (
          num(row["budget_positive_amount"]) > 0
          or num(row["budget_latest_amount"]) > 0
         )

    if has_text(row["equipment_target_summary"]):
        evidence += 1

    if has_text(row["equipment_target_snippets"]):
        evidence += 1

    if evidence >= 4:
        return "HIGH"

    if evidence >= 2:
        return "MEDIUM"

    return "LOW"


def main():
    parser = argparse.ArgumentParser(
        description="Build 02D Opportunity Intelligence from 02C opportunity scores."
    )
    parser.add_argument(
        "--database",
        required=True,
        help="Path to SQLite database",
    )

    args = parser.parse_args()

    conn = sqlite3.connect(args.database)
    conn.row_factory = sqlite3.Row

    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM opportunity_scores
    """)

    rows = cur.fetchall()

    cur.execute("DROP TABLE IF EXISTS opportunity_intelligence")

    cur.execute("""
        CREATE TABLE opportunity_intelligence (
            opportunity_id TEXT,
            project_title TEXT,
            country_codes TEXT,
            reporting_org_name TEXT,
            funding_agencies TEXT,
            implementing_partners TEXT,
            activity_status_code TEXT,
            activity_status_label TEXT,
            procurement_stage,
            planned_start_date TEXT,
            actual_start_date TEXT,
            planned_end_date TEXT,
            actual_end_date TEXT,
            last_updated TEXT,
            total_budget_amount REAL,
            budget_currency TEXT,
            primary_equipment_category,
            equipment_signal,
            equipment_target_summary TEXT,
            equipment_target_snippets TEXT,
            opportunity_score,
            opportunity_priority,
            stage_score,
            market_fit_score,
            geographic_score,
            financial_score,
            procurement_evidence_score,
            timing_score,
            procurement_relevance,
            likely_procurement_type,
            opportunity_rationale,
            key_score_factors,
            recommended_action,
            engagement_urgency,
            intelligence_confidence,
            has_direct_equipment_evidence,
            has_budget_data,
            has_implementing_partner_data,
            intelligence_status
        )
    """)

    insert_sql = """
        INSERT INTO opportunity_intelligence (
            opportunity_id,
            project_title,
            country_codes,
            reporting_org_name,
            funding_agencies,
            implementing_partners,
            activity_status_code,
            activity_status_label,
            procurement_stage,
            planned_start_date,
            actual_start_date,
            planned_end_date,
            actual_end_date,
            last_updated,
            total_budget_amount,
            budget_currency,
            primary_equipment_category,
            equipment_signal,
            equipment_target_summary,
            equipment_target_snippets,
            opportunity_score,
            opportunity_priority,
            stage_score,
            market_fit_score,
            geographic_score,
            financial_score,
            procurement_evidence_score,
            timing_score,
            procurement_relevance,
            likely_procurement_type,
            opportunity_rationale,
            key_score_factors,
            recommended_action,
            engagement_urgency,
            intelligence_confidence,
            has_direct_equipment_evidence,
            has_budget_data,
            has_implementing_partner_data,
            intelligence_status
        )
        VALUES (
?,?,?,?,?,?,?,?,?,?,
?,?,?,?,?,?,?,?,?,?,
?,?,?,?,?,?,?,?,?,?,
?,?,?,?,?,?,?,?,?
)
    """

    records = []

    for row in rows:
        relevance = procurement_relevance(
            row["procurement_stage"],
            row["equipment_signal"],
            row["primary_equipment_category"],
        )

        procurement_type = likely_procurement_type(
            row["primary_equipment_category"],
            row["equipment_target_summary"],
        )

        confidence = intelligence_confidence(row)

        records.append((
            row["activity_id"],
            row["project_title"],
            row["country_codes"],
            row["reporting_org_name"],
            row["funding_agencies"],
            row["implementing_partners"],
            row["activity_status_code"],
            row["activity_status_label"],
            row["procurement_stage"],
            row["planned_start_date"],
            row["actual_start_date"],
            row["planned_end_date"],
            row["actual_end_date"],
            row["last_updated"],
            row["total_budget_amount"],
            row["budget_currency"],
            row["primary_equipment_category"],
            row["equipment_signal"],
            row["equipment_target_summary"],
            row["equipment_target_snippets"],
            row["opportunity_score"],
            row["opportunity_priority"],
            row["stage_score"],
            row["market_fit_score"],
            row["geographic_score"],
            row["financial_score"],
            row["procurement_evidence_score"],
            row["timing_score"],
            relevance,
            procurement_type,
            build_rationale(row),
            key_score_factors(row),
            recommended_action(row),
            engagement_urgency(row),
            confidence,
            1 if num(row["equipment_signal"]) else 0,
            1 if num(row["total_budget_amount"]) > 0 else 0,
            1 if has_text(row["implementing_partners"]) else 0,
            "GENERATED"
        ))

    cur.executemany(insert_sql, records)

    cur.execute("""
        CREATE INDEX idx_oi_score
        ON opportunity_intelligence(opportunity_score)
    """)

    cur.execute("""
        CREATE INDEX idx_oi_priority
        ON opportunity_intelligence(opportunity_priority)
    """)

    cur.execute("""
        CREATE INDEX idx_oi_category
        ON opportunity_intelligence(primary_equipment_category)
    """)

    cur.execute("""
        CREATE INDEX idx_oi_country
        ON opportunity_intelligence(country_codes)
    """)

    conn.commit()

    print(f"Built Opportunity Intelligence: {len(records):,} records")
    print("Table: opportunity_intelligence")
    print(f"Generated at: {datetime.utcnow().isoformat()}Z")

    conn.close()


if __name__ == "__main__":
    main()
