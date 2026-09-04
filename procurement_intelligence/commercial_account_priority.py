"""Combine buyer demand, procurement opportunity, catalogue fit and Faram familiarity."""
from __future__ import annotations
import argparse,csv,re
from datetime import date
from pathlib import Path

FIELDS=["target_account_id","account_name","organisation_entity_id","country","account_type","crm_stage","buyer_demand_score","buyer_demand_tier","opportunity_score","active_opportunities","high_priority_opportunities","upcoming_pipeline","estimated_opportunity_value","catalogue_fit_score","catalogue_fit_status","catalogue_matched_events","catalogue_matched_products","historical_familiarity_score","historical_familiarity_band","historical_evidence_count","timing_score","next_closing_date","commercial_account_priority_score","commercial_account_priority_tier","priority_reason","recommended_action","procurement_event_ids","familiarity_evidence_ids"]
COUNTRIES={"kenya":"KE","ke":"KE","uganda":"UG","ug":"UG","rwanda":"RW","rw":"RW","ethiopia":"ET","et":"ET","somalia":"SO","so":"SO","south sudan":"SS","ss":"SS","democratic republic of the congo":"CD","drc":"CD","cd":"CD"}

def text(v): return " ".join(str(v or "").split())
def norm(v): return re.sub(r"[^a-z0-9]+"," ",text(v).lower()).strip()
def num(v):
    try:return float(v or 0)
    except (TypeError,ValueError):return 0.0
def integer(v):
    try:return int(float(v or 0))
    except (TypeError,ValueError):return 0
def parsed_date(v):
    try:return date.fromisoformat(text(v))
    except (TypeError,ValueError):return None
def country_code(v):
    n=norm(v); return COUNTRIES.get(n,n.upper() if len(n)==2 else "")
def load_csv(path):
    if not path.exists(): return []
    with path.open(newline="",encoding="utf-8") as h:return list(csv.DictReader(h))
def account_countries(account):
    out=set()
    for field in ("country_codes","country_names","country"):
        for value in text(account.get(field)).split(";"):
            code=country_code(value)
            if code: out.add(code)
    return out
def country_matches(account,value):
    target=country_code(value); allowed=account_countries(account)
    return not target or not allowed or target in allowed

def account_row_matches(account,row):
    entity=text(account.get("organisation_entity_id")); row_entity=text(row.get("entity_id") or row.get("organisation_entity_id"))
    if entity and row_entity:return entity==row_entity
    names={norm(account.get("account_name")),norm(account.get("canonical_buyer")),norm(account.get("buyer"))}
    return bool(norm(account.get("account_name")) in names and norm(account.get("account_name"))==norm(row.get("canonical_buyer") or row.get("buyer") or row.get("account_name")) and country_matches(account,row.get("country")))

def buyer_row(account,rows):
    matches=[r for r in rows if account_row_matches(account,r)]
    return max(matches,key=lambda r:(num(r.get("buyer_demand_score") or r.get("faram_account_score")),integer(r.get("active_opportunities"))),default={})
def event_rows(account,rows):
    entity=text(account.get("organisation_entity_id")); name=norm(account.get("account_name")); out=[]
    for r in rows:
        same=(entity and entity==text(r.get("entity_id"))) or (name and name==norm(r.get("canonical_buyer") or r.get("buyer")))
        if same and country_matches(account,r.get("country")):out.append(r)
    seen=set(); unique=[]
    for r in out:
        key=text(r.get("procurement_event_id")) or "|".join([text(r.get("tender_reference")),text(r.get("title")),text(r.get("closing_date"))])
        if key not in seen:seen.add(key);unique.append(r)
    return unique

def opportunity_score(rows):
    active=sum(text(r.get("opportunity_status")).upper()=="ACTIVE_OPPORTUNITY" for r in rows)
    high=sum(text(r.get("procurement_priority")).upper()=="HIGH" for r in rows)
    upcoming=sum(text(r.get("opportunity_status")).upper() in {"UPCOMING_GPN","PROCUREMENT_PLAN"} for r in rows)
    value=sum(num(r.get("estimated_value")) for r in rows)
    score=min(40,active*20)+min(20,high*10)+min(15,upcoming*5)
    score+=15 if value>=1_000_000 else 11 if value>=250_000 else 7 if value>=50_000 else 3 if value>0 else 0
    return round(min(100,score),1),active,high,upcoming,value

def catalogue_fit(account,rows):
    matched=[r for r in rows if norm(r.get("buyer"))==norm(account.get("account_name")) and country_matches(account,r.get("country"))]
    actionable=[r for r in matched if text(r.get("match_status"))=="FARAM_MATCH"]
    review=[r for r in matched if text(r.get("match_status"))=="REQUIRES_TERRITORY_REVIEW"]
    products=sorted({text(r.get("faram_product_id")) for r in actionable if text(r.get("faram_product_id"))})
    event_ids=sorted({text(r.get("procurement_event_id")) for r in actionable if text(r.get("procurement_event_id"))})
    if actionable:return 100.0,"FARAM_MATCH",len(event_ids),products
    if review:return 60.0,"TERRITORY_REVIEW",len({text(r.get("procurement_event_id")) for r in review}),[]
    if matched:return 15.0,"NON_ACTIONABLE_MATCH",0,[]
    return 0.0,"NO_VERIFIED_CATALOGUE_MATCH",0,[]

def timing(rows,today):
    dates=[parsed_date(r.get("closing_date")) for r in rows if parsed_date(r.get("closing_date")) and text(r.get("opportunity_status")).upper() in {"ACTIVE_OPPORTUNITY","UPCOMING_GPN","PROCUREMENT_PLAN"}]
    dates=[d for d in dates if d]
    if not dates:return 0.0,""
    d=min(dates); days=(d-today).days
    score=100 if days<=14 else 90 if days<=30 else 70 if days<=60 else 50 if days<=90 else 30 if days<=180 else 10
    return float(max(0,score)),d.isoformat()

