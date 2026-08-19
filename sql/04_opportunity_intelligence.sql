-- ============================================================
-- 04_opportunity_intelligence.sql
-- OPPORTUNITY INTELLIGENCE
--
-- Builds an actionable intelligence layer on top of
-- opportunity_scores.
--
-- 02B = Procurement Intelligence
-- 02C = Opportunity Scoring
-- 02D = Opportunity Intelligence
-- ============================================================

DROP TABLE IF EXISTS opportunity_intelligence;

CREATE TABLE opportunity_intelligence AS

WITH base AS (

    SELECT
        activity_id,
        project_title,
        country_codes,
        reporting_org_name,
        funding_agencies,
        implementing_partners,

        activity_status_code,
        activity_status_label,

        planned_start_date,
        actual_start_date,
        planned_end_date,
        actual_end_date,

        total_budget_amount,
        budget_currency,

        equipment_target_summary,
        equipment_target_snippets,

        last_updated,

        procurement_stage,
        equipment_signal,
        primary_equipment_category,

        stage_score,
        market_fit_score,
        geographic_score,
        financial_score,
        procurement_evidence_score,
        timing_score,

        opportunity_score,
        opportunity_priority

    FROM opportunity_scores
)

SELECT

    ------------------------------------------------------------
    -- OPPORTUNITY IDENTITY
    ------------------------------------------------------------

    activity_id AS opportunity_id,

    project_title,

    country_codes,

    reporting_org_name,

    funding_agencies,

    implementing_partners,


    ------------------------------------------------------------
    -- PROJECT STATUS / TIMING
    ------------------------------------------------------------

    activity_status_code,

    activity_status_label,

    procurement_stage,

    planned_start_date,

    actual_start_date,

    planned_end_date,

    actual_end_date,

    last_updated,


    ------------------------------------------------------------
    -- COMMERCIAL VALUE
    ------------------------------------------------------------

    total_budget_amount,

    budget_currency,


    ------------------------------------------------------------
    -- EQUIPMENT INTELLIGENCE
    ------------------------------------------------------------

    primary_equipment_category,

    equipment_signal,

    equipment_target_summary,

    equipment_target_snippets,


    ------------------------------------------------------------
    -- SCORE
    ------------------------------------------------------------

    opportunity_score,

    opportunity_priority,

    stage_score,

    market_fit_score,

    geographic_score,

    financial_score,

    procurement_evidence_score,

    timing_score,


    ------------------------------------------------------------
    -- INTELLIGENCE: PROCUREMENT RELEVANCE
    ------------------------------------------------------------

    CASE

        WHEN procurement_evidence_score >= 15
             AND equipment_signal IS NOT NULL
        THEN 'HIGH'

        WHEN procurement_evidence_score >= 10
        THEN 'MEDIUM'

        ELSE 'LOW'

    END AS procurement_relevance,


    ------------------------------------------------------------
    -- INTELLIGENCE: PROCUREMENT TYPE
    ------------------------------------------------------------

    CASE

        WHEN primary_equipment_category = 'DIAGNOSTIC EQUIPMENT'
        THEN 'Diagnostic equipment / laboratory procurement'

        WHEN primary_equipment_category = 'MEDICAL DEVICES & EQUIPMENT'
        THEN 'Medical equipment / biomedical procurement'

        WHEN primary_equipment_category = 'HEALTH IT / INFORMATION SYSTEMS'
        THEN 'Health IT / digital health procurement'

        WHEN primary_equipment_category = 'COLD CHAIN / STORAGE'
        THEN 'Cold chain / storage procurement'

        WHEN primary_equipment_category = 'VEHICLES / TRANSPORT'
        THEN 'Healthcare transport / vehicle procurement'

        WHEN primary_equipment_category = 'FACILITY INFRASTRUCTURE'
        THEN 'Health facility infrastructure / equipment procurement'

        WHEN primary_equipment_category = 'PPE'
        THEN 'PPE / protective equipment procurement'

        ELSE 'Other healthcare procurement'

    END AS likely_procurement_type,


    ------------------------------------------------------------
    -- INTELLIGENCE: OPPORTUNITY RATIONALE
    ------------------------------------------------------------

    TRIM(

        CASE

            WHEN procurement_evidence_score >= 15
            THEN 'Strong evidence of equipment-related procurement. '

            WHEN procurement_evidence_score >= 10
            THEN 'Moderate evidence of equipment-related procurement. '

            ELSE
                'Limited direct evidence of procurement. '

        END

        ||

        CASE

            WHEN financial_score >= 15
            THEN 'Project has strong financial scale. '

            WHEN financial_score >= 10
            THEN 'Project has meaningful financial scale. '

            ELSE
                'Project has relatively limited financial scale. '

        END

        ||

        CASE

            WHEN timing_score >= 15
            THEN 'Timing is favourable for engagement. '

            WHEN timing_score >= 10
            THEN 'Timing provides a potential engagement window. '

            ELSE
                'Timing requires monitoring. '

        END

        ||

        CASE

            WHEN market_fit_score >= 15
            THEN 'Strong alignment with target market. '

            WHEN market_fit_score >= 10
            THEN 'Moderate alignment with target market. '

            ELSE
                'Limited current market alignment. '

        END

    ) AS opportunity_rationale,


    ------------------------------------------------------------
    -- INTELLIGENCE: KEY SCORE FACTORS
    ------------------------------------------------------------

    TRIM(

        'Stage: ' || COALESCE(stage_score, 0)
        || '/20; '

        || 'Market fit: ' || COALESCE(market_fit_score, 0)
        || '/20; '

        || 'Geography: ' || COALESCE(geographic_score, 0)
        || '/15; '

        || 'Financial: ' || COALESCE(financial_score, 0)
        || '/15; '

        || 'Procurement evidence: ' || COALESCE(procurement_evidence_score, 0)
        || '/15; '

        || 'Timing: ' || COALESCE(timing_score, 0)
        || '/15'

    ) AS key_score_factors,


    ------------------------------------------------------------
    -- INTELLIGENCE: RECOMMENDED ACTION
    ------------------------------------------------------------

    CASE

        WHEN opportunity_priority = 'A - PRIORITY OPPORTUNITY'
        THEN 'Immediate commercial engagement. Identify decision makers, implementing partners and procurement pathway.'

        WHEN opportunity_priority = 'B - STRONG OPPORTUNITY'
             AND procurement_stage = 'PIPELINE'
        THEN 'Early engagement. Identify implementing organisation and donor contacts and monitor procurement development.'

        WHEN opportunity_priority = 'B - STRONG OPPORTUNITY'
             AND procurement_stage = 'ACTIVE'
        THEN 'Active business development. Engage relevant organisation and identify equipment/procurement requirements.'

        WHEN opportunity_priority = 'C - MONITOR'
             AND procurement_stage = 'PIPELINE'
        THEN 'Monitor pipeline. Track project development and revisit when procurement evidence strengthens.'

        WHEN opportunity_priority = 'C - MONITOR'
             AND procurement_stage = 'ACTIVE'
        THEN 'Qualify opportunity. Determine whether equipment requirements justify commercial engagement.'

        WHEN opportunity_priority = 'D - LOW PRIORITY'
        THEN 'Low priority. Monitor passively unless new procurement evidence emerges.'

        ELSE
            'Review opportunity and determine appropriate engagement.'

    END AS recommended_action,


    ------------------------------------------------------------
    -- INTELLIGENCE: URGENCY
    ------------------------------------------------------------

    CASE

        WHEN opportunity_priority = 'A - PRIORITY OPPORTUNITY'
        THEN 'IMMEDIATE'

        WHEN opportunity_priority = 'B - STRONG OPPORTUNITY'
             AND procurement_stage = 'ACTIVE'
        THEN 'HIGH'

        WHEN opportunity_priority = 'B - STRONG OPPORTUNITY'
             AND procurement_stage = 'PIPELINE'
        THEN 'MEDIUM'

        WHEN opportunity_priority = 'C - MONITOR'
        THEN 'LOW'

        ELSE
            'PASSIVE'

    END AS engagement_urgency,


    ------------------------------------------------------------
    -- INTELLIGENCE CONFIDENCE
    --
    -- Confidence is based on the strength of the underlying
    -- evidence rather than the opportunity score itself.
    ------------------------------------------------------------

    CASE

        WHEN equipment_target_snippets IS NOT NULL
             AND TRIM(equipment_target_snippets) <> ''
             AND procurement_evidence_score >= 15
        THEN 'HIGH'

        WHEN equipment_target_summary IS NOT NULL
             AND TRIM(equipment_target_summary) <> ''
             AND procurement_evidence_score >= 10
        THEN 'MEDIUM'

        ELSE
            'LOW'

    END AS intelligence_confidence,


    ------------------------------------------------------------
    -- DATA / INFERENCE FLAGS
    ------------------------------------------------------------

    CASE

        WHEN equipment_target_snippets IS NOT NULL
             AND TRIM(equipment_target_snippets) <> ''
        THEN 1

        ELSE 0

    END AS has_direct_equipment_evidence,


    CASE

        WHEN total_budget_amount IS NOT NULL
             AND total_budget_amount > 0
        THEN 1

        ELSE 0

    END AS has_budget_data,


    CASE

        WHEN implementing_partners IS NOT NULL
             AND TRIM(implementing_partners) <> ''
        THEN 1

        ELSE 0

    END AS has_implementing_partner_data,


    ------------------------------------------------------------
    -- RECORD CLASSIFICATION
    ------------------------------------------------------------

    CASE

        WHEN opportunity_priority = 'A - PRIORITY OPPORTUNITY'
        THEN 'ACTION'

        WHEN opportunity_priority = 'B - STRONG OPPORTUNITY'
        THEN 'ACTION'

        WHEN opportunity_priority = 'C - MONITOR'
        THEN 'MONITOR'

        ELSE
            'LOW_PRIORITY'

    END AS intelligence_status

