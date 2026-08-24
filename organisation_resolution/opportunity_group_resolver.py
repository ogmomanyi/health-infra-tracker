import html
import sqlite3

from organisation_resolution.normalizer import normalize_name
from organisation_resolution.database_resolver import (
    get_canonical_entity_id,
    load_entity_candidates,
    load_alias_candidates,
    table_exists,
)


DB = "data/iati_intelligence.db"

GROUP_REFERENCE_ALIASES = {
    "UNICEF": [
        "UNICEF",
        "United Nations Children's Fund",
        "United Nations Children's Fund (UNICEF)",
        "UNITED NATIONS CHILDREN'S FUND FONDS DES NATIONS UNIES POUR L'ENFA",
    ],
    "WORLD_HEALTH_ORGANIZATION": [
        "WHO",
        "World Health Organization",
        "World Health Organisation",
        "WHO - World Health Organization",
        "World Health Organisation - core voluntary contributions account",
        "WHO Contingency Fund for Emergencies",
    ],
    "GAVI": [
        "GAVI",
        "GAVI The Vaccine Alliance",
        "Gavi, the Vaccine Alliance",
    ],
    "GLOBAL_FUND": [
        "Global Fund",
        "The Global Fund",
        "The Global Fund to Fight AIDS, Tuberculosis and Malaria",
    ],
    "GATES_FOUNDATION": [
        "Bill & Melinda Gates Foundation",
        "Gates Foundation",
        "Gates Philanthropy Partners",
    ],
    "FCDO": [
        "DFID",
        "Foreign, Commonwealth & Development Office",
        "Foreign, Commonwealth & Development Office (FCDO), United Kingdom",
        "Department for International Development",
    ],
    "USAID": [
        "USAID",
        "United States Agency for International Development",
        "United States Agency for International Development (USAID)",
    ],
    "WORLD_BANK": [
        "World Bank",
        "International Development Association",
        "International Bank for Reconstruction and Development",
    ],
    "CANADA_GOVERNMENT": [
        "Canada",
        "Canada - Department of Foreign Affairs, Trade and Development",
        "Canada - Department of Foreign Affairscomma Trade and Development",
        "Department of Foreign Affairs, Trade and Development (DFATD), Canada",
    ],
    "JAPAN_GOVERNMENT": [
        "Japan",
        "Japan - Ministry of Finance",
        "Ministry of Foreign Affairs, Japan",
        "Japan International Cooperation Agency",
    ],
    "FRANCE_GOVERNMENT": [
        "France",
        "Ministry for Europe and Foreign Affairs (MEAE), France",
        "French Development Agency",
        "Agence Française de Developpement",
    ],
    "DENMARK_MFA": [
        "Denmark - Ministry of Foreign Affairs",
        "Ministry of Foreign Affairs, Denmark",
        "Ministry of Foreign Affairs of Denmark, Danida",
    ],
    "WORLD_VISION": [
        "World Vision",
        "World Vision International",
        "WORLD VISION INTERNATIONAL",
    ],
    "INNOVATIONS_FOR_POVERTY_ACTION": [
        "Innovations for Poverty Action",
        "Innovations For Poverty Action",
    ],
    "IDRC": [
        "International Development Research Centre",
    ],
    "KOICA": [
        "KOICA",
        "Korea International Cooperation Agency",
    ],
    "UNITAID": [
        "UNITAID",
        "Unitaid",
    ],
    "AICS": [
        "AICS - Italian Agency for Cooperation and Development",
        "Italian Agency for Cooperation and Development",
    ],
    "UK_DHSC": [
        "UK - Department of Health and Social Care (DHSC)",
        "Department of Health and Social Care",
    ],
    "KING_SALMAN_RELIEF": [
        "King Salman Humanitarian Aid and Relief Centre",
    ],
    "LSHTM": [
        "London School of Hygiene and Tropical Medicine",
    ],
    "LIVERPOOL_TROPICAL_MEDICINE": [
        "Liverpool School of Tropical Medicine",
    ],
    "CORDAID": [
        "Cordaid",
    ],
    "INTERNATIONAL_RESCUE_COMMITTEE": [
        "IRC",
        "International Rescue Committee",
        "INTERNATIONAL RESCUE COMMITTEE",
    ],
    "CLINTON_HEALTH_ACCESS_INITIATIVE": [
        "CHAI",
        "Clinton Health Access Initiative",
        "Clinton Health Access Initiative, Inc.",
        "Clinton Health Access Initiative Inc",
    ],
    "AMREF": [
        "AMREF",
        "AMREF Health Africa",
        "Amref Health Africa",
        "Amref UK",
        "Amref Health Africa - UK",
    ],
    "PALLADIUM": [
        "Palladium International",
        "Palladium International Ltd",
        "Palladium International Ltd (UK)",
    ],
    "OXFORD_POLICY_MANAGEMENT": [
        "Oxford Policy Management",
    ],
    "ADDIS_ABABA_UNIVERSITY": [
        "Addis Ababa University",
    ],
    "DRC_GOVERNMENT": [
        "Democratic Republic of the Congo",
        "Democratic Republic of Congo",
    ],
    "UGANDA_GOVERNMENT": [
        "Uganda",
        "Government of Uganda",
    ],
    "TANZANIA_GOVERNMENT": [
        "United Republic of Tanzania",
        "Tanzania",
        "Government of Tanzania",
    ],
    "ROCKEFELLER_FOUNDATION": [
        "Rockefeller Foundation",
        "The Rockefeller Foundation",
    ],
    "OXFAM": [
        "Oxfam",
        "Oxfam Novib",
    ],
    "NORWEGIAN_REFUGEE_COUNCIL": [
        "Norwegian Refugee Council",
    ],
    "SIGHTSAVERS": [
        "Sightsavers",
    ],
    "POPULATION_SERVICES": [
        "Population Services International",
        "Population Services Kenya",
    ],
    "GHENT_UNIVERSITY": [
        "Ghent University",
    ],
    "CANADEM": [
        "CANADEM",
    ],
    "POWER_OF_NUTRITION": [
        "The Power of Nutrition",
        "Power of Nutrition",
    ],
    "RESOLVE_TO_SAVE_LIVES": [
        "Resolve to Save Lives",
    ],
    "SEND_A_COW": [
        "Send a Cow Ethiopia",
        "Send a Cow",
    ],
    "HEALTH_RESEARCH_OPERATIONS_KENYA": [
        "Health Research Operations Kenya Limited",
        "Health Research Operations Kenya Ltd",
    ],
    "UNIVERSITY_COLLEGE_LONDON": [
        "University College London",
        "UCL",
    ],
    "UNIVERSITY_OF_OXFORD": [
        "University of Oxford",
    ],
    "CARE_NEDERLAND": [
        "Care Nederland",
    ],
    "CESVI": [
        "Cesvi",
    ],
    "EXPERTISE_FRANCE": [
        "Expertise France",
        "EXPERTISE FRANCE",
    ],
    "ETHIOPIAID_IRELAND": [
        "Ethiopiaid Ireland",
    ],
    "INSTITUTE_OF_DEVELOPMENT_STUDIES": [
        "Institute of Development Studies",
    ],
    "ICRC": [
        "International Committee of the Red Cross",
        "ICRC",
    ],
    "IOM": [
        "International Organization for Migration",
        "IOM",
    ],
    "KEMRI": [
        "Kenya Medical Research Institute",
        "KEMRI",
    ],
    "PREMIERE_URGENCE_INTERNATIONALE": [
        "Première Urgence Internationale",
        "Premiere Urgence Internationale",
    ],
    "RUTGERS": [
        "Rutgers",
    ],
    "SAVE_THE_CHILDREN": [
        "Save the Children",
        "Save the Children Netherlands",
        "Save the Children Fund",
    ],
}


