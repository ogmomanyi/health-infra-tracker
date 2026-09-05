#!/usr/bin/env python3
"""Small stdlib-only HTTP server for the persistent commercial CRM state."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from procurement_intelligence import commercial_crm


class CRMHandler(BaseHTTPRequestHandler):
    db_path = commercial_crm.DB_DEFAULT

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _actor(self, payload: dict | None = None) -> str:
        return str((payload or {}).get("actor") or self.headers.get("X-CRM-Actor") or "local-user")

    def _route(self):
        return [part for part in urlparse(self.path).path.split("/") if part]

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CRM-Actor")
        self.end_headers()

    def do_GET(self):
        try:
            parts = self._route()
            if parts == ["api", "health"]:
                return self._json(200, {"ok": True})
            if parts == ["api", "opportunities"]:
                params = parse_qs(urlparse(self.path).query)
                status = params.get("status", [None])[0]
                owner = params.get("owner", [None])[0]
                return self._json(200, commercial_crm.list_opportunities(db_path=self.db_path, status=status, owner=owner))
            if len(parts) == 3 and parts[:2] == ["api", "opportunities"]:
                item = commercial_crm.get_opportunity(parts[2], db_path=self.db_path)
                if item is None:
                    return self._json(404, {"error": "opportunity not found"})
                return self._json(200, item)
            if len(parts) == 4 and parts[:2] == ["api", "opportunities"] and parts[3] in {"activities", "audit"}:
                opportunity_id = parts[2]
                if commercial_crm.get_opportunity(opportunity_id, db_path=self.db_path) is None:
                    return self._json(404, {"error": "opportunity not found"})
                if parts[3] == "activities":
                    return self._json(200, commercial_crm.list_activities(opportunity_id, db_path=self.db_path))
                return self._json(200, commercial_crm.list_audit_log(opportunity_id, db_path=self.db_path))
            return self._json(404, {"error": "not found"})
        except Exception as exc:
            return self._json(400, {"error": str(exc)})

    def do_PATCH(self):
        try:
            parts = self._route()
            if len(parts) != 3 or parts[:2] != ["api", "opportunities"]:
                return self._json(404, {"error": "not found"})
            payload = self._read_json()
            item = commercial_crm.update_state(
                parts[2], db_path=self.db_path, actor=self._actor(payload),
                status=payload.get("status"), assigned_owner=payload.get("assigned_owner"),
                next_activity=payload.get("next_activity"),
                next_activity_due_date=payload.get("next_activity_due_date"),
                notes=payload.get("notes"),
            )
            return self._json(200, item)
        except KeyError as exc:
            return self._json(404, {"error": str(exc)})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self._json(400, {"error": str(exc)})
        except Exception as exc:
            return self._json(500, {"error": str(exc)})

    def do_POST(self):
        try:
            parts = self._route()
            if len(parts) != 4 or parts[:2] != ["api", "opportunities"] or parts[3] != "activities":
                return self._json(404, {"error": "not found"})
            payload = self._read_json()
            activity_id = commercial_crm.add_activity(
                parts[2], db_path=self.db_path, actor=self._actor(payload),
                activity_type=payload.get("activity_type", "NOTE"),
                subject=payload.get("subject", ""), notes=payload.get("notes", ""),
                activity_date=payload.get("activity_date"), due_date=payload.get("due_date"),
                owner=payload.get("owner"),
            )
            return self._json(201, {"activity_id": activity_id})
        except KeyError as exc:
            return self._json(404, {"error": str(exc)})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self._json(400, {"error": str(exc)})
        except Exception as exc:
            return self._json(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=str(commercial_crm.DB_DEFAULT))
    args = parser.parse_args()
    commercial_crm.initialize(args.db)
    CRMHandler.db_path = args.db
    server = ThreadingHTTPServer((args.host, args.port), CRMHandler)
    print(f"Commercial CRM API listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
