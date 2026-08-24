import sqlite3
import html
import uuid
from pathlib import Path

from organisation_resolution.normalizer import normalize_name


DB = Path("data/iati_intelligence.db")
SEEDED_SOURCES = ("MANUAL_AUDIT", "SYSTEM_GROUP_SEED")


GROUPS = [
    {
        "key": "UNICEF",
        "name": "UNICEF",
        "name_contains": ["unicef", "united nations children's fund"],
        "ref_prefixes": ["XM-DAC-41122", "41122"],
    },
    {
        "key": "WORLD_HEALTH_ORGANIZATION",
        "name": "World Health Organization",
        "name_contains": ["world health organization"],
        "ref_prefixes": ["XM-DAC-928"],
    },
    {
        "key": "GAVI",
        "name": "Gavi, the Vaccine Alliance",
        "name_contains": ["gavi", "vaccine alliance"],
    },
    {
        "key": "GLOBAL_FUND",
        "name": "Global Fund",
        "name_contains": ["global fund"],
        "exclude_contains": ["global fund for women"],
    },
    {
        "key": "GATES_FOUNDATION",
        "name": "Gates Foundation",
        "name_contains": ["gates foundation", "bill melinda gates"],
    },
    {
        "key": "EUROPEAN_COMMISSION",
        "name": "European Commission",
        "name_contains": [
            "european commission",
            "european civil protection and humanitarian aid",
        ],
    },
    {
        "key": "FCDO",
        "name": "Foreign, Commonwealth & Development Office",
        "name_contains": [
            "foreign commonwealth development office",
            "department for international development",
        ],
        "ref_prefixes": ["GB-GOV-1"],
    },
    {
        "key": "USAID",
        "name": "USAID",
        "name_contains": ["usaid", "united states agency for international development"],
        "ref_prefixes": ["US-GOV-1"],
    },
    {
        "key": "WORLD_BANK",
        "name": "World Bank",
        "name_contains": [
            "world bank",
            "international bank for reconstruction",
            "international development association",
        ],
        "ref_prefixes": ["44000"],
    },
    {
        "key": "CANADA_GOVERNMENT",
        "name": "Government of Canada",
        "name_contains": [
            "department of foreign affairs trade and development canada",
            "global affairs canada",
        ],
    },
    {
        "key": "JAPAN_GOVERNMENT",
        "name": "Government of Japan",
        "name_contains": [
            "ministry of foreign affairs japan",
            "japan ministry of finance",
            "japan international cooperation agency",
        ],
        "exclude_contains": ["committee for unicef"],
    },
    {
        "key": "FRANCE_GOVERNMENT",
        "name": "Government of France",
        "name_contains": [
            "ministry for europe and foreign affairs",
            "french development agency",
            "agence francaise de developpement",
        ],
        "exclude_contains": ["committee for unicef"],
    },
    {
        "key": "DENMARK_MFA",
        "name": "Ministry of Foreign Affairs, Denmark",
        "name_contains": [
            "ministry of foreign affairs denmark",
            "denmark ministry of foreign affairs",
        ],
    },
    {
        "key": "WORLD_VISION",
        "name": "World Vision",
        "name_contains": ["world vision"],
    },
    {
        "key": "INNOVATIONS_FOR_POVERTY_ACTION",
        "name": "Innovations for Poverty Action",
        "name_contains": ["innovations for poverty action"],
    },
    {
        "key": "IDRC",
        "name": "International Development Research Centre",
        "name_contains": ["international development research centre"],
    },
    {
        "key": "KOICA",
        "name": "KOICA",
        "name_contains": ["korea international cooperation agency", "koica"],
    },
    {
        "key": "UNITAID",
        "name": "UNITAID",
        "name_contains": ["unitaid"],
    },
    {
        "key": "AICS",
        "name": "Italian Agency for Cooperation and Development",
        "name_contains": ["italian agency for cooperation and development"],
    },
    {
        "key": "UK_DHSC",
        "name": "UK Department of Health and Social Care",
        "name_contains": ["department of health and social care"],
    },
    {
        "key": "KING_SALMAN_RELIEF",
        "name": "King Salman Humanitarian Aid and Relief Centre",
        "name_contains": ["king salman humanitarian aid and relief centre"],
    },
    {
        "key": "LSHTM",
        "name": "London School of Hygiene and Tropical Medicine",
        "name_contains": ["london school of hygiene and tropical medicine"],
    },
    {
        "key": "LIVERPOOL_TROPICAL_MEDICINE",
        "name": "Liverpool School of Tropical Medicine",
        "name_contains": ["liverpool school of tropical medicine"],
    },
    {
        "key": "CORDAID",
        "name": "Cordaid",
        "name_contains": ["cordaid"],
    },
    {
        "key": "INTERNATIONAL_RESCUE_COMMITTEE",
        "name": "International Rescue Committee",
        "name_contains": ["international rescue committee"],
    },
    {
        "key": "CLINTON_HEALTH_ACCESS_INITIATIVE",
        "name": "Clinton Health Access Initiative",
        "name_contains": ["clinton health access initiative"],
    },
    {
        "key": "AMREF",
        "name": "AMREF Health Africa",
        "name_contains": [
            "amref health africa",
            "african medical and research foundation",
        ],
    },
    {
        "key": "PALLADIUM",
        "name": "Palladium International",
        "name_contains": ["palladium international"],
    },
    {
        "key": "OXFORD_POLICY_MANAGEMENT",
        "name": "Oxford Policy Management",
        "name_contains": ["oxford policy management"],
    },
    {
        "key": "ADDIS_ABABA_UNIVERSITY",
        "name": "Addis Ababa University",
        "name_contains": ["addis ababa university"],
    },
    {
        "key": "DRC_GOVERNMENT",
        "name": "Government of the Democratic Republic of the Congo",
        "name_contains": [
            "democratic republic of the congo",
            "democratic republic of congo",
        ],
    },
    {
        "key": "UGANDA_GOVERNMENT",
        "name": "Government of Uganda",
        "name_contains": ["government of uganda"],
    },
    {
        "key": "TANZANIA_GOVERNMENT",
        "name": "Government of Tanzania",
        "name_contains": [
            "government of tanzania",
            "united republic of tanzania",
        ],
    },
    {
        "key": "ROCKEFELLER_FOUNDATION",
        "name": "Rockefeller Foundation",
        "name_contains": ["rockefeller foundation"],
    },
    {
        "key": "OXFAM",
        "name": "Oxfam",
        "name_contains": ["oxfam"],
    },
    {
        "key": "NORWEGIAN_REFUGEE_COUNCIL",
        "name": "Norwegian Refugee Council",
        "name_contains": ["norwegian refugee council"],
    },
    {
        "key": "SIGHTSAVERS",
        "name": "Sightsavers",
        "name_contains": ["sightsavers"],
    },
    {
        "key": "POPULATION_SERVICES",
        "name": "Population Services International",
        "name_contains": [
            "population services international",
            "population services kenya",
        ],
    },
    {
        "key": "GHENT_UNIVERSITY",
        "name": "Ghent University",
        "name_contains": ["ghent university"],
    },
    {
        "key": "CANADEM",
        "name": "CANADEM",
        "name_contains": ["canadem"],
    },
    {
        "key": "POWER_OF_NUTRITION",
        "name": "Power of Nutrition",
        "name_contains": ["power of nutrition"],
    },
    {
        "key": "RESOLVE_TO_SAVE_LIVES",
        "name": "Resolve to Save Lives",
        "name_contains": ["resolve to save lives"],
    },
    {
        "key": "SEND_A_COW",
        "name": "Send a Cow",
        "name_contains": ["send a cow"],
    },
    {
        "key": "HEALTH_RESEARCH_OPERATIONS_KENYA",
        "name": "Health Research Operations Kenya",
        "name_contains": [
            "health research operations kenya limited",
            "health research operations kenya ltd",
        ],
    },
    {
        "key": "UNIVERSITY_COLLEGE_LONDON",
        "name": "University College London",
        "name_contains": ["university college london"],
    },
    {
        "key": "UNIVERSITY_OF_OXFORD",
        "name": "University of Oxford",
        "name_contains": ["university of oxford"],
    },
    {
        "key": "CARE_NEDERLAND",
        "name": "Care Nederland",
        "name_contains": ["care nederland"],
    },
    {
        "key": "CESVI",
        "name": "Cesvi",
        "name_contains": ["cesvi"],
    },
    {
        "key": "EXPERTISE_FRANCE",
        "name": "Expertise France",
        "name_contains": ["expertise france"],
    },
    {
        "key": "ETHIOPIAID_IRELAND",
        "name": "Ethiopiaid Ireland",
        "name_contains": ["ethiopiaid ireland"],
    },
    {
        "key": "INSTITUTE_OF_DEVELOPMENT_STUDIES",
        "name": "Institute of Development Studies",
        "name_contains": ["institute of development studies"],
    },
    {
        "key": "ICRC",
        "name": "International Committee of the Red Cross",
        "name_contains": ["international committee of the red cross"],
    },
    {
        "key": "IOM",
        "name": "International Organization for Migration",
        "name_contains": ["international organization for migration"],
    },
    {
        "key": "KEMRI",
        "name": "Kenya Medical Research Institute",
        "name_contains": ["kenya medical research institute", "kemri"],
    },
    {
        "key": "PREMIERE_URGENCE_INTERNATIONALE",
        "name": "Première Urgence Internationale",
        "name_contains": [
            "premiere urgence internationale",
            "première urgence internationale",
        ],
    },
    {
        "key": "RUTGERS",
        "name": "Rutgers",
        "name_contains": ["rutgers"],
    },
    {
        "key": "SAVE_THE_CHILDREN",
        "name": "Save the Children",
        "name_contains": ["save the children"],
    },
]


