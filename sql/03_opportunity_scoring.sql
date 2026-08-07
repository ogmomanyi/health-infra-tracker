DROP VIEW IF EXISTS opportunity_scores;

CREATE VIEW opportunity_scores AS

WITH base AS (
    SELECT
        po.*,

        /* ---------------------------------------------------------
           1. PROCUREMENT STAGE SCORE
           Pipeline gets a higher score because early visibility
           creates more time to position with the buyer/implementer.
           --------------------------------------------------------- */
        CASE
            WHEN procurement_stage = 'PIPELINE' THEN 15
            WHEN procurement_stage = 'ACTIVE' THEN 10
            ELSE 0
        END AS stage_score,

        /* ---------------------------------------------------------
           2. EQUIPMENT / MARKET FIT
           Higher = closer to Faram's core business.
           --------------------------------------------------------- */
        CASE
            WHEN primary_equipment_category = 'DIAGNOSTIC EQUIPMENT'
                THEN 20

            WHEN primary_equipment_category = 'MEDICAL DEVICES & EQUIPMENT'
                THEN 20

            WHEN primary_equipment_category = 'COLD CHAIN / STORAGE'
                THEN 15

            WHEN primary_equipment_category = 'HEALTH IT / INFORMATION SYSTEMS'
                THEN 10

            WHEN primary_equipment_category = 'FACILITY INFRASTRUCTURE'
                THEN 7

            WHEN primary_equipment_category = 'VEHICLES / TRANSPORT'
                THEN 3

            WHEN primary_equipment_category = 'PPE'
                THEN 5

            ELSE 0
        END AS market_fit_score,

        /* ---------------------------------------------------------
           3. GEOGRAPHIC SCORE
           Kenya gets maximum priority.
           East Africa gets strong priority.
           Other African markets remain relevant.
           --------------------------------------------------------- */
        CASE

            WHEN country_codes = 'KE'
                THEN 20

            WHEN country_codes IN ('UG','TZ','RW','SS','SO','ET','CD')
                THEN 15

            WHEN country_codes LIKE '%KE%'
                THEN 15

            WHEN country_codes LIKE '%UG%'
              OR country_codes LIKE '%TZ%'
              OR country_codes LIKE '%RW%'
              OR country_codes LIKE '%SS%'
              OR country_codes LIKE '%SO%'
                THEN 12

            WHEN country_codes IS NOT NULL
                THEN 7

            ELSE 0

        END AS geographic_score,

        /* ---------------------------------------------------------
           4. PROJECT VALUE SCORE
           
           This is deliberately logarithmic rather than assigning
           enormous weight to very large projects.
           --------------------------------------------------------- */
        CASE
            WHEN total_budget_amount IS NULL THEN 0

            WHEN total_budget_amount >= 100000000
                THEN 15

            WHEN total_budget_amount >= 50000000
                THEN 13

            WHEN total_budget_amount >= 10000000
                THEN 11

            WHEN total_budget_amount >= 5000000
                THEN 9

            WHEN total_budget_amount >= 1000000
                THEN 7

            WHEN total_budget_amount >= 500000
                THEN 5

            WHEN total_budget_amount >= 100000
                THEN 3

            ELSE 1
        END AS financial_score,

        /* ---------------------------------------------------------
           5. PROCUREMENT EVIDENCE
           
           Score based on actual procurement-related information
           captured in the opportunity record.
           --------------------------------------------------------- */
        CASE

            WHEN
                procurement_stage = 'PIPELINE'
                AND (
                    equipment_target_summary IS NOT NULL
                    AND TRIM(equipment_target_summary) <> ''
                )
                THEN 15

            WHEN
                equipment_target_summary IS NOT NULL
                AND TRIM(equipment_target_summary) <> ''
                THEN 12

            ELSE 5

        END AS procurement_evidence_score,

        /* ---------------------------------------------------------
           6. DATA RECENCY / TIMING
           --------------------------------------------------------- */
        CASE
            WHEN last_updated IS NULL THEN 3

            WHEN julianday('now') - julianday(last_updated) <= 30
                THEN 10

            WHEN julianday('now') - julianday(last_updated) <= 90
                THEN 8

            WHEN julianday('now') - julianday(last_updated) <= 180
                THEN 6

            WHEN julianday('now') - julianday(last_updated) <= 365
                THEN 4

            ELSE 2
        END AS timing_score

    FROM procurement_opportunities po
)

SELECT
    base.*,

    /* -------------------------------------------------------------
       TOTAL SCORE
       Maximum = 105
       ------------------------------------------------------------- */

    (
        stage_score
        + market_fit_score
        + geographic_score
        + financial_score
        + procurement_evidence_score
        + timing_score
    ) AS opportunity_score,

    /* -------------------------------------------------------------
       PRIORITY CLASSIFICATION
       ------------------------------------------------------------- */

    CASE

        WHEN (
            stage_score
            + market_fit_score
            + geographic_score
            + financial_score
            + procurement_evidence_score
            + timing_score
        ) >= 80
            THEN 'A - HIGH PRIORITY'

        WHEN (
            stage_score
            + market_fit_score
            + geographic_score
            + financial_score
            + procurement_evidence_score
            + timing_score
        ) >= 65
            THEN 'B - STRONG OPPORTUNITY'

        WHEN (
            stage_score
            + market_fit_score
            + geographic_score
            + financial_score
            + procurement_evidence_score
            + timing_score
        ) >= 50
            THEN 'C - MONITOR'

        ELSE 'D - LOW PRIORITY'

    END AS opportunity_priority

FROM base;