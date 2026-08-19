DROP VIEW IF EXISTS v_opportunity_intelligence_master;

CREATE VIEW v_opportunity_intelligence_master AS
SELECT
    opportunity_id,

    -- Core opportunity identity
    project_title,
    country_codes,
    reporting_org_name,
    funding_agencies,
    implementing_partners,

    -- Activity / pipeline
    activity_status_code,
    activity_status_label,
    procurement_stage,

    planned_start_date,
    actual_start_date,
    planned_end_date,
    actual_end_date,
    last_updated,

    -- Financial
    total_budget_amount,
    budget_currency,
    has_budget_data,

    -- Equipment
    primary_equipment_category,
    equipment_signal,
    equipment_target_summary,
    equipment_target_snippets,
    has_direct_equipment_evidence,

    -- Scoring
    opportunity_score,
    opportunity_priority,

    stage_score,
    market_fit_score,
    geographic_score,
    financial_score,
    procurement_evidence_score,
    timing_score,

    -- Procurement intelligence
    procurement_relevance,
    likely_procurement_type,

    -- Intelligence
    opportunity_rationale,
    key_score_factors,
    recommended_action,
    engagement_urgency,
    intelligence_confidence,

    has_implementing_partner_data,
    intelligence_status

FROM v_opportunity_detail;