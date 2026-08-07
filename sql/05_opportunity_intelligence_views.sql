-- ============================================================================
-- 05 OPPORTUNITY INTELLIGENCE VIEWS
-- ============================================================================
--
-- Purpose:
-- Turn the 02C opportunity scoring output into an operational intelligence
-- layer for business development.
--
-- Source:
--   opportunity_intelligence
--
-- This layer intentionally does NOT change the scoring model.
-- It interprets the existing scores and evidence.
-- ============================================================================


-- ============================================================================
-- 1. EXECUTIVE SUMMARY
-- ============================================================================

DROP VIEW IF EXISTS v_opportunity_executive_summary;

CREATE VIEW v_opportunity_executive_summary AS
SELECT
    COUNT(*) AS total_opportunities,

    SUM(
        CASE
            WHEN intelligence_status = 'ACTION'
            THEN 1 ELSE 0
        END
    ) AS action_opportunities,

    SUM(
        CASE
            WHEN intelligence_status = 'MONITOR'
            THEN 1 ELSE 0
        END
    ) AS monitor_opportunities,

    SUM(
        CASE
            WHEN intelligence_status = 'LOW_PRIORITY'
            THEN 1 ELSE 0
        END
    ) AS low_priority_opportunities,

    SUM(
        CASE
            WHEN engagement_urgency = 'HIGH'
            THEN 1 ELSE 0
        END
    ) AS high_urgency_opportunities,

    SUM(
        CASE
            WHEN engagement_urgency = 'MEDIUM'
            THEN 1 ELSE 0
        END
    ) AS medium_urgency_opportunities,

    ROUND(
        AVG(opportunity_score),
        1
    ) AS average_opportunity_score,

    ROUND(
        AVG(
            CASE
                WHEN intelligence_status = 'ACTION'
                THEN opportunity_score
            END
        ),
        1
    ) AS average_action_score,

    SUM(
        CASE
            WHEN has_direct_equipment_evidence = 1
            THEN 1 ELSE 0
        END
    ) AS direct_equipment_evidence_opportunities,

    SUM(
        CASE
            WHEN has_budget_data = 1
            THEN 1 ELSE 0
        END
    ) AS opportunities_with_budget_data,

    SUM(
        CASE
            WHEN has_implementing_partner_data = 1
            THEN 1 ELSE 0
        END
    ) AS opportunities_with_partner_data

FROM opportunity_intelligence;


-- ============================================================================
-- 2. ACTION QUEUE
-- ============================================================================
--
-- This is the operational list.
-- These are opportunities that should potentially receive BD attention.
-- ============================================================================

DROP VIEW IF EXISTS v_opportunity_action_queue;

CREATE VIEW v_opportunity_action_queue AS
SELECT
    opportunity_id,
    project_title,
    country_codes,

    reporting_org_name,
    funding_agencies,
    implementing_partners,

    procurement_stage,

    primary_equipment_category,
    equipment_signal,
    equipment_target_summary,
    equipment_target_snippets,

    total_budget_amount,
    budget_currency,

    opportunity_score,
    opportunity_priority,

    procurement_relevance,
    likely_procurement_type,

    engagement_urgency,
    intelligence_confidence,

    opportunity_rationale,
    key_score_factors,

    recommended_action,

    has_direct_equipment_evidence,
    has_budget_data,
    has_implementing_partner_data,

    planned_start_date,
    actual_start_date,
    planned_end_date,
    actual_end_date,

    last_updated

FROM opportunity_intelligence

WHERE intelligence_status = 'ACTION'

ORDER BY
    CASE engagement_urgency
        WHEN 'IMMEDIATE' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        ELSE 4
    END,

    opportunity_score DESC;


-- ============================================================================
-- 3. HIGH-VALUE OPPORTUNITIES
-- ============================================================================
--
-- Highest scoring opportunities irrespective of urgency.
-- ============================================================================

DROP VIEW IF EXISTS v_top_opportunities;

CREATE VIEW v_top_opportunities AS
SELECT
    opportunity_id,
    project_title,
    country_codes,
    reporting_org_name,
    procurement_stage,
    primary_equipment_category,

    total_budget_amount,
    budget_currency,

    opportunity_score,
    opportunity_priority,

    procurement_relevance,
    engagement_urgency,
    intelligence_confidence,

    recommended_action

FROM opportunity_intelligence

WHERE opportunity_score IS NOT NULL

ORDER BY
    opportunity_score DESC,
    total_budget_amount DESC;


