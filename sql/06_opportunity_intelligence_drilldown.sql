-- ============================================================
-- 06 OPPORTUNITY INTELLIGENCE DRILL-DOWN
-- Health Infrastructure Intelligence Platform
-- ============================================================

-- ------------------------------------------------------------
-- 1. OPPORTUNITY DETAIL
-- One complete intelligence record per opportunity
-- ------------------------------------------------------------

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

    -- Overall intelligence
    opportunity_score,

    opportunity_priority,

    intelligence_status,

    engagement_urgency,

    intelligence_confidence,

    -- Score components
    stage_score,

    market_fit_score,

    geographic_score,

    financial_score,

    procurement_evidence_score,

    timing_score,

    -- Intelligence interpretation
    procurement_relevance,

    likely_procurement_type,

    opportunity_rationale,

    key_score_factors,

    recommended_action,

    -- Evidence indicators
    has_direct_equipment_evidence,

    has_budget_data,

    has_implementing_partner_data

FROM opportunity_intelligence;


-- ------------------------------------------------------------
-- 2. COUNTRY OPPORTUNITY INTELLIGENCE
-- ------------------------------------------------------------

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

    SUM(
        CASE
            WHEN engagement_urgency = 'MEDIUM'
            THEN 1 ELSE 0
        END
    ) AS medium_urgency_opportunities,

    SUM(
        CASE
            WHEN procurement_stage = 'PIPELINE'
            THEN 1 ELSE 0
        END
    ) AS pipeline_opportunities,

    SUM(
        CASE
            WHEN procurement_stage = 'ACTIVE'
            THEN 1 ELSE 0
        END
    ) AS active_opportunities,

    ROUND(
        AVG(opportunity_score),
        1
    ) AS average_score,

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
    ) AS direct_equipment_evidence,

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

FROM opportunity_intelligence

GROUP BY country_codes;


-- ------------------------------------------------------------
-- 3. OPPORTUNITY PIPELINE
-- Separates pipeline and active opportunities
-- ------------------------------------------------------------

DROP VIEW IF EXISTS v_opportunity_pipeline;

CREATE VIEW v_opportunity_pipeline AS
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

    intelligence_status,

    procurement_relevance,

    engagement_urgency,

    intelligence_confidence,

    likely_procurement_type,

    equipment_target_summary,

    opportunity_rationale,

    key_score_factors,

    recommended_action,

    planned_start_date,

    actual_start_date,

    planned_end_date,

    actual_end_date,

    last_updated

FROM opportunity_intelligence

WHERE procurement_stage IN (
    'PIPELINE',
    'ACTIVE'
);


-- ------------------------------------------------------------
-- 4. HIGH-VALUE ACTION QUEUE
-- Strictly business-development focused
-- ------------------------------------------------------------

DROP VIEW IF EXISTS v_opportunity_priority_queue;

CREATE VIEW v_opportunity_priority_queue AS
SELECT

    opportunity_id,

    project_title,

    country_codes,

    reporting_org_name,

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

    likely_procurement_type,

    opportunity_rationale,

    key_score_factors,

    recommended_action,

    equipment_target_summary,

    planned_end_date,

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


-- ------------------------------------------------------------
-- 5. EQUIPMENT-FOCUSED OPPORTUNITY QUEUE
-- Useful for Faram's commercial targeting
-- ------------------------------------------------------------

DROP VIEW IF EXISTS v_opportunity_equipment_queue;

CREATE VIEW v_opportunity_equipment_queue AS
SELECT

    opportunity_id,

    project_title,

    country_codes,

    reporting_org_name,

    procurement_stage,

    primary_equipment_category,

    equipment_signal,

    equipment_target_summary,

    equipment_target_snippets,

    opportunity_score,

    opportunity_priority,

    procurement_relevance,

    engagement_urgency,

    intelligence_confidence,

    recommended_action,

    opportunity_rationale,

    key_score_factors

FROM opportunity_intelligence

WHERE
    has_direct_equipment_evidence = 1

ORDER BY

    opportunity_score DESC;