FROM base;


-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_oi_score
ON opportunity_intelligence(opportunity_score DESC);

CREATE INDEX idx_oi_priority
ON opportunity_intelligence(opportunity_priority);

CREATE INDEX idx_oi_country
ON opportunity_intelligence(country_codes);

CREATE INDEX idx_oi_category
ON opportunity_intelligence(primary_equipment_category);

CREATE INDEX idx_oi_organisation
ON opportunity_intelligence(reporting_org_name);

CREATE INDEX idx_oi_stage
ON opportunity_intelligence(procurement_stage);

CREATE INDEX idx_oi_urgency
ON opportunity_intelligence(engagement_urgency);


-- ============================================================
-- VALIDATION
-- ============================================================

SELECT
    COUNT(*) AS total_opportunities,

    SUM(
        CASE
            WHEN intelligence_status = 'ACTION'
            THEN 1
            ELSE 0
        END
    ) AS action_opportunities,

    SUM(
        CASE
            WHEN intelligence_status = 'MONITOR'
            THEN 1
            ELSE 0
        END
    ) AS monitor_opportunities,

    SUM(
        CASE
            WHEN intelligence_status = 'LOW_PRIORITY'
            THEN 1
            ELSE 0
        END
    ) AS low_priority_opportunities

FROM opportunity_intelligence;