-- ============================================================================
-- 4. COUNTRY INTELLIGENCE
-- ============================================================================
--
-- Aggregates opportunity activity by country code.
--
-- Note:
-- Multi-country activities remain represented by their original country_codes.
-- We do not artificially split them at this stage.
-- ============================================================================

DROP VIEW IF EXISTS v_opportunity_country_intelligence;

CREATE VIEW v_opportunity_country_intelligence AS
SELECT
    country_codes,

    COUNT(*) AS opportunities,

    SUM(
        CASE
            WHEN intelligence_status = 'ACTION'
            THEN 1 ELSE 0
        END
    ) AS action_opportunities,

    SUM(
        CASE
            WHEN engagement_urgency = 'HIGH'
            THEN 1 ELSE 0
        END
    ) AS high_urgency_opportunities,

    ROUND(
        AVG(opportunity_score),
        1
    ) AS average_score,

    MAX(opportunity_score) AS highest_score,

    SUM(
        CASE
            WHEN primary_equipment_category =
                'DIAGNOSTIC EQUIPMENT'
            THEN 1 ELSE 0
        END
    ) AS diagnostic_opportunities,

    SUM(
        CASE
            WHEN primary_equipment_category =
                'MEDICAL DEVICES & EQUIPMENT'
            THEN 1 ELSE 0
        END
    ) AS medical_device_opportunities,

    SUM(
        CASE
            WHEN primary_equipment_category =
                'FACILITY INFRASTRUCTURE'
            THEN 1 ELSE 0
        END
    ) AS facility_infrastructure_opportunities,

    SUM(
        CASE
            WHEN primary_equipment_category =
                'HEALTH IT / INFORMATION SYSTEMS'
            THEN 1 ELSE 0
        END
    ) AS health_it_opportunities,

    SUM(
        CASE
            WHEN primary_equipment_category =
                'COLD CHAIN / STORAGE'
            THEN 1 ELSE 0
        END
    ) AS cold_chain_opportunities,

    SUM(
        CASE
            WHEN primary_equipment_category =
                'VEHICLES / TRANSPORT'
            THEN 1 ELSE 0
        END
    ) AS vehicle_opportunities,

    SUM(
        CASE
            WHEN primary_equipment_category = 'PPE'
            THEN 1 ELSE 0
        END
    ) AS ppe_opportunities

FROM opportunity_intelligence

GROUP BY
    country_codes

ORDER BY
    action_opportunities DESC,
    average_score DESC;


-- ============================================================================
-- 5. EQUIPMENT CATEGORY INTELLIGENCE
-- ============================================================================

DROP VIEW IF EXISTS v_opportunity_category_intelligence;

CREATE VIEW v_opportunity_category_intelligence AS
SELECT
    primary_equipment_category,

    COUNT(*) AS opportunities,

    SUM(
        CASE
            WHEN intelligence_status = 'ACTION'
            THEN 1 ELSE 0
        END
    ) AS action_opportunities,

    SUM(
        CASE
            WHEN engagement_urgency = 'HIGH'
            THEN 1 ELSE 0
        END
    ) AS high_urgency_opportunities,

    ROUND(
        AVG(opportunity_score),
        1
    ) AS average_score,

    MAX(opportunity_score) AS highest_score,

    SUM(
        CASE
            WHEN has_direct_equipment_evidence = 1
            THEN 1 ELSE 0
        END
    ) AS direct_equipment_evidence,

    SUM(
        CASE
            WHEN procurement_relevance = 'HIGH'
            THEN 1 ELSE 0
        END
    ) AS high_procurement_relevance,

    SUM(
        CASE
            WHEN procurement_relevance = 'MEDIUM'
            THEN 1 ELSE 0
        END
    ) AS medium_procurement_relevance

FROM opportunity_intelligence

GROUP BY
    primary_equipment_category

ORDER BY
    action_opportunities DESC,
    average_score DESC;


-- ============================================================================
-- 6. ORGANISATION INTELLIGENCE
-- ============================================================================
--
-- Identifies organisations associated with the strongest opportunities.
-- This becomes an input into Step 03 Donor / Organisation Intelligence.
-- ============================================================================

DROP VIEW IF EXISTS v_opportunity_organisation_intelligence;