def tier(score):return "ACT_NOW" if score>=75 else "PRIORITISE" if score>=55 else "DEVELOP" if score>=35 else "MONITOR"
def action(tier_name,fit_status,active,familiarity):
    if tier_name=="ACT_NOW":return "Engage buyer immediately; qualify the active opportunity, confirm principal coverage and launch bid/no-bid review." if fit_status=="FARAM_MATCH" else "Engage immediately to resolve product/territory fit before committing tender resources."
    if tier_name=="PRIORITISE":
        if fit_status=="FARAM_MATCH" and active:return "Assign account owner; review active notices, compliance requirements and bid strategy."
        if familiarity>0:return "Develop account around familiar product families and verify current principal/territory coverage."
        return "Build account plan and validate the relevant procurement route and product coverage."
    if tier_name=="DEVELOP":return "Track procurement signals, strengthen product coverage and establish buyer/procurement relationships."
    return "Keep on watchlist; revisit when new procurement demand or catalogue-fit evidence appears."
def reason(demand,opportunity,fit,familiarity,timing_score,active,high):
    parts=[]
    if demand>=70:parts.append("strong buyer demand")
    elif demand>=45:parts.append("established buyer demand")
    if active:parts.append(f"{active} active opportunit{'y' if active==1 else 'ies'}")
    if high:parts.append(f"{high} high-priority signal{'s' if high!=1 else ''}")
    if fit>=100:parts.append("current Faram catalogue fit")
    elif fit>=60:parts.append("catalogue fit pending territory review")
    if familiarity>=60:parts.append("strong historical familiarity")
    elif familiarity>0:parts.append("historical familiarity")
    if timing_score>=90:parts.append("near-term closing")
    return "; ".join(parts) if parts else "No strong commercial signal yet."

def build_priority(accounts,buyers,events,matches,memory,today=None):
    today=today or date.today(); output=[]
    for account in accounts:
        b=buyer_row(account,buyers); ev=event_rows(account,events)
        demand=num(b.get("buyer_demand_score") or b.get("faram_account_score")); demand_tier=text(b.get("buyer_demand_tier") or b.get("faram_account_tier")) or "MONITOR"
        opp,active,high,upcoming,value=opportunity_score(ev); fit,fit_status,fit_events,products=catalogue_fit(account,matches)
        mem=next((r for r in memory if text(r.get("target_account_id"))==text(account.get("target_account_id"))),{})
        familiarity=min(100,num(mem.get("commercial_memory_score"))*10); familiarity_band=text(mem.get("commercial_memory_band")) or "NONE"
        tscore,closing=timing(ev,today)
        overall=round(.30*demand+.30*opp+.20*fit+.15*familiarity+.05*tscore,1); t=tier(overall)
        output.append({"target_account_id":text(account.get("target_account_id")),"account_name":text(account.get("account_name")),"organisation_entity_id":text(account.get("organisation_entity_id")),"country":text(account.get("country_names") or account.get("country_codes")),"account_type":text(account.get("account_type")),"crm_stage":text(account.get("crm_stage")),"buyer_demand_score":f"{demand:.1f}","buyer_demand_tier":demand_tier,"opportunity_score":f"{opp:.1f}","active_opportunities":str(active),"high_priority_opportunities":str(high),"upcoming_pipeline":str(upcoming),"estimated_opportunity_value":f"{value:.2f}","catalogue_fit_score":f"{fit:.1f}","catalogue_fit_status":fit_status,"catalogue_matched_events":str(fit_events),"catalogue_matched_products":"; ".join(products),"historical_familiarity_score":f"{familiarity:.1f}","historical_familiarity_band":familiarity_band,"historical_evidence_count":str(integer(mem.get("commercial_memory_evidence_count"))),"timing_score":f"{tscore:.1f}","next_closing_date":closing,"commercial_account_priority_score":f"{overall:.1f}","commercial_account_priority_tier":t,"priority_reason":reason(demand,opp,fit,familiarity,tscore,active,high),"recommended_action":action(t,fit_status,active,familiarity),"procurement_event_ids":"; ".join(text(r.get("procurement_event_id")) for r in ev if text(r.get("procurement_event_id"))),"familiarity_evidence_ids":text(mem.get("commercial_memory_evidence_ids"))})
    return sorted(output,key=lambda r:(-num(r["commercial_account_priority_score"]),norm(r["account_name"])))

def write_priority(output_path,accounts_path,buyer_path,events_path,matches_path,memory_path,today=None):
    rows=build_priority(load_csv(accounts_path),load_csv(buyer_path),load_csv(events_path),load_csv(matches_path),load_csv(memory_path),today=today)
    output_path.parent.mkdir(parents=True,exist_ok=True)
    with output_path.open("w",newline="",encoding="utf-8") as h:
        w=csv.DictWriter(h,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    return len(rows)

def main():
    p=argparse.ArgumentParser();p.add_argument("--accounts",default="data/target_accounts.csv");p.add_argument("--buyers",default="data/procurement_buyer_history.csv");p.add_argument("--events",default="data/procurement_events.csv");p.add_argument("--catalogue-matches",default="data/faram_product_matches.csv");p.add_argument("--memory",default="data/faram_account_commercial_memory.csv");p.add_argument("--output",default="data/commercial_account_priority.csv");a=p.parse_args()
    print(f"Commercial account priority completed: {write_priority(Path(a.output),Path(a.accounts),Path(a.buyers),Path(a.events),Path(a.catalogue_matches),Path(a.memory))} accounts")
if __name__=="__main__":main()
