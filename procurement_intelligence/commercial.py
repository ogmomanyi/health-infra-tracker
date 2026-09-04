"""Commercial intelligence derived from external procurement events."""
from __future__ import annotations
import csv
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from organisation_resolution.normalizer import normalize_name

FARAM_CATEGORIES = {"Laboratory Equipment", "Diagnostics", "Medical Equipment", "Blood Banking", "Cold Chain", "Sterilization", "PPE", "Ophthalmology", "Laboratory Consumables"}
BUYER_FIELDS = ["buyer", "country", "entity_id", "canonical_buyer", "buyer_match_status", "buyer_match_confidence", "raw_buyer_names", "event_count", "active_opportunities", "upcoming_gpn", "procurement_plans", "award_history", "high_priority_opportunities", "estimated_value_total", "estimated_value_currency", "latest_publication_date", "next_closing_date", "iati_linked_events", "project_count", "sources", "categories", "recurring_categories", "linked_projects", "faram_account_score", "faram_account_tier", "recommended_action"]

def _number(value):
    try: return float(value or 0)
    except (TypeError, ValueError): return 0.0

def _date(value):
    try: return date.fromisoformat((value or "").strip())
    except (TypeError, ValueError): return None

def _canonical_root(conn, entity_id):
    current = entity_id; visited = set()
    try:
        while current:
            if current in visited: raise RuntimeError(f"Cycle detected in organisation relationships at {current}")
            visited.add(current)
            row = conn.execute("SELECT parent_entity_id FROM organisation_relationships WHERE child_entity_id = ? AND relationship_type = 'DUPLICATE_OF'", (current,)).fetchone()
            if not row: break
            current = row[0]
    except sqlite3.OperationalError: return entity_id
    return current

def load_buyer_resolution_index(database):
    empty = {"names": {}, "canonical_names": {}}
    if database is None or not Path(database).exists(): return empty
    with sqlite3.connect(database) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"organisation_entities", "organisation_aliases"}.issubset(tables): return empty
        entities = conn.execute("SELECT entity_id, canonical_name FROM organisation_entities WHERE entity_status = 'ACTIVE'").fetchall()
        canonical = {}; by_entity = {}
        for entity_id, name in entities:
            root = _canonical_root(conn, entity_id); normalized = normalize_name(name)
            if normalized: canonical[normalized] = root
            by_entity.setdefault(root, name)
            if root == entity_id: by_entity[root] = name
        aliases = defaultdict(set)
        for entity_id, alias in conn.execute("SELECT a.entity_id, a.alias_name FROM organisation_aliases a JOIN organisation_entities e ON e.entity_id=a.entity_id WHERE e.entity_status='ACTIVE'"):
            normalized = normalize_name(alias)
            if normalized: aliases[normalized].add(_canonical_root(conn, entity_id))
        for name, ids in aliases.items():
            if len(ids) == 1: canonical.setdefault(name, next(iter(ids)))
    return {"names": canonical, "canonical_names": by_entity}

def _resolve_buyer(raw, index):
    raw = (raw or "").strip(); normalized = normalize_name(raw)
    if not normalized: return "", raw, "UNMATCHED", 0.0
    entity = index.get("names", {}).get(normalized)
    if not entity: return "", raw, "UNMATCHED", 0.0
    canonical = index.get("canonical_names", {}).get(entity, raw)
    return entity, canonical, ("CANONICAL_EXACT" if normalized == normalize_name(canonical) else "ALIAS_EXACT"), 1.0

def _safe_value_signal(items):
    by_currency = defaultdict(float)
    for event in items:
        value = _number(event.estimated_value)
        currency = (event.currency or "").strip().upper()
        if value > 0: by_currency[currency or "UNSPECIFIED"] += value
    if len(by_currency) == 1:
        currency, value = next(iter(by_currency.items())); return value, currency
    return (max(by_currency.values()) if by_currency else 0.0), "MIXED" if by_currency else ""

def _account_score(items, recurring, today):
    active = sum(e.opportunity_status == "ACTIVE_OPPORTUNITY" for e in items); high = sum(e.procurement_priority == "HIGH" for e in items)
    fit = sum(e.equipment_category in FARAM_CATEGORIES for e in items); awards = sum(e.opportunity_status == "AWARD_HISTORY" for e in items); iati = sum(bool(e.matched_iati_identifier) for e in items)
    recent = sum(1 for e in items if (d := _date(e.publication_date)) and 0 <= (today-d).days <= 90)
    value, currency = _safe_value_signal(items)
    score = min(20, active*5) + min(15, high*5) + min(15, fit*3) + min(10, len(recurring)*5) + min(10, awards*2) + min(10, iati*2) + min(10, recent*2)
    if currency != "MIXED": score += 10 if value >= 1_000_000 else 7 if value >= 250_000 else 4 if value >= 50_000 else 2 if value > 0 else 0
    return round(min(100.0, score), 1)

def _tier(score): return "A" if score >= 70 else "B" if score >= 45 else "C" if score >= 20 else "MONITOR"