CREATE VIEW v_opportunity_organisation_intelligence AS
SELECT
    reporting_org_name,

    COUNT(*) AS opportunities,

    SUM(
        CASE
            WHEN intelligence_status = 'ACTION'
            THEN 1 ELSE 0
        END
    ) AS action_opportunities,

    SUM(
        CASE
            WHEN engagement_urgency = 'HIGH'
            THEN 1 ELSE 0
        END
    ) AS high_urgency_opportunities,

    ROUND(
        AVG(opportunity_score),
        1
    ) AS average_score,

    MAX(opportunity_score) AS highest_score,

    SUM(
        CASE
            WHEN procurement_relevance = 'HIGH'
            THEN 1 ELSE 0
        END
    ) AS high_procurement_relevance,

    SUM(
        CASE
            WHEN has_direct_equipment_evidence = 1
            THEN 1 ELSE 0
        END
    ) AS direct_equipment_evidence,

    SUM(
        CASE
            WHEN has_budget_data = 1
            THEN 1 ELSE 0
        END
    ) AS budgeted_opportunities

FROM opportunity_intelligence

WHERE
    reporting_org_name IS NOT NULL
    AND TRIM(reporting_org_name) <> ''

GROUP BY
    reporting_org_name

ORDER BY
    action_opportunities DESC,
    average_score DESC;


-- ============================================================================
-- 7. PROCUREMENT INTELLIGENCE
-- ============================================================================
--
-- Focuses specifically on opportunities where the database has evidence
-- that procurement may be relevant.
-- ============================================================================

DROP VIEW IF EXISTS v_procurement_intelligence;

CREATE VIEW v_procurement_intelligence AS
SELECT
    opportunity_id,
    project_title,
    country_codes,

    reporting_org_name,
    funding_agencies,
    implementing_partners,

    procurement_stage,

    primary_equipment_category,
    likely_procurement_type,

    total_budget_amount,
    budget_currency,

    opportunity_score,
    opportunity_priority,

    procurement_relevance,
    engagement_urgency,
    intelligence_confidence,

    has_direct_equipment_evidence,
    has_budget_data,
    has_implementing_partner_data,

    equipment_target_summary,
    equipment_target_snippets,

    opportunity_rationale,
    recommended_action

FROM opportunity_intelligence

WHERE
    procurement_relevance IN ('HIGH', 'MEDIUM')

ORDER BY
    CASE procurement_relevance
        WHEN 'HIGH' THEN 1
        WHEN 'MEDIUM' THEN 2
        ELSE 3
    END,

    opportunity_score DESC;


-- ============================================================================
-- 8. EARLY-ENGAGEMENT PIPELINE
-- ============================================================================
--
-- Pipeline opportunities where engagement can potentially happen before
-- procurement becomes fully active.
-- ============================================================================

DROP VIEW IF EXISTS v_early_engagement_pipeline;

CREATE VIEW v_early_engagement_pipeline AS
SELECT
    opportunity_id,
    project_title,
    country_codes,

    reporting_org_name,
    funding_agencies,
    implementing_partners,

    procurement_stage,

    primary_equipment_category,

    total_budget_amount,
    budget_currency,

    opportunity_score,
    opportunity_priority,

    procurement_relevance,
    engagement_urgency,
    intelligence_confidence,

    opportunity_rationale,
    key_score_factors,
    recommended_action,

    has_direct_equipment_evidence,
    has_budget_data,
    has_implementing_partner_data,

    planned_start_date,
    planned_end_date

FROM opportunity_intelligence

WHERE
    procurement_stage = 'PIPELINE'

    AND intelligence_status IN (
        'ACTION',
        'MONITOR'
    )

ORDER BY
    opportunity_score DESC;


-- ============================================================================
-- 9. OPPORTUNITIES WITH DIRECT EQUIPMENT EVIDENCE
-- ============================================================================
--
-- These are particularly important because the source data explicitly
-- contains equipment-related evidence.
-- ============================================================================

DROP VIEW IF EXISTS v_direct_equipment_opportunities;

CREATE VIEW v_direct_equipment_opportunities AS
SELECT
    opportunity_id,
    project_title,
    country_codes,

    reporting_org_name,
    funding_agencies,
    implementing_partners,

    procurement_stage,

    primary_equipment_category,

    equipment_target_summary,
    equipment_target_snippets,

    total_budget_amount,
    budget_currency,

    opportunity_score,
    opportunity_priority,

    procurement_relevance,
    likely_procurement_type,

    engagement_urgency,
    intelligence_confidence,

    opportunity_rationale,
    recommended_action

FROM opportunity_intelligence

WHERE
    has_direct_equipment_evidence = 1

ORDER BY
    opportunity_score DESC;


-- ============================================================================
-- 10. OPPORTUNITY DETAIL
-- ============================================================================
--
-- Full intelligence record.
-- This is the source for the eventual opportunity detail interface.
-- ============================================================================

DROP VIEW IF EXISTS v_opportunity_detail;

CREATE VIEW v_opportunity_detail AS
SELECT
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

FROM opportunity_intelligence;