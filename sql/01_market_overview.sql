-- ============================================================
-- IATI HEALTH INTELLIGENCE
-- 01 - MARKET OVERVIEW
-- ============================================================

-- 1. Overall project universe
SELECT
    COUNT(*) AS total_projects,

    SUM(
        CASE
            WHEN activity_status_code = '1'
            THEN 1 ELSE 0
        END
    ) AS pipeline_projects,

    SUM(
        CASE
            WHEN activity_status_code = '2'
            THEN 1 ELSE 0
        END
    ) AS active_projects,

    SUM(
        CASE
            WHEN equipment_target_summary IS NOT NULL
             AND TRIM(equipment_target_summary) <> ''
            THEN 1 ELSE 0
        END
    ) AS equipment_relevant_projects

FROM activities;


-- ============================================================
-- 2. Projects by country
-- ============================================================

SELECT
    ac.country_code,

    COUNT(DISTINCT ac.activity_id) AS projects,

    COUNT(
        DISTINCT CASE
            WHEN a.activity_status_code = '1'
            THEN a.iati_identifier
        END
    ) AS pipeline_projects,

    COUNT(
        DISTINCT CASE
            WHEN a.activity_status_code = '2'
            THEN a.iati_identifier
        END
    ) AS active_projects,

    COUNT(
        DISTINCT CASE
            WHEN a.equipment_target_summary IS NOT NULL
             AND TRIM(a.equipment_target_summary) <> ''
            THEN a.iati_identifier
        END
    ) AS equipment_relevant_projects

FROM activity_countries ac

JOIN activities a
    ON a.iati_identifier = ac.activity_id

GROUP BY ac.country_code

ORDER BY projects DESC;


-- ============================================================
-- 3. Projects by reporting organisation
-- ============================================================

SELECT
    reporting_org_name,

    COUNT(*) AS projects,

    SUM(
        CASE
            WHEN activity_status_code = '1'
            THEN 1 ELSE 0
        END
    ) AS pipeline_projects,

    SUM(
        CASE
            WHEN activity_status_code = '2'
            THEN 1 ELSE 0
        END
    ) AS active_projects

FROM activities

WHERE reporting_org_name IS NOT NULL
  AND TRIM(reporting_org_name) <> ''

GROUP BY reporting_org_name

ORDER BY projects DESC
LIMIT 50;


-- ============================================================
-- 4. Equipment opportunity universe
-- ============================================================

SELECT
    equipment_target_summary,

    COUNT(*) AS projects

FROM activities

WHERE equipment_target_summary IS NOT NULL
  AND TRIM(equipment_target_summary) <> ''

GROUP BY equipment_target_summary

ORDER BY projects DESC;
