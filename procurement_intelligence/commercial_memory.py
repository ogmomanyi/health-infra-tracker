"""Normalize historical Faram commercial evidence into a richer memory layer."""
from __future__ import annotations
import csv
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

MEMORY_FIELDS = ["memory_id","evidence_id","event_date","supplier_company","supplier_email","manufacturer_name","product_family","product_name","model","category","evidence_type","country","customer_or_project","outcome","evidence_strength","representation_signal","source_email_id","notes"]
_WEIGHTS = {"quotation_and_tender_support":4,"tender_fit_and_pricing":4,"order_and_business_review":5,"quotation":3,"quotation_inquiry":3,"tender_compliance_and_quotation":4,"quotation_and_technical_support":3,"tender_support":3,"tender_bid_support":3,"market_evaluation_and_pricing":2,"partnership_and_tender_support":2,"project_inquiry":2,"procurement_inquiry":2,"request_for_pricing":2,"quotation_and_partnership":3,"quotation_follow_up":3,"tender_or_product_pricing":3}
_EXPLICIT_OUTCOMES = {"order_and_business_review":"ORDERED","quotation":"QUOTED","quotation_inquiry":"INQUIRY","quotation_and_tender_support":"TENDER_SUPPORT","quotation_and_technical_support":"QUOTED","quotation_and_compliance":"QUOTED","tender_fit_and_pricing":"TENDER_SUPPORT","tender_compliance_and_quotation":"TENDER_SUPPORT","tender_support":"TENDER_SUPPORT","tender_bid_support":"TENDER_SUPPORT","partnership_and_tender_support":"TENDER_SUPPORT","tender_or_product_pricing":"QUOTED","request_for_pricing":"INQUIRY","quotation_follow_up":"QUOTED","quotation_and_partnership":"QUOTED"}

def _text(value: object) -> str: return " ".join(str(value or "").split())
def normalize(value: object) -> str: return re.sub(r"[^a-z0-9]+", " ", _text(value).lower().replace("&", " and ")).strip()

def _supplier_company(email: str) -> str:
    domain = _text(email).split("@",1)[-1].lower() if "@" in email else ""
    known = {"3dhistech.com":"3DHISTECH","midmark.com":"Midmark","shinva.com":"SHINVA","tharmac.de":"Tharmac","healthskybio.com":"HealthSky","pixcell.co":"PixCell","eschweiler-kiel.de":"ESCHWEILER","shengfengpack.com":"Shengfeng Pack","mflab.com":"MF Lab","recarecn.cn":"Recare","blu-med.com":"BLU-MED Response Systems","htds.fr":"HTDS","moldev.com":"Molecular Devices","memmert.com":"Memmert","silverlakeresearch.com":"Silver Lake Research","biopanda.co.uk":"BioPanda","thermofisher.com":"Thermo Fisher Scientific","ansell.com":"Ansell","yicaremedical.com":"YiCare Medical","inflammatix.com":"Inflammatix","medtecs.com":"Medtecs","honodmedical.com":"Honod Medical"}
    return known.get(domain, domain)

def _outcome(row): return _EXPLICIT_OUTCOMES.get(normalize(row.get("evidence_type")).replace(" ","_"), "NO_OUTCOME_RECORDED")
def _signal(row):
    if normalize(row.get("evidence_id")) == "hqe 005": return "EXTERNAL_ONLY"
    et, notes = normalize(row.get("evidence_type")), normalize(row.get("notes"))
    if et == "order and business review": return "TRANSACTIONAL"
    if "competitive reference" in notes or "not faram representation" in notes: return "COMPETITIVE_REFERENCE"
    if "external procurement" in notes: return "EXTERNAL_ONLY"
    if any(t in et for t in ("quotation","tender","rfq","request for pricing","procurement")): return "ACTIVE_COMMERCIAL"
    return "MARKET_EXPLORATION"
def _strength(weight): return "HIGH" if weight >= 5 else "MEDIUM" if weight >= 2 else "LOW"
def load_evidence(path: Path):
    if not path.exists(): return []
    with path.open(newline="",encoding="utf-8") as handle: return list(csv.DictReader(handle))
def normalize_evidence(rows: Iterable[dict[str,str]]):
    result=[]
    for index,row in enumerate(rows,1):
        evidence_id=_text(row.get("evidence_id"))
        if not evidence_id: continue
        weight=_WEIGHTS.get(normalize(row.get("evidence_type")).replace(" ","_"),1)
        result.append({"memory_id":f"FCM-{index:04d}","evidence_id":evidence_id,"event_date":_text(row.get("event_date")),"supplier_company":_supplier_company(_text(row.get("supplier_email"))),"supplier_email":_text(row.get("supplier_email")),"manufacturer_name":_text(row.get("manufacturer_name")),"product_family":_text(row.get("product_family")),"product_name":_text(row.get("product_name")),"model":_text(row.get("model")),"category":_text(row.get("category")),"evidence_type":_text(row.get("evidence_type")),"country":_text(row.get("country")),"customer_or_project":_text(row.get("customer_or_project")),"outcome":_outcome(row),"evidence_strength":_strength(weight),"representation_signal":_signal(row),"source_email_id":_text(row.get("source_email_id")),"notes":_text(row.get("notes"))})
    return result
def write_memory(path: Path, rows):
    normalized=normalize_evidence(rows); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=MEMORY_FIELDS); writer.writeheader(); writer.writerows(normalized)
    return len(normalized)
def build_summary(memory_rows, catalogue_rows=()):
    groups=defaultdict(list)
    for row in memory_rows:
        if _text(row.get("representation_signal")) in {"EXTERNAL_ONLY","COMPETITIVE_REFERENCE"}: continue
        groups[(_text(row.get("manufacturer_name")),_text(row.get("product_family")),_text(row.get("product_name")),_text(row.get("model")))].append(row)
    active_keys={(normalize(r.get("manufacturer_name")),normalize(r.get("product_family"))) for r in catalogue_rows if normalize(r.get("principal_status")) in {"active","current","yes","true"}}
    rank={"HIGH":3,"MEDIUM":2,"LOW":1}; summary=[]
    for (manufacturer,family,product,model),items in groups.items():
        suppliers={normalize(r.get("supplier_company")) for r in items if normalize(r.get("supplier_company"))}; dates=[]
        for r in items:
            v=_text(r.get("event_date"))
            if v:
                try: dates.append(datetime.fromisoformat(v.replace("Z","+00:00")))
                except ValueError: pass
        strongest=max(items,key=lambda r:rank.get(_text(r.get("evidence_strength")),0),default={})
        summary.append({"manufacturer_name":manufacturer,"product_family":family,"product_name":product,"model":model,"supplier_count":str(len(suppliers)),"evidence_count":str(len(items)),"latest_event_date":max(dates).date().isoformat() if dates else "","strongest_evidence":_text(strongest.get("evidence_type")),"commercial_familiarity_score":str(min(10,sum(rank.get(_text(r.get("evidence_strength")),1) for r in items))),"current_catalogue_status":"CATALOGUE_MATCH" if (normalize(manufacturer),normalize(family)) in active_keys else "NOT_FOUND"})
    return sorted(summary,key=lambda r:(-int(r["commercial_familiarity_score"]),r["manufacturer_name"].lower(),r["product_family"].lower()))
def write_summary(path: Path,memory_rows,catalogue_rows=()):
    fields=["manufacturer_name","product_family","product_name","model","supplier_count","evidence_count","latest_event_date","strongest_evidence","commercial_familiarity_score","current_catalogue_status"]; rows=build_summary(memory_rows,catalogue_rows); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return len(rows)
def main():
    import argparse
    p=argparse.ArgumentParser(); p.add_argument("--evidence",default="data/faram_historical_quote_evidence.csv"); p.add_argument("--catalogue",default="data/faram_product_catalogue.csv"); p.add_argument("--output",default="data/faram_commercial_memory.csv"); p.add_argument("--summary",default="data/faram_commercial_memory_summary.csv"); a=p.parse_args()
    evidence=load_evidence(Path(a.evidence)); catalogue=load_evidence(Path(a.catalogue)); count=write_memory(Path(a.output),evidence); memory=load_evidence(Path(a.output)); summary=write_summary(Path(a.summary),memory,catalogue); print(f"Faram commercial memory completed: {count} events; {summary} grouped records")
if __name__ == "__main__": main()
