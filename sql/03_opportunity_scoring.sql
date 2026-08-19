DROP VIEW IF EXISTS opportunity_scores;

CREATE VIEW opportunity_scores AS

WITH classified AS (

    SELECT
        a.*,

        /* ============================================================
           DERIVE PRIMARY EQUIPMENT CATEGORY
           ============================================================ */

        CASE
            WHEN LOWER(COALESCE(a.equipment_target_summary, '')) LIKE '%diagnostic%'
                THEN 'DIAGNOSTIC EQUIPMENT'

            WHEN LOWER(COALESCE(a.equipment_target_summary, '')) LIKE '%laboratory%'
                THEN 'DIAGNOSTIC EQUIPMENT'

            WHEN LOWER(COALESCE(a.equipment_target_summary, '')) LIKE '%medical device%'
                THEN 'MEDICAL DEVICES & EQUIPMENT'

            WHEN LOWER(COALESCE(a.equipment_target_summary, '')) LIKE '%cold chain%'
                THEN 'COLD CHAIN / STORAGE'

            WHEN LOWER(COALESCE(a.equipment_target_summary, '')) LIKE '%ppe%'
                THEN 'PPE'

            WHEN LOWER(COALESCE(a.equipment_target_summary, '')) LIKE '%health it%'
                THEN 'HEALTH IT / INFORMATION SYSTEMS'

            WHEN LOWER(COALESCE(a.equipment_target_summary, '')) LIKE '%facility infrastructure%'
                THEN 'FACILITY INFRASTRUCTURE'

            WHEN LOWER(COALESCE(a.equipment_target_summary, '')) LIKE '%vehicle%'
                THEN 'VEHICLES / TRANSPORT'

            WHEN TRIM(COALESCE(a.equipment_target_summary, '')) <> ''
                THEN TRIM(a.equipment_target_summary)

            ELSE NULL
        END AS primary_equipment_category,

        /* ============================================================
           EQUIPMENT SIGNAL
           ============================================================ */

        CASE
            WHEN TRIM(COALESCE(a.equipment_target_summary, '')) <> ''
                THEN 1

            WHEN TRIM(COALESCE(a.equipment_target_snippets, '')) <> ''
                THEN 1

            ELSE 0
        END AS equipment_signal

    FROM activities a
),

/* ================================================================
   STATIC FX RATES
   USD VALUE OF ONE UNIT OF LOCAL CURRENCY
   ================================================================ */

fx_rates(currency, usd_rate) AS (

    VALUES
        ('USD', 1.0),
        ('EUR', 1.17),
        ('GBP', 1.35),
        ('KES', 0.00775),
        ('UGX', 0.00027),
        ('TZS', 0.00039),
        ('RWF', 0.00069),
        ('ETB', 0.00725),
        ('SSP', 0.00077),
        ('SOS', 0.00775),
        ('CDF', 0.00035),
        ('NGN', 0.00077),
        ('ZAR', 0.055),
        ('EGP', 0.019),
        ('GHS', 0.078),
        ('XOF', 0.00180),
        ('XAF', 0.00180),
        ('CAD', 0.73),
        ('AUD', 0.65),
        ('CHF', 1.25),
        ('SEK', 0.108),
        ('NOK', 0.095),
        ('DKK', 0.157),
        ('JPY', 0.0067),
        ('CNY', 0.139),
        ('INR', 0.0117)
),

/* ================================================================
   NORMALISE BUDGET
   ================================================================ */

base AS (

    SELECT
        c.*,

        CASE
            WHEN c.total_budget_amount IS NULL
                THEN NULL

            WHEN c.total_budget_amount <= 0
                THEN NULL

            WHEN c.budget_currency IS NULL
                THEN NULL

            WHEN TRIM(c.budget_currency) = ''
                THEN NULL

            WHEN UPPER(TRIM(c.budget_currency)) = 'MIXED'
                THEN NULL

            WHEN fx.usd_rate IS NULL
                THEN NULL

            ELSE c.total_budget_amount * fx.usd_rate
        END AS budget_usd,

        CASE
            WHEN c.total_budget_amount IS NULL
                THEN 'NO_BUDGET'

            WHEN c.total_budget_amount <= 0
                THEN 'NO_BUDGET'

            WHEN c.budget_currency IS NULL
                THEN 'UNKNOWN_CURRENCY'

            WHEN TRIM(c.budget_currency) = ''
                THEN 'UNKNOWN_CURRENCY'

            WHEN UPPER(TRIM(c.budget_currency)) = 'MIXED'
                THEN 'UNKNOWN_CURRENCY'

            WHEN fx.usd_rate IS NULL
                THEN 'UNKNOWN_CURRENCY'

            ELSE 'CONVERTED'
        END AS budget_normalization_status

    FROM classified c

    LEFT JOIN fx_rates fx
        ON UPPER(TRIM(c.budget_currency)) = fx.currency
),

/* ================================================================
   SCORE COMPONENTS
   ================================================================ */