def split_values(value):
    return [
        item.strip()
        for item in html.unescape(str(value or "")).split(";")
        if item.strip()
    ]


def ensure_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS organisation_groups (
            group_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL,
            canonical_group_key TEXT NOT NULL UNIQUE,
            group_type TEXT NOT NULL DEFAULT 'ORGANISATION_FAMILY',
            group_status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS organisation_group_members (
            group_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            membership_type TEXT NOT NULL DEFAULT 'MEMBER',
            confidence_score REAL NOT NULL DEFAULT 1.0,
            source_system TEXT NOT NULL DEFAULT 'SYSTEM_GROUP_SEED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (group_id, entity_id)
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_org_group_members_entity
        ON organisation_group_members(entity_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_org_group_members_group
        ON organisation_group_members(group_id)
        """
    )


def load_entities(conn):
    return conn.execute(
        """
        SELECT
            entity_id,
            canonical_name,
            primary_org_ref,
            org_refs
        FROM organisation_entities
        WHERE entity_status = 'ACTIVE'
        """
    ).fetchall()


def entity_matches(entity, definition):
    _, canonical_name, primary_org_ref, org_refs = entity
    normalized_name = normalize_name(canonical_name)
    refs = {
        ref.lower()
        for value in (primary_org_ref, org_refs)
        for ref in split_values(value)
    }

    for excluded in definition.get("exclude_contains", []):
        if normalize_name(excluded) in normalized_name:
            return False

    for needle in definition.get("name_contains", []):
        if normalize_name(needle) in normalized_name:
            return True

    for prefix in definition.get("ref_prefixes", []):
        prefix = prefix.lower()

        if any(ref == prefix or ref.startswith(f"{prefix}-") for ref in refs):
            return True

    return False


def upsert_group(conn, definition):
    row = conn.execute(
        """
        SELECT group_id
        FROM organisation_groups
        WHERE canonical_group_key = ?
        """,
        (definition["key"],),
    ).fetchone()

    if row:
        group_id = row[0]
        conn.execute(
            """
            UPDATE organisation_groups
            SET group_name = ?,
                group_status = 'ACTIVE',
                updated_at = CURRENT_TIMESTAMP
            WHERE group_id = ?
            """,
            (definition["name"], group_id),
        )
        return group_id

    group_id = f"GRP-{uuid.uuid4().hex[:8].upper()}"
    conn.execute(
        """
        INSERT INTO organisation_groups (
            group_id,
            group_name,
            canonical_group_key,
            group_type,
            group_status
        )
        VALUES (?, ?, ?, 'ORGANISATION_FAMILY', 'ACTIVE')
        """,
        (group_id, definition["name"], definition["key"]),
    )

    return group_id


def seed_groups(db_path=DB):
    conn = sqlite3.connect(db_path)

    try:
        ensure_schema(conn)
        entities = load_entities(conn)
        summary = {}

        for definition in GROUPS:
            group_id = upsert_group(conn, definition)
            source_placeholders = ",".join("?" for _ in SEEDED_SOURCES)

            conn.execute(
                f"""
                DELETE FROM organisation_group_members
                WHERE group_id = ?
                  AND source_system IN ({source_placeholders})
                """,
                (group_id, *SEEDED_SOURCES),
            )

            members = [
                entity[0]
                for entity in entities
                if entity_matches(entity, definition)
            ]

            conn.executemany(
                """
                INSERT OR IGNORE INTO organisation_group_members (
                    group_id,
                    entity_id,
                    membership_type,
                    confidence_score,
                    source_system
                )
                VALUES (?, ?, 'MEMBER', 1.0, 'SYSTEM_GROUP_SEED')
                """,
                [(group_id, entity_id) for entity_id in members],
            )
            summary[definition["key"]] = len(members)

        conn.commit()
        return summary
    finally:
        conn.close()


def main():
    summary = seed_groups()
    total = sum(summary.values())

    print(f"Organisation groups seeded successfully: {total} memberships.")

    for key, count in summary.items():
        print(f"{key}: {count}")


if __name__ == "__main__":
    main()
