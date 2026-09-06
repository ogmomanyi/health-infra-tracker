#!/usr/bin/env python3
"""Small stdlib-only HTTP server for the persistent commercial CRM state."""
from __future__ import annotations
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from procurement_intelligence import commercial_crm, commercial_work, account_work
ROOT = Path(__file__).resolve().parent
EXECUTION_HTML = ROOT / "procurement_intelligence" / "execution.html"
MY_WORK_HTML = ROOT / "procurement_intelligence" / "my_work.html"
ACCOUNT_HTML = ROOT / "procurement_intelligence" / "account.html"
class CRMHandler(BaseHTTPRequestHandler):
    db_path = commercial_crm.DB_DEFAULT
    def _json(self,status,payload):
        body=json.dumps(payload,default=str).encode("utf-8"); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers(); self.wfile.write(body)
    def _read_json(self):
        length=int(self.headers.get("Content-Length","0"));
        if length>1_000_000: raise ValueError("request body too large")
        data=json.loads((self.rfile.read(length) if length else b"{}").decode("utf-8"));
        if not isinstance(data,dict): raise ValueError("JSON body must be an object")
        return data
    def _actor(self,payload=None): return str((payload or {}).get("actor") or self.headers.get("X-CRM-Actor") or "local-user")
    def _route(self): return [p for p in urlparse(self.path).path.split("/") if p]
    def _serve(self,path):
        body=path.read_bytes(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_OPTIONS(self):
        self.send_response(204); self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Access-Control-Allow-Methods","GET, POST, PATCH, OPTIONS"); self.send_header("Access-Control-Allow-Headers","Content-Type, X-CRM-Actor"); self.end_headers()
    def do_GET(self):
        try:
            parts=self._route(); path=urlparse(self.path).path
            if path in {"/","/execution","/execution.html"}: return self._serve(EXECUTION_HTML)
            if path in {"/my-work","/my-work.html"}: return self._serve(MY_WORK_HTML)
            if path in {"/accounts","/accounts.html"}: return self._serve(ACCOUNT_HTML)
            if parts==["api","health"]: return self._json(200,{"ok":True})
            if parts==["api","work"]:
                p=parse_qs(urlparse(self.path).query); return self._json(200,commercial_work.list_work(db_path=self.db_path,owner=p.get("owner",[None])[0],today=p.get("today",[None])[0]))
            if parts==["api","accounts"]:
                p=parse_qs(urlparse(self.path).query); return self._json(200,{"accounts":account_work.list_accounts(db_path=self.db_path,today=p.get("today",[None])[0])})
            if parts==["api","opportunities"]:
                p=parse_qs(urlparse(self.path).query); return self._json(200,commercial_crm.list_opportunities(db_path=self.db_path,status=p.get("status",[None])[0],owner=p.get("owner",[None])[0]))
            if len(parts)==3 and parts[:2]==["api","opportunities"]:
                item=commercial_crm.get_opportunity(parts[2],db_path=self.db_path); return self._json(200,item) if item else self._json(404,{"error":"opportunity not found"})
            if len(parts)==4 and parts[:2]==["api","opportunities"] and parts[3] in {"activities","audit"}:
                oid=parts[2]
                if commercial_crm.get_opportunity(oid,db_path=self.db_path) is None: return self._json(404,{"error":"opportunity not found"})
                data=commercial_crm.list_activities(oid,db_path=self.db_path) if parts[3]=="activities" else commercial_crm.list_audit_log(oid,db_path=self.db_path); return self._json(200,data)
            return self._json(404,{"error":"not found"})
        except Exception as exc: return self._json(400,{"error":str(exc)})
    def do_PATCH(self):
        try:
            parts=self._route()
            if len(parts)!=3 or parts[:2]!=["api","opportunities"]: return self._json(404,{"error":"not found"})
            p=self._read_json(); item=commercial_crm.update_state(parts[2],db_path=self.db_path,actor=self._actor(p),status=p.get("status"),assigned_owner=p.get("assigned_owner"),next_activity=p.get("next_activity"),next_activity_due_date=p.get("next_activity_due_date"),notes=p.get("notes")); return self._json(200,item)
        except KeyError as exc: return self._json(404,{"error":str(exc)})
        except (ValueError,TypeError,json.JSONDecodeError) as exc: return self._json(400,{"error":str(exc)})
        except Exception as exc: return self._json(500,{"error":str(exc)})
    def do_POST(self):
        try:
            parts=self._route()
            if len(parts)!=4 or parts[:2]!=["api","opportunities"] or parts[3]!="activities": return self._json(404,{"error":"not found"})
            p=self._read_json(); aid=commercial_crm.add_activity(parts[2],db_path=self.db_path,actor=self._actor(p),activity_type=p.get("activity_type","NOTE"),subject=p.get("subject",""),notes=p.get("notes",""),activity_date=p.get("activity_date"),due_date=p.get("due_date"),owner=p.get("owner")); return self._json(201,{"activity_id":aid})
        except KeyError as exc: return self._json(404,{"error":str(exc)})
        except (ValueError,TypeError,json.JSONDecodeError) as exc: return self._json(400,{"error":str(exc)})
        except Exception as exc: return self._json(500,{"error":str(exc)})
    def log_message(self,fmt,*args): return
def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--host",default="127.0.0.1"); parser.add_argument("--port",type=int,default=8765); parser.add_argument("--db",default=str(commercial_crm.DB_DEFAULT)); args=parser.parse_args(); commercial_crm.initialize(args.db); CRMHandler.db_path=args.db; server=ThreadingHTTPServer((args.host,args.port),CRMHandler); print(f"Commercial CRM API listening on http://{args.host}:{args.port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__=="__main__": main()