scored AS (

    SELECT
        b.*,

        /* ============================================================
           1. MARKET / EQUIPMENT FIT — MAX 25
           ============================================================ */

        CASE

            WHEN b.primary_equipment_category = 'DIAGNOSTIC EQUIPMENT'
                THEN 25

            WHEN b.primary_equipment_category = 'MEDICAL DEVICES & EQUIPMENT'
                THEN 25

            WHEN b.primary_equipment_category = 'COLD CHAIN / STORAGE'
                THEN 20

            WHEN b.primary_equipment_category = 'PPE'
                THEN 12

            WHEN b.primary_equipment_category = 'HEALTH IT / INFORMATION SYSTEMS'
                THEN 10

            WHEN b.primary_equipment_category = 'FACILITY INFRASTRUCTURE'
                THEN 7

            WHEN b.primary_equipment_category = 'VEHICLES / TRANSPORT'
                THEN 3

            ELSE 0

        END AS market_fit_score,

        /* ============================================================
           2. GEOGRAPHIC FIT — MAX 20
           ============================================================ */

        CASE

            WHEN TRIM(COALESCE(b.country_codes, '')) = 'KE'
                THEN 20

            WHEN TRIM(COALESCE(b.country_codes, '')) IN ('UG', 'TZ', 'RW')
                THEN 17

            WHEN TRIM(COALESCE(b.country_codes, '')) IN
                 ('ET', 'SS', 'SO', 'CD')
                THEN 14

            WHEN b.country_codes LIKE '%KE%'
                 AND (
                     b.country_codes LIKE '%UG%'
                     OR b.country_codes LIKE '%TZ%'
                     OR b.country_codes LIKE '%RW%'
                 )
                THEN 17

            WHEN TRIM(COALESCE(b.country_codes, '')) <> ''
                THEN 10

            ELSE 0

        END AS geographic_score,

        /* ============================================================
           3. PROCUREMENT READINESS — MAX 15

           IATI activity status:
           2 = Implementation / Active
           ============================================================ */

        CASE

            WHEN b.activity_status_code = '2'
                THEN 12

            WHEN b.activity_status_code = '3'
                THEN 15

            WHEN b.activity_status_code = '4'
                THEN 0

            ELSE 5

        END AS stage_score,

        /* ============================================================
           4. PROCUREMENT / EQUIPMENT EVIDENCE — MAX 15
           ============================================================ */

        CASE

            WHEN TRIM(COALESCE(b.equipment_target_summary, '')) <> ''
                 AND (
                     LOWER(b.equipment_target_summary) LIKE '%diagnostic%'
                     OR LOWER(b.equipment_target_summary) LIKE '%equipment%'
                     OR LOWER(b.equipment_target_summary) LIKE '%laboratory%'
                     OR LOWER(b.equipment_target_summary) LIKE '%cold chain%'
                     OR LOWER(b.equipment_target_summary) LIKE '%medical device%'
                     OR LOWER(b.equipment_target_summary) LIKE '%pcr%'
                     OR LOWER(b.equipment_target_summary) LIKE '%ultrasound%'
                     OR LOWER(b.equipment_target_summary) LIKE '%centrifuge%'
                     OR LOWER(b.equipment_target_summary) LIKE '%analy%'
                 )
                THEN 15

            WHEN TRIM(COALESCE(b.equipment_target_summary, '')) <> ''
                THEN 10

            WHEN b.equipment_signal = 1
                THEN 7

            ELSE 0

        END AS procurement_evidence_score,

        /* ============================================================
           5. FINANCIAL ATTRACTIVENESS — MAX 15
           ============================================================ */

        CASE

            WHEN b.budget_usd IS NULL
                THEN 0

            WHEN b.budget_usd >= 10000000
                THEN 15

            WHEN b.budget_usd >= 5000000
                THEN 13

            WHEN b.budget_usd >= 1000000
                THEN 10

            WHEN b.budget_usd >= 500000
                THEN 7

            WHEN b.budget_usd >= 100000
                THEN 4

            ELSE 2

        END AS financial_score,

        /* ============================================================
           6. DATA RECENCY — MAX 10
           ============================================================ */

        CASE

            WHEN b.last_updated IS NULL
                THEN 3

            WHEN TRIM(b.last_updated) = ''
                THEN 3

            WHEN julianday('now') - julianday(b.last_updated) <= 30
                THEN 10

            WHEN julianday('now') - julianday(b.last_updated) <= 90
                THEN 8

            WHEN julianday('now') - julianday(b.last_updated) <= 180
                THEN 6

            WHEN julianday('now') - julianday(b.last_updated) <= 365
                THEN 4

            ELSE 2

        END AS timing_score

    FROM base b
),

/* ================================================================
   FINAL SCORE
   ================================================================ */

final_scores AS (

    SELECT
        s.*,

        (
            s.market_fit_score
            + s.geographic_score
            + s.stage_score
            + s.procurement_evidence_score
            + s.financial_score
            + s.timing_score
        ) AS opportunity_score

    FROM scored s
)

/* ================================================================
   FINAL VIEW
   ================================================================ */

SELECT
    f.*,

    CASE

        WHEN f.opportunity_score >= 75
            THEN 'VERY HIGH'

        WHEN f.opportunity_score >= 65
            THEN 'HIGH'

        WHEN f.opportunity_score >= 55
            THEN 'MEDIUM'

        WHEN f.opportunity_score >= 40
            THEN 'LOW'

        ELSE 'VERY LOW'

    END AS opportunity_priority

FROM final_scores f;