def split_values(value):
    if not value:
        return []

    return [
        item.strip()
        for item in html.unescape(str(value)).split(";")
        if item.strip()
    ]


def load_group_aliases(conn):
    """
    Build a normalized-name -> group mapping from all entity names
    belonging to organisation groups.

    These aliases allow exact entity names that have been explicitly
    associated with an organisation family to be recognised.

    Raw generic organisation names such as "European Commission"
    are handled separately by load_group_keys().
    """

    aliases = {}

    rows = conn.execute("""
        SELECT
            g.group_id,
            g.group_name,
            e.canonical_name
        FROM organisation_groups g
        JOIN organisation_group_members m
            ON m.group_id = g.group_id
        JOIN organisation_entities e
            ON e.entity_id = m.entity_id
        WHERE g.group_status = 'ACTIVE'
          AND e.entity_status = 'ACTIVE'
    """).fetchall()

    for group_id, group_name, canonical_name in rows:
        key = normalize_name(canonical_name)

        if key:
            aliases.setdefault(key, set()).add(
                (group_id, group_name)
            )

    return aliases


def load_group_keys(conn):
    """
    Load explicit group-level aliases.

    These are deliberately conservative.

    The group name itself and its canonical group key are treated
    as explicit family-level references.

    Examples:

        European Commission
        EUROPEAN_COMMISSION

        Global Fund
        GLOBAL_FUND
    """

    rows = conn.execute("""
        SELECT
            group_id,
            group_name,
            canonical_group_key
        FROM organisation_groups
        WHERE group_status = 'ACTIVE'
    """).fetchall()

    aliases = {}

    for group_id, group_name, group_key in rows:

        group_name_key = normalize_name(group_name)

        if group_name_key:
            aliases.setdefault(
                group_name_key,
                set()
            ).add(
                (group_id, group_name)
            )

        group_key_normalized = normalize_name(group_key)

        if group_key_normalized:
            aliases.setdefault(
                group_key_normalized,
                set()
            ).add(
                (group_id, group_name)
            )

        for alias in GROUP_REFERENCE_ALIASES.get(group_key, []):
            alias_key = normalize_name(alias)

            if alias_key:
                aliases.setdefault(
                    alias_key,
                    set()
                ).add(
                    (group_id, group_name)
                )

    return aliases


def resolve_entity(conn, value, candidates=None):
    """
    Resolve an opportunity organisation name to an entity_id.

    This resolves the NAME first, then canonicalizes the resulting
    entity through DUPLICATE_OF relationships.
    """

    normalized = normalize_name(value)

    if not normalized:
        return None

    if candidates is None:
        candidates = (
            load_entity_candidates(conn)
            + load_alias_candidates(conn)
        )

    matches = {
        candidate["entity_id"]
        for candidate in candidates
        if candidate["normalized_name"] == normalized
    }

    if len(matches) != 1:
        return None

    entity_id = next(iter(matches))

    return get_canonical_entity_id(
        conn,
        entity_id
    )

def resolve_group(
    value,
    group_aliases,
    group_keys
):
    """
    Resolve a generic organisation reference to an organisation group.

    A group is only returned when the normalized value maps to exactly
    one group. This prevents ambiguous family-level assignments.
    """

    normalized = normalize_name(value)

    if not normalized:
        return None

    explicit_candidates = group_keys.get(normalized, set())

    if len(explicit_candidates) == 1:
        return next(iter(explicit_candidates))

    if len(explicit_candidates) > 1:
        return None

    candidates = set(group_aliases.get(normalized, set()))

    if len(candidates) == 1:
        return next(iter(candidates))

    return None


def classify_non_entity(value):
    """
    Conservative classification of known IATI generic categories.

    These should not be assigned to real organisations.
    """

    text = str(value or "").strip()

    if "\n" in text or len(text) > 180:
        return True

    normalized = normalize_name(value)

    if not normalized:
        return True

    categories = {
        normalize_name(
            "Anonymous"
        ),
        normalize_name(
            "IP not published"
        ),
        normalize_name(
            "Undefined"
        ),
        normalize_name(
            "Developing country-based NGO"
        ),
        normalize_name(
            "Secteur privé du pays bénéficiaire"
        ),
        normalize_name(
            "University, college or other teaching institution, research institute or think-tank"
        ),
        normalize_name(
            "Local Government"
        ),
        normalize_name(
            "Gouvernement central (SUD/EST)"
        ),
    }

    return normalized in categories


def find_group_for_entity(conn, entity_id):
    """
    Return the organisation group associated with an entity.

    An entity may currently belong to zero or more groups, but this
    resolver uses the first active membership for the opportunity
    resolution record.
    """

    row = conn.execute("""
        SELECT m.group_id
        FROM organisation_group_members m
        JOIN organisation_groups g
            ON g.group_id = m.group_id
        WHERE m.entity_id = ?
          AND g.group_status = 'ACTIVE'
        LIMIT 1
    """, (entity_id,)).fetchone()

    return row[0] if row else None


def resolve_reference(
    conn,
    value,
    group_aliases,
    group_keys,
    entity_candidates,
):
    """
    Resolve one opportunity organisation reference.

    Resolution hierarchy:

        1. Explicit organisation group
        2. Existing canonical entity
        3. Known non-entity category
        4. Unresolved

    Important distinction:

        GROUP
            The raw opportunity reference is itself a generic
            organisation-family reference.

        ENTITY
            The raw opportunity reference identifies a specific
            organisation entity.

    For an ENTITY result, group_id is also populated when that
    entity belongs to a known organisation group.
    """

    # ---------------------------------------------------------
    # 1. Explicit organisation-group reference
    # ---------------------------------------------------------

    group = resolve_group(
        value,
        group_aliases,
        group_keys
    )

    if group:
        group_id, _ = group

        return {
            "entity_id": None,
            "group_id": group_id,
            "resolution_level": "GROUP",
            "confidence_score": 1.0,
            "resolution_method": "GROUP_EXACT",
        }

    # ---------------------------------------------------------
    # 2. Existing canonical entity / alias resolution
    # ---------------------------------------------------------

    entity_id = resolve_entity(
         conn,
         value,
         entity_candidates,
    )

    if entity_id:

        return {
            "entity_id": entity_id,
            "group_id": find_group_for_entity(
                conn,
                entity_id
            ),
            "resolution_level": "ENTITY",
            "confidence_score": 1.0,
            "resolution_method": "ENTITY_RESOLUTION",
        }

    # ---------------------------------------------------------
    # 3. Known non-entity category
    # ---------------------------------------------------------

    if classify_non_entity(value):

        return {
            "entity_id": None,
            "group_id": None,
            "resolution_level": "NON_ENTITY",
            "confidence_score": 1.0,
            "resolution_method": "NON_ENTITY_CLASSIFICATION",
        }

    # ---------------------------------------------------------
    # 4. Unresolved
    # ---------------------------------------------------------

    return {
        "entity_id": None,
        "group_id": None,
        "resolution_level": "UNRESOLVED",
        "confidence_score": 0.0,
        "resolution_method": "UNRESOLVED",
    }


def extract_opportunity_references(row):
    """
    Extract the three organisation roles from an opportunity.

    Returns references for:

        FUNDING
        IMPLEMENTING
        REPORTING
    """

    (
        opportunity_id,
        funding_agencies,
        implementing_partners,
        reporting_org_name,
    ) = row

    references = []

    for name in split_values(funding_agencies):
        references.append({
            "opportunity_id": opportunity_id,
            "organisation_name": name,
            "organisation_role": "FUNDING",
        })

    for name in split_values(implementing_partners):
        references.append({
            "opportunity_id": opportunity_id,
            "organisation_name": name,
            "organisation_role": "IMPLEMENTING",
        })

    reporting = (
        str(reporting_org_name).strip()
        if reporting_org_name
        else ""
    )

    if reporting:
        references.append({
            "opportunity_id": opportunity_id,
            "organisation_name": reporting,
            "organisation_role": "REPORTING",
        })

    return references


def load_opportunities(conn):
    """
    Load opportunities and their organisation references.
    """

    if table_exists(conn, "opportunities"):
        return conn.execute("""
            SELECT
                iati_identifier AS opportunity_id,
                funding_agencies,
                implementing_partners,
                reporting_org_name
            FROM opportunities
            ORDER BY iati_identifier
        """).fetchall()

    return conn.execute("""
        SELECT
            opportunity_id,
            funding_agencies,
            implementing_partners,
            reporting_org_name
        FROM opportunity_intelligence
        ORDER BY opportunity_id
    """).fetchall()


def create_resolution_table(conn):
    """
    Create the opportunity organisation resolution table if it
    does not already exist.
    """

    conn.execute("""
        CREATE TABLE IF NOT EXISTS opportunity_organisation_resolution (
            resolution_id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id TEXT NOT NULL,
            organisation_name TEXT NOT NULL,
            organisation_role TEXT NOT NULL,
            entity_id TEXT,
            group_id TEXT,
            resolution_level TEXT NOT NULL,
            confidence_score REAL NOT NULL DEFAULT 0.0,
            resolution_method TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()


def resolve_opportunity_references(conn):
    """
    Resolve all organisation references appearing in opportunities.
    """

    group_aliases = load_group_aliases(conn)
    group_keys = load_group_keys(conn)
    entity_candidates = (
        load_entity_candidates(conn)
        + load_alias_candidates(conn)
    )

    rows = load_opportunities(conn)

    decisions = []

    for row in rows:

        references = extract_opportunity_references(row)

        for reference in references:

            result = resolve_reference(
                conn,
                reference["organisation_name"],
                group_aliases,
                group_keys,
                entity_candidates,
            )

            decisions.append({
                "opportunity_id": reference["opportunity_id"],
                "organisation_name": reference["organisation_name"],
                "organisation_role": reference["organisation_role"],
                **result,
            })

    return decisions


def persist_resolutions(conn, decisions):
    """
    Replace the current opportunity organisation resolutions
    with the newly calculated resolution set.

    This makes the resolver idempotent: running it repeatedly
    produces the same logical result rather than accumulating
    duplicate rows.
    """

    conn.execute("""
        DELETE FROM opportunity_organisation_resolution
    """)

    conn.executemany("""
        INSERT INTO opportunity_organisation_resolution (
            opportunity_id,
            organisation_name,
            organisation_role,
            entity_id,
            group_id,
            resolution_level,
            confidence_score,
            resolution_method
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (
            decision["opportunity_id"],
            decision["organisation_name"],
            decision["organisation_role"],
            decision["entity_id"],
            decision["group_id"],
            decision["resolution_level"],
            decision["confidence_score"],
            decision["resolution_method"],
        )
        for decision in decisions
    ])

    conn.commit()


def main():
    """
    Execute the opportunity organisation group resolver.
    """

    conn = sqlite3.connect(DB)

    try:
        create_resolution_table(conn)

        decisions = resolve_opportunity_references(conn)

        persist_resolutions(
            conn,
            decisions
        )

        print(
            f"Opportunity organisation resolution completed: "
            f"{len(decisions)} references."
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