def _action(tier, active, plans, gpn, awards):
    if tier == "A" and active: return "Engage now: qualify the opportunity, confirm bid route, and mobilize the tender/technical team."
    if tier == "A" and (plans or gpn): return "Pre-position: map stakeholders, procurement route and product fit before the next notice."
    if tier == "B" and active: return "Pursue: review active notices and establish the buyer/procurement contact path."
    if tier == "B" and (plans or gpn): return "Develop account: track the pipeline and prepare relevant product/manufacturer coverage."
    if awards: return "Research incumbent pattern and monitor for the buyer's next comparable procurement."
    if tier == "C": return "Monitor: retain the account on the watchlist and review new procurement signals."
    return "Monitor."

def _iati_project_index(database):
    if database is None or not Path(database).exists(): return {}
    try:
        with sqlite3.connect(database) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "activities" not in tables: return {}
            cols = {r[1] for r in conn.execute("PRAGMA table_info(activities)")}
            if "iati_identifier" not in cols: return {}
            fields = [f for f in ("iati_identifier", "project_title", "project_name", "activity_title", "activity_ref") if f in cols]
            rows = conn.execute("SELECT " + ",".join('"'+f+'"' for f in fields) + " FROM activities").fetchall()
        pos = {f:i for i,f in enumerate(fields)}; result = {}
        for row in rows:
            ident = str(row[pos["iati_identifier"]] or "").strip()
            if not ident: continue
            title = next((str(row[pos[f]]).strip() for f in ("project_title","project_name","activity_title","activity_ref") if f in pos and row[pos[f]]), "")
            result[ident] = title
        return result
    except sqlite3.Error: return {}

def build_buyer_history(events, database=None, today=None):
    today = today or date.today(); index = load_buyer_resolution_index(database); projects = _iati_project_index(database)
    grouped = defaultdict(list); meta = {}
    for event in events:
        raw = (event.buyer or "").strip(); country = (event.country or "").strip()
        if not raw: continue
        entity, canonical, status, confidence = _resolve_buyer(raw, index)
        key = (entity or "RAW:"+normalize_name(raw), country); grouped[key].append(event)
        m = meta.setdefault(key, {"entity_id":entity, "canonical":canonical, "status":status, "confidence":confidence, "raw":set()}); m["raw"].add(raw)
        if entity and status == "ALIAS_EXACT": m["canonical"] = canonical
    rows = []
    for key, items in grouped.items():
        m = meta[key]; counts = Counter(e.equipment_category for e in items if e.equipment_category); recurring = sorted(c for c,n in counts.items() if n >= 2)
        linked = [e.matched_iati_identifier for e in items if e.matched_iati_identifier]; linked_projects = sorted({projects.get(i,i) for i in linked if projects.get(i,i)})
        publications = [e.publication_date for e in items if e.publication_date]; closing = [_date(e.closing_date) for e in items if _date(e.closing_date)]
        active=sum(e.opportunity_status=="ACTIVE_OPPORTUNITY" for e in items); plans=sum(e.opportunity_status=="PROCUREMENT_PLAN" for e in items); gpn=sum(e.opportunity_status=="UPCOMING_GPN" for e in items); awards=sum(e.opportunity_status=="AWARD_HISTORY" for e in items); high=sum(e.procurement_priority=="HIGH" for e in items)
        value, currency = _safe_value_signal(items); score=_account_score(items, recurring, today); tier=_tier(score)
        rows.append({"buyer":m["canonical"],"country":key[1],"entity_id":m["entity_id"],"canonical_buyer":m["canonical"],"buyer_match_status":m["status"],"buyer_match_confidence":f"{m['confidence']:.3f}","raw_buyer_names":"; ".join(sorted(m["raw"])),"event_count":str(len(items)),"active_opportunities":str(active),"upcoming_gpn":str(gpn),"procurement_plans":str(plans),"award_history":str(awards),"high_priority_opportunities":str(high),"estimated_value_total":f"{value:.2f}" if value else "","estimated_value_currency":currency,"latest_publication_date":max(publications) if publications else "","next_closing_date":min(closing).isoformat() if closing else "","iati_linked_events":str(len(linked)),"project_count":str(len(set(linked))),"sources":"; ".join(sorted({e.source for e in items if e.source})),"categories":"; ".join(sorted(counts)),"recurring_categories":"; ".join(recurring),"linked_projects":"; ".join(linked_projects),"faram_account_score":f"{score:.1f}","faram_account_tier":tier,"recommended_action":_action(tier,active,plans,gpn,awards)})
    return sorted(rows,key=lambda r:(-float(r["faram_account_score"]),-int(r["active_opportunities"]),-int(r["high_priority_opportunities"]),-int(r["award_history"]),r["buyer"].lower()))

def write_buyer_history(path, events, database=None, today=None):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); rows=build_buyer_history(events,database=database,today=today)
    with path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=BUYER_FIELDS); writer.writeheader(); writer.writerows(rows)
    return len(rows)
