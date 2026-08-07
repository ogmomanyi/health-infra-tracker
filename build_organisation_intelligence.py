#!/usr/bin/env python3

import argparse
import sqlite3
from collections import defaultdict


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def split_values(value):
    """
    Split IATI-style semicolon-separated organisation/country fields.
    """
    value = clean(value)

    if not value:
        return []

    return [
        item.strip()
        for item in value.split(";")
        if item.strip()
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Build Phase 03 Organisation Intelligence"
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

    # ---------------------------------------------------------
    # Recreate output table
    # ---------------------------------------------------------

    cur.execute("""
        DROP TABLE IF EXISTS organisation_intelligence
    """)

    cur.execute("""
        CREATE TABLE organisation_intelligence (
            organisation_key TEXT,
            org_ref TEXT,
            org_name TEXT,

            funding_appearances INTEGER,
            reporting_appearances INTEGER,
            implementing_appearances INTEGER,
            accountable_appearances INTEGER,
            total_appearances INTEGER,

            funded_opportunities INTEGER,
            implemented_opportunities INTEGER,
            reported_opportunities INTEGER,
            accountable_opportunities INTEGER,

            active_opportunities INTEGER,
            pipeline_opportunities INTEGER,

            strong_opportunities INTEGER,
            high_priority_opportunities INTEGER,

            total_opportunity_budget REAL,

            countries TEXT,
            country_count INTEGER,

            equipment_categories TEXT,

            diagnostic_opportunities INTEGER,
            medical_device_opportunities INTEGER,
            cold_chain_opportunities INTEGER,
            facility_infrastructure_opportunities INTEGER,

            average_opportunity_score REAL,
            maximum_opportunity_score REAL,

            top_country TEXT,
            top_equipment_category TEXT,

            organisation_roles TEXT,
            organisation_types TEXT,

            intelligence_status TEXT
        )
    """)

    # ---------------------------------------------------------
    # Raw organisation appearances
    # ---------------------------------------------------------

    organisation_rows = cur.execute("""
        SELECT
            org_ref,
            org_name,
            role,
            org_type
        FROM organisations
        WHERE org_name IS NOT NULL
        AND TRIM(org_name) <> ''
    """).fetchall()

    # Key:
    # Prefer org_ref where available.
    # Otherwise use a normalised name.
    identities = {}

    for row in organisation_rows:
        org_ref = clean(row["org_ref"])
        org_name = clean(row["org_name"])

        if org_ref:
            key = f"REF:{org_ref}"
        else:
            key = f"NAME:{org_name.lower()}"

        if key not in identities:
            identities[key] = {
                "org_ref": org_ref,
                "names": defaultdict(int),
                "roles": defaultdict(int),
                "types": defaultdict(int),
                "funding": 0,
                "reporting": 0,
                "implementing": 0,
                "accountable": 0,
                "total": 0,
            }

        data = identities[key]

        data["names"][org_name] += 1

        role = clean(row["role"]).lower()

        if role:
            data["roles"][role] += 1

        org_type = clean(row["org_type"])

        if org_type:
            data["types"][org_type] += 1

        data["total"] += 1

        if role == "funding":
            data["funding"] += 1
        elif role == "reporting":
            data["reporting"] += 1
        elif role == "implementing":
            data["implementing"] += 1
        elif role == "accountable":
            data["accountable"] += 1

    # ---------------------------------------------------------
    # Opportunity intelligence
    # ---------------------------------------------------------

    opportunities = cur.execute("""
        SELECT
            opportunity_id,
            country_codes,
            funding_agencies,
            implementing_partners,
            reporting_org_name,

            opportunity_score,
            opportunity_priority,
            activity_status_label,
            procurement_stage,

            total_budget_amount,
            budget_currency,

            primary_equipment_category
        FROM opportunity_intelligence
    """).fetchall()

    # ---------------------------------------------------------
    # Relationship accumulators
    # ---------------------------------------------------------

    stats = {}

    def ensure(key):
        if key not in stats:
            stats[key] = {
                "funded": set(),
                "implemented": set(),
                "reported": set(),
                "accountable": set(),

                "active": set(),
                "pipeline": set(),

                "strong": set(),
                "high_priority": set(),

                "budgets": [],

                "countries": defaultdict(int),
                "categories": defaultdict(int),

                "diagnostic": set(),
                "medical": set(),
                "cold_chain": set(),
                "facility": set(),

                "scores": [],
            }

        return stats[key]

    # ---------------------------------------------------------
    # Match organisation identity
    # ---------------------------------------------------------

    # Map exact org names to identity keys.
    name_to_key = {}

    for key, data in identities.items():
        for name in data["names"]:
            name_to_key[name.lower()] = key

    # Also map org_ref to identity.
    ref_to_key = {}

    for key, data in identities.items():
        if data["org_ref"]:
            ref_to_key[data["org_ref"]] = key

    # ---------------------------------------------------------
    # Process opportunities
    # ---------------------------------------------------------

    for row in opportunities:

        opportunity_id = clean(row["opportunity_id"])

        # -----------------------------
        # Countries
        # -----------------------------

        countries = split_values(row["country_codes"])

        # -----------------------------
        # Funding organisations
        # -----------------------------

        funders = split_values(row["funding_agencies"])

        # -----------------------------
        # Implementers
        # -----------------------------

        implementers = split_values(row["implementing_partners"])

        # -----------------------------
        # Reporting organisation
        # -----------------------------

        reporting = clean(row["reporting_org_name"])

        # -----------------------------
        # Opportunity characteristics
        # -----------------------------

        score = row["opportunity_score"]

        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.0

        priority = clean(row["opportunity_priority"]).upper()
        status = clean(row["activity_status_label"]).upper()
        stage = clean(row["procurement_stage"]).upper()

        category = clean(
            row["primary_equipment_category"]
        ).upper()

        budget = row["total_budget_amount"]

        try:
            budget = float(budget)
        except (TypeError, ValueError):
            budget = 0.0

        # -----------------------------------------------------
        # Helper to update organisation opportunity stats
        # -----------------------------------------------------

        def update_org(name, relationship):

            name_clean = clean(name)

            if not name_clean:
                return

            key = name_to_key.get(name_clean.lower())

            if key is None:
                key = f"NAME:{name_clean.lower()}"

                if key not in identities:
                    identities[key] = {
                        "org_ref": "",
                        "names": defaultdict(int),
                        "roles": defaultdict(int),
                        "types": defaultdict(int),
                        "funding": 0,
                        "reporting": 0,
                        "implementing": 0,
                        "accountable": 0,
                        "total": 0,
                    }

                identities[key]["names"][name_clean] += 1
                name_to_key[name_clean.lower()] = key

            s = ensure(key)

            if relationship == "funding":
                s["funded"].add(opportunity_id)

            elif relationship == "implementing":
                s["implemented"].add(opportunity_id)

            elif relationship == "reporting":
                s["reported"].add(opportunity_id)

            elif relationship == "accountable":
                s["accountable"].add(opportunity_id)

            if status == "ACTIVE":
                s["active"].add(opportunity_id)

            if stage == "PIPELINE":
                s["pipeline"].add(opportunity_id)

            if priority.startswith("B -"):
                s["strong"].add(opportunity_id)

            if priority.startswith("A -"):
                s["high_priority"].add(opportunity_id)

            if budget > 0:
                s["budgets"].append(budget)

            for country in countries:
                s["countries"][country] += 1

            if category:
                s["categories"][category] += 1

                if category == "DIAGNOSTIC EQUIPMENT":
                    s["diagnostic"].add(opportunity_id)

                elif category == "MEDICAL DEVICES & EQUIPMENT":
                    s["medical"].add(opportunity_id)

                elif category == "COLD CHAIN / STORAGE":
                    s["cold_chain"].add(opportunity_id)

                elif category == "FACILITY INFRASTRUCTURE":
                    s["facility"].add(opportunity_id)

            s["scores"].append(score)

        # -----------------------------------------------------
        # Apply relationships
        # -----------------------------------------------------

        for name in funders:
            update_org(name, "funding")

        for name in implementers:
            update_org(name, "implementing")

        if reporting:
            update_org(reporting, "reporting")

    # ---------------------------------------------------------
    # Build output records
    # ---------------------------------------------------------

    records = []

    for key, identity in identities.items():

        s = stats.get(key, {
            "funded": set(),
            "implemented": set(),
            "reported": set(),
            "accountable": set(),
            "active": set(),
            "pipeline": set(),
            "strong": set(),
            "high_priority": set(),
            "budgets": [],
            "countries": defaultdict(int),
            "categories": defaultdict(int),
            "diagnostic": set(),
            "medical": set(),
            "cold_chain": set(),
            "facility": set(),
            "scores": [],
        })

        names = identity["names"]

        # Most frequently observed name
        canonical_name = max(
            names.items(),
            key=lambda x: x[1]
        )[0]

        countries_sorted = sorted(
            s["countries"].items(),
            key=lambda x: (-x[1], x[0])
        )

        categories_sorted = sorted(
            s["categories"].items(),
            key=lambda x: (-x[1], x[0])
        )

        roles_sorted = sorted(
            identity["roles"].keys()
        )

        types_sorted = sorted(
            identity["types"].keys()
        )

        scores = s["scores"]

        avg_score = (
            sum(scores) / len(scores)
            if scores
            else None
        )

        max_score = (
            max(scores)
            if scores
            else None
        )

        intelligence_status = (
            "ACTIVE INTELLIGENCE"
            if (
                len(s["strong"]) > 0
                or len(s["active"]) > 0
            )
            else "MONITOR"
        )

        records.append((
            key,
            identity["org_ref"],
            canonical_name,

            identity["funding"],
            identity["reporting"],
            identity["implementing"],
            identity["accountable"],
            identity["total"],

            len(s["funded"]),
            len(s["implemented"]),
            len(s["reported"]),
            len(s["accountable"]),

            len(s["active"]),
            len(s["pipeline"]),

            len(s["strong"]),
            len(s["high_priority"]),

            sum(s["budgets"]) if s["budgets"] else 0,

            "; ".join(x[0] for x in countries_sorted),
            len(countries_sorted),

            "; ".join(x[0] for x in categories_sorted),

            len(s["diagnostic"]),
            len(s["medical"]),
            len(s["cold_chain"]),
            len(s["facility"]),

            avg_score,
            max_score,

            countries_sorted[0][0] if countries_sorted else "",
            categories_sorted[0][0] if categories_sorted else "",

            "; ".join(roles_sorted),
            "; ".join(types_sorted),

            intelligence_status,
        ))

    # ---------------------------------------------------------
    # Insert
    # ---------------------------------------------------------

    insert_sql = """
        INSERT INTO organisation_intelligence (
            organisation_key,
            org_ref,
            org_name,

            funding_appearances,
            reporting_appearances,
            implementing_appearances,
            accountable_appearances,
            total_appearances,

            funded_opportunities,
            implemented_opportunities,
            reported_opportunities,
            accountable_opportunities,

            active_opportunities,
            pipeline_opportunities,

            strong_opportunities,
            high_priority_opportunities,

            total_opportunity_budget,

            countries,
            country_count,

            equipment_categories,

            diagnostic_opportunities,
            medical_device_opportunities,
            cold_chain_opportunities,
            facility_infrastructure_opportunities,

            average_opportunity_score,
            maximum_opportunity_score,

            top_country,
            top_equipment_category,

            organisation_roles,
            organisation_types,

            intelligence_status
        )
        VALUES (
        ?,?,?,?,?,?,?,?,?,?,
        ?,?,?,?,?,?,?,?,?,?,
        ?,?,?,?,?,?,?,?,?,?,
        ?
    )
    """

    cur.executemany(insert_sql, records)

    # ---------------------------------------------------------
    # Indexes
    # ---------------------------------------------------------

    cur.execute("""
        CREATE INDEX idx_org_intel_name
        ON organisation_intelligence(org_name)
    """)

    cur.execute("""
        CREATE INDEX idx_org_intel_ref
        ON organisation_intelligence(org_ref)
    """)

    cur.execute("""
        CREATE INDEX idx_org_intel_funding
        ON organisation_intelligence(funding_appearances)
    """)

    cur.execute("""
        CREATE INDEX idx_org_intel_opportunity
        ON organisation_intelligence(funded_opportunities)
    """)

    cur.execute("""
        CREATE INDEX idx_org_intel_score
        ON organisation_intelligence(average_opportunity_score)
    """)

    cur.execute("""
        CREATE INDEX idx_org_intel_country
        ON organisation_intelligence(top_country)
    """)

    conn.commit()

    print(
        f"Built Organisation Intelligence: "
        f"{len(records):,} organisations"
    )

    print(
        "Table: organisation_intelligence"
    )

    conn.close()


if __name__ == "__main__":
    main()
