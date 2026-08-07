-- ============================================================
-- STEP 2B: PROCUREMENT INTELLIGENCE
-- ============================================================

DROP TABLE IF EXISTS procurement_opportunities;

CREATE TABLE procurement_opportunities AS

SELECT
    a.iati_identifier AS activity_id,

    a.project_title,

    a.country_codes,

    a.reporting_org_name,

    a.funding_agencies,

    a.implementing_partners,

    a.activity_status_code,

    a.activity_status_label,

    a.planned_start_date,

    a.actual_start_date,

    a.planned_end_date,

    a.actual_end_date,

    a.total_budget_amount,

    a.budget_currency,

    a.equipment_target_summary,

    a.equipment_target_snippets,

    a.last_updated,

    CASE
        WHEN a.activity_status_code = '1'
            THEN 'PIPELINE'

        WHEN a.activity_status_code = '2'
            THEN 'ACTIVE'

        WHEN a.activity_status_code = '4'
            THEN 'CLOSED'

        ELSE 'UNKNOWN'
    END AS procurement_stage,

    CASE
        WHEN a.equipment_target_summary IS NOT NULL
             AND TRIM(a.equipment_target_summary) <> ''
            THEN 1
        ELSE 0
    END AS equipment_signal,

    CASE
        WHEN a.equipment_target_summary LIKE '%Diagnostic Equipment%'
            THEN 'DIAGNOSTIC EQUIPMENT'

        WHEN a.equipment_target_summary LIKE '%Medical Devices%'
            THEN 'MEDICAL DEVICES & EQUIPMENT'

        WHEN a.equipment_target_summary LIKE '%Cold Chain%'
            THEN 'COLD CHAIN / STORAGE'

        WHEN a.equipment_target_summary LIKE '%IT / Health Information%'
            THEN 'HEALTH IT / INFORMATION SYSTEMS'

        WHEN a.equipment_target_summary LIKE '%Vehicles%'
            THEN 'VEHICLES / TRANSPORT'

        WHEN a.equipment_target_summary LIKE '%PPE%'
            THEN 'PPE'

        WHEN a.equipment_target_summary LIKE '%Facility Infrastructure%'
            THEN 'FACILITY INFRASTRUCTURE'

        ELSE NULL
    END AS primary_equipment_category

FROM activities a

WHERE
    a.equipment_target_summary IS NOT NULL
    AND TRIM(a.equipment_target_summary) <> '';