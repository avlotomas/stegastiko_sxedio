#!/usr/bin/env python3
"""Local working prototype for the Nicosia housing-plots workflow.

Uses the Python standard library and SQLite. Binds to loopback only. This is a
reviewable internal prototype, not a public service or a production PII store.
"""

import base64
import csv
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DB = Path(os.getenv("HOUSING_DB", str(ROOT / "data" / "housing.sqlite3"))).resolve()
UPLOADS = DB.parent / "uploads"
TZ = ZoneInfo("Asia/Nicosia")
MAX_BODY = 28 * 1024 * 1024  # Base64 encoding expands an allowed 20 MiB file.
FLOWS = {"legacy": "Αδιάθετα παλαιού διαχωρισμού", "new": "Νέο αίτημα διαχωρισμού"}
LOT_STATUSES = {"available", "reserved", "awarded", "withdrawn"}
CRITERIA = ["citizenship", "age", "residence", "property", "alienation", "income", "previous_aid"]
CRITERIA_NAMES = {
    "citizenship": "10.4.1 Κυπριακή υπηκοότητα",
    "age": "10.4.2 Ηλικία",
    "residence": "10.4.3 Διαμονή",
    "property": "10.4.4 Άλλη ακίνητη ιδιοκτησία",
    "alienation": "10.4.5 Αποξένωση",
    "income": "10.4.6 Εισόδημα",
    "previous_aid": "10.4.7 Προηγούμενη κρατική στεγαστική ενίσχυση",
}
CASE_SECTIONS = {"1", "2", "3", "4", "5", "6", "7", *(f"8.{i}" for i in range(1, 9))}
APPLICATION_SECTIONS = {"10.1", "10.2.2", "10.3.1", "10.3.2", "10.3.3", "10.3.4", "10.3.5", "10.4.6", "10.4", "10.5", "10.6", "10.7", "10.8", "10.9", "10.10", "10.11", "10.12"}


def now():
    return datetime.now(TZ).isoformat(timespec="seconds")


def today():
    return datetime.now(TZ).date().isoformat()


def obj(value):
    try:
        return json.loads(value or "{}")
    except (ValueError, TypeError):
        return {}


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def money(value):
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise Problem(400, "Η αξία πρέπει να είναι αριθμός.") from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
        raise Problem(400, "Η αξία πρέπει να είναι μη αρνητική και εύλογη.")
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def as_lot(row):
    lot = dict(row)
    value = (lot.get("valuation_value") if lot.get("title_status") == "Δεν υπάρχει τίτλος"
             else lot.get("general_value") or lot.get("valuation_value"))
    lot["disposal_price"] = money(Decimal(value) * Decimal("0.25")) if value else None
    return lot


def summary(value):
    result = {}
    for criterion in CRITERIA:
        data = value.get(criterion, {})
        if isinstance(data, str):
            state = data
        elif isinstance(data, dict):
            state = data.get("result", "ΕΚΚΡΕΜΕΙ")
        else:
            state = "ΕΚΚΡΕΜΕΙ"
        result[criterion] = state if state in ("ΠΛΗΡΟΥΤΑΙ", "ΔΕΝ ΠΛΗΡΟΥΤΑΙ") else "ΕΚΚΡΕΜΕΙ"
    if "ΔΕΝ ΠΛΗΡΟΥΤΑΙ" in result.values():
        outcome = "Κατ’ αρχήν δεν πληροί"
    elif all(state == "ΠΛΗΡΟΥΤΑΙ" for state in result.values()):
        outcome = "Κατ’ αρχήν πληροί"
    else:
        outcome = "Εκκρεμεί"
    return {"criteria": result, "preliminary": outcome, "failed": [CRITERIA_NAMES[k] for k,v in result.items() if v == "ΔΕΝ ΠΛΗΡΟΥΤΑΙ"]}


class Problem(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


@contextmanager
def connection():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_db():
    with connection() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS areas (
          id INTEGER PRIMARY KEY, province TEXT NOT NULL, kind TEXT NOT NULL,
          municipality TEXT NOT NULL, name TEXT NOT NULL, source_row INTEGER NOT NULL,
          source_col INTEGER NOT NULL, UNIQUE(province,kind,name)
        );
        CREATE TABLE IF NOT EXISTS cases (
          id INTEGER PRIMARY KEY, case_no TEXT UNIQUE, area_id INTEGER NOT NULL REFERENCES areas(id),
          flow TEXT NOT NULL CHECK(flow IN ('legacy','new')),
          received_at TEXT, email TEXT NOT NULL DEFAULT '', council_ref TEXT NOT NULL DEFAULT '',
          state TEXT NOT NULL DEFAULT 'Σε εξέλιξη', notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS cases_area ON cases(area_id);
        CREATE TABLE IF NOT EXISTS sections (
          entity TEXT NOT NULL CHECK(entity IN ('case','application')),
          entity_id INTEGER NOT NULL, code TEXT NOT NULL, data TEXT NOT NULL,
          updated_at TEXT NOT NULL, PRIMARY KEY(entity,entity_id,code)
        );
        CREATE TABLE IF NOT EXISTS section_history (
          id INTEGER PRIMARY KEY, entity TEXT NOT NULL, entity_id INTEGER NOT NULL,
          code TEXT NOT NULL, previous_data TEXT, new_data TEXT NOT NULL,
          changed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lots (
          id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id),
          lot_no TEXT NOT NULL, sheet_plan TEXT NOT NULL DEFAULT '',
          registration_no TEXT NOT NULL DEFAULT '', title_no TEXT NOT NULL DEFAULT '',
          title_status TEXT NOT NULL DEFAULT 'Εκκρεμεί', area_sqm TEXT NOT NULL DEFAULT '',
          general_value TEXT, valuation_value TEXT, valuation_date TEXT,
          valuation_ref TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'available', notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(case_id,lot_no)
        );
        CREATE INDEX IF NOT EXISTS lots_case ON lots(case_id);
        CREATE TABLE IF NOT EXISTS notices (
          id INTEGER PRIMARY KEY, notice_no TEXT UNIQUE, publication_date TEXT,
          start_date TEXT, deadline TEXT, submission_address TEXT NOT NULL DEFAULT '',
          contact TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'Προσχέδιο',
          notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notice_lots (
          notice_id INTEGER NOT NULL REFERENCES notices(id),
          lot_id INTEGER NOT NULL REFERENCES lots(id),
          PRIMARY KEY(notice_id,lot_id)
        );
        CREATE TABLE IF NOT EXISTS people (
          id INTEGER PRIMARY KEY, identity_no TEXT UNIQUE NOT NULL,
          full_name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS applications (
          id INTEGER PRIMARY KEY, application_no TEXT UNIQUE,
          notice_id INTEGER NOT NULL REFERENCES notices(id),
          area_id INTEGER NOT NULL REFERENCES areas(id),
          person_id INTEGER NOT NULL REFERENCES people(id),
          received_at TEXT NOT NULL, protocol_no TEXT NOT NULL DEFAULT '',
          family_type TEXT NOT NULL DEFAULT '', preference INTEGER,
          state TEXT NOT NULL DEFAULT 'Καταχωρισμένη',
          committee_decision TEXT NOT NULL DEFAULT 'Εκκρεμεί', rank_no INTEGER,
          allocated_lot_id INTEGER UNIQUE REFERENCES lots(id),
          data TEXT NOT NULL DEFAULT '{}', criteria TEXT NOT NULL DEFAULT '{}',
          notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS apps_notice_area ON applications(notice_id,area_id);
        CREATE INDEX IF NOT EXISTS apps_person ON applications(person_id);
        CREATE TABLE IF NOT EXISTS files (
          id INTEGER PRIMARY KEY, entity TEXT NOT NULL, entity_id INTEGER NOT NULL,
          original_name TEXT NOT NULL, mime TEXT NOT NULL, stored_name TEXT NOT NULL,
          sha256 TEXT NOT NULL, size INTEGER NOT NULL, label TEXT NOT NULL DEFAULT '',
          uploaded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY, entity TEXT NOT NULL, entity_id INTEGER NOT NULL,
          action TEXT NOT NULL, detail TEXT NOT NULL, actor TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        """)
        if not c.execute("SELECT 1 FROM areas LIMIT 1").fetchone():
            with (ROOT / "data" / "areas.csv").open(encoding="utf-8-sig", newline="") as f:
                for area in csv.DictReader(f):
                    if area["επαρχία"] != "ΛΕΥΚΩΣΙΑΣ":
                        continue
                    c.execute("INSERT INTO areas(province,kind,municipality,name,source_row,source_col) VALUES(?,?,?,?,?,?)",
                              (area["επαρχία"],area["τύπος"],area["δήμος"],area["περιοχή_όπως_στο_παράρτημα"],area["γραμμή_πηγής"],area["στήλη_πηγής"]))


def required(record, key, label):
    value = record.get(key)
    if value is None or str(value).strip() == "":
        raise Problem(400, f"Απαιτείται: {label}.")
    return value


def get(c, table, identifier):
    if table not in ("cases", "lots", "notices", "applications", "files"):
        raise Problem(400, "Μη έγκυρη αναφορά.")
    row = c.execute(f"SELECT * FROM {table} WHERE id=?", (identifier,)).fetchone()
    if not row:
        raise Problem(404, "Η εγγραφή δεν βρέθηκε.")
    return dict(row)


def area(c, identifier):
    row = c.execute("SELECT * FROM areas WHERE id=?", (identifier,)).fetchone()
    if not row:
        raise Problem(400, "Επιλέξτε κοινότητα από τον κατάλογο Λευκωσίας.")
    return dict(row)


def audit(c, entity, identifier, action, detail, actor="Εσωτερικός χρήστης (τοπική επίδειξη)"):
    c.execute("INSERT INTO audit(entity,entity_id,action,detail,actor,created_at) VALUES(?,?,?,?,?,?)",
              (entity,identifier,action,detail,actor,now()))


def changes(old, fields):
    return "; ".join(f"{key}: {old.get(key) or '—'} → {value or '—'}" for key,value in fields.items() if old.get(key)!=value)


def case_list(c):
    return [dict(r) for r in c.execute("""
      SELECT x.*, a.name area_name,a.kind area_kind,a.municipality,
      (SELECT COUNT(*) FROM lots l WHERE l.case_id=x.id) lot_count
      FROM cases x JOIN areas a ON a.id=x.area_id ORDER BY x.id DESC""")]


def lot_list(c):
    return [as_lot(r) for r in c.execute("""
      SELECT l.*, x.area_id,x.case_no,x.flow,a.name area_name
      FROM lots l JOIN cases x ON x.id=l.case_id JOIN areas a ON a.id=x.area_id
      ORDER BY l.id DESC""")]


def notice_offers(c, identifier):
    return [as_lot(r) for r in c.execute("""
      SELECT l.*, x.area_id,x.case_no,x.flow,a.name area_name
      FROM notice_lots nl JOIN lots l ON l.id=nl.lot_id JOIN cases x ON x.id=l.case_id
      JOIN areas a ON a.id=x.area_id WHERE nl.notice_id=? ORDER BY a.name,l.id""", (identifier,))]


def notice_list(c):
    rows = [dict(r) for r in c.execute("SELECT * FROM notices ORDER BY id DESC")]
    for r in rows:
        r["offers"] = notice_offers(c,r["id"])
        r["lot_count"] = len(r["offers"])
        r["area_count"] = len({x["area_id"] for x in r["offers"]})
    return rows


def application_list(c):
    return [dict(r) for r in c.execute("""
      SELECT ap.id,ap.application_no,ap.notice_id,ap.area_id,ap.person_id,
      ap.received_at,ap.family_type,ap.preference,ap.state,ap.committee_decision,
      ap.allocated_lot_id,p.full_name,p.identity_no,a.name area_name,n.notice_no
      FROM applications ap JOIN people p ON p.id=ap.person_id
      JOIN areas a ON a.id=ap.area_id JOIN notices n ON n.id=ap.notice_id
      ORDER BY ap.id DESC""")]


def json_section(c, entity, identifier, code):
    row = c.execute("SELECT data FROM sections WHERE entity=? AND entity_id=? AND code=?", (entity,identifier,code)).fetchone()
    return obj(row[0]) if row else {}


def section_map(c, entity, identifier):
    return {r["code"]:obj(r["data"]) for r in c.execute("SELECT code,data FROM sections WHERE entity=? AND entity_id=?", (entity,identifier))}


def file_list(c, entity, identifier):
    return [dict(r) for r in c.execute("SELECT id,original_name,mime,sha256,size,label,uploaded_at FROM files WHERE entity=? AND entity_id=? ORDER BY id DESC",(entity,identifier))]


def api_get(c, pieces, query):
    if pieces == ["health"]:
        return {"ok":True,"area_count":c.execute("SELECT COUNT(*) FROM areas").fetchone()[0]}
    if pieces == ["bootstrap"]:
        return {"areas":[dict(r) for r in c.execute("SELECT * FROM areas ORDER BY name")],
                "cases":case_list(c),"lots":lot_list(c),"notices":notice_list(c),
                "applications":application_list(c),"criteria_names":CRITERIA_NAMES}
    if pieces == ["cases"]: return case_list(c)
    if pieces == ["lots"]: return lot_list(c)
    if pieces == ["notices"]: return notice_list(c)
    if pieces == ["applications"]: return application_list(c)
    if len(pieces)==2 and pieces[0]=="cases":
        item=get(c,"cases",int(pieces[1]))
        item["area"]=area(c,item["area_id"])
        item["sections"]=section_map(c,"case",item["id"])
        item["lots"]=[x for x in lot_list(c) if x["case_id"]==item["id"]]
        item["files"]=file_list(c,"case",item["id"])
        return item
    if len(pieces)==2 and pieces[0]=="notices":
        item=get(c,"notices",int(pieces[1]))
        item["offers"]=notice_offers(c,item["id"])
        item["files"]=file_list(c,"notice",item["id"])
        return item
    if len(pieces)==2 and pieces[0]=="applications":
        item=get(c,"applications",int(pieces[1]))
        item["area"]=area(c,item["area_id"])
        item["person"]=dict(c.execute("SELECT * FROM people WHERE id=?",(item["person_id"],)).fetchone())
        item["data"]=obj(item["data"])
        item["criteria"]=obj(item["criteria"])
        item["criteria_summary"]=summary(item["criteria"])
        item["sections"]=section_map(c,"application",item["id"])
        item["files"]=file_list(c,"application",item["id"])
        item["related"]=[x for x in application_list(c) if x["person_id"]==item["person_id"] and x["id"]!=item["id"]]
        return item
    if pieces == ["audit"]:
        entity=query.get("entity",[""])[0]
        identifier=query.get("id",[""])[0]
        if entity not in ("case","application","notice") or not identifier.isdigit():
            raise Problem(400,"Επιλέξτε έγκυρη υπόθεση, αίτηση ή γνωστοποίηση.")
        return [dict(x) for x in c.execute("SELECT * FROM audit WHERE entity=? AND entity_id=? ORDER BY id DESC",(entity,identifier))]
    if pieces == ["history"]:
        entity=query.get("entity",[""])[0]
        identifier=query.get("id",[""])[0]
        if entity not in ("case","application") or not identifier.isdigit():
            raise Problem(400,"Μη έγκυρη αναφορά ιστορικού.")
        return [{**dict(r),"previous_data":obj(r["previous_data"]) if r["previous_data"] else None,
                 "new_data":obj(r["new_data"])} for r in c.execute(
                "SELECT * FROM section_history WHERE entity=? AND entity_id=? ORDER BY id DESC",(entity,identifier))]
    raise Problem(404,"Άγνωστη διεύθυνση.")


def api_post(c, pieces, value):
    if not isinstance(value,dict): raise Problem(400,"Τα δεδομένα πρέπει να είναι αντικείμενο.")
    stamp=now()
    if pieces == ["cases"]:
        area_id=int(required(value,"area_id","Κοινότητα")); area(c,area_id)
        flow=required(value,"flow","Τύπος ροής")
        if flow not in FLOWS: raise Problem(400,"Μη έγκυρος τύπος ροής.")
        cur=c.execute("INSERT INTO cases(area_id,flow,received_at,email,council_ref,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                      (area_id,flow,value.get("received_at"),str(value.get("email","")).strip(),
                       str(value.get("council_ref","")).strip() if flow=="new" else "",str(value.get("notes","")).strip(),stamp,stamp))
        identifier=cur.lastrowid
        code=f"ΛΕΥ-{datetime.now(TZ):%Y}-{identifier:06d}"
        c.execute("UPDATE cases SET case_no=? WHERE id=?",(code,identifier))
        audit(c,"case",identifier,"Δημιουργία",FLOWS[flow])
        return {"id":identifier,"case_no":code}
    if pieces == ["lots"]:
        case_id=int(required(value,"case_id","Υπόθεση")); case=get(c,"cases",case_id)
        lot_no=str(required(value,"lot_no","Αριθμός οικοπέδου")).strip()
        if case["flow"]=="new" and not lot_no:
            raise Problem(400,"Απαιτείται τελικός αριθμός οικοπέδου.")
        vals=[case_id,lot_no,str(value.get("sheet_plan","")).strip(),str(value.get("registration_no","")).strip(),
              str(value.get("title_no","")).strip(),str(value.get("title_status","Εκκρεμεί")),
              str(value.get("area_sqm","")).strip(),money(value.get("general_value")),money(value.get("valuation_value")),
              value.get("valuation_date"),str(value.get("valuation_ref","")).strip(),str(value.get("location","")).strip(),
              str(value.get("notes","")).strip(),stamp,stamp]
        try:
            cur=c.execute("""INSERT INTO lots(case_id,lot_no,sheet_plan,registration_no,title_no,title_status,area_sqm,
              general_value,valuation_value,valuation_date,valuation_ref,location,notes,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",vals)
        except sqlite3.IntegrityError as exc:
            raise Problem(409,"Ο αριθμός οικοπέδου υπάρχει ήδη σε αυτή την υπόθεση.") from exc
        audit(c,"case",case_id,"Προσθήκη οικοπέδου",lot_no)
        return as_lot(get(c,"lots",cur.lastrowid))
    if pieces == ["notices"]:
        ids=value.get("lot_ids") or []
        if not isinstance(ids,list) or not ids: raise Problem(400,"Επιλέξτε τουλάχιστον ένα διαθέσιμο οικόπεδο.")
        ids=list(dict.fromkeys(int(x) for x in ids))
        for identifier in ids:
            lot=get(c,"lots",identifier)
            if lot["status"]!="available": raise Problem(409,"Επιλέχθηκε οικόπεδο που δεν είναι διαθέσιμο.")
        cur=c.execute("""INSERT INTO notices(publication_date,start_date,deadline,submission_address,contact,notes,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?)""",
              (value.get("publication_date"),value.get("start_date"),value.get("deadline"),
               str(value.get("submission_address","")).strip(),str(value.get("contact","")).strip(),
               str(value.get("notes","")).strip(),stamp,stamp))
        identifier=cur.lastrowid
        code=f"ΓΝ-ΛΕΥ-{datetime.now(TZ):%Y}-{identifier:05d}"
        c.execute("UPDATE notices SET notice_no=? WHERE id=?",(code,identifier))
        c.executemany("INSERT INTO notice_lots(notice_id,lot_id) VALUES(?,?)",[(identifier,x) for x in ids])
        audit(c,"notice",identifier,"Δημιουργία",f"{len(ids)} οικόπεδα από μία ή περισσότερες υποθέσεις")
        return {"id":identifier,"notice_no":code}
    if len(pieces)==3 and pieces[0]=="notices" and pieces[2]=="publish":
        identifier=int(pieces[1]); notice=get(c,"notices",identifier)
        if notice["state"]!="Προσχέδιο": raise Problem(409,"Η γνωστοποίηση έχει ήδη δημοσιευθεί.")
        for k in ("publication_date","start_date","deadline"):
            if not notice[k]: raise Problem(400,"Συμπληρώστε ημερομηνία δημοσίευσης, έναρξης και λήξης.")
        if not (notice["publication_date"]<=notice["start_date"]<=notice["deadline"]):
            raise Problem(400,"Οι ημερομηνίες της γνωστοποίησης δεν είναι σε σωστή σειρά.")
        lots=notice_offers(c,identifier)
        if not lots: raise Problem(400,"Η γνωστοποίηση δεν περιλαμβάνει οικόπεδα.")
        for lot in lots:
            active=c.execute("""SELECT n.notice_no FROM notice_lots nl JOIN notices n ON n.id=nl.notice_id
              WHERE nl.lot_id=? AND n.state='Δημοσιευμένη' AND n.id<>? LIMIT 1""",(lot["id"],identifier)).fetchone()
            if active: raise Problem(409,f"Το οικόπεδο {lot['lot_no']} περιλαμβάνεται ήδη στη {active[0]}.")
            if lot["status"]!="available": raise Problem(409,f"Το οικόπεδο {lot['lot_no']} δεν είναι διαθέσιμο.")
            if lot["disposal_price"] is None:
                raise Problem(400,f"Καταχωρίστε αξία ανά οικόπεδο πριν από τη δημοσίευση: {lot['lot_no']}.")
            if lot["title_status"]=="Δεν υπάρχει τίτλος" and not lot["valuation_ref"]:
                raise Problem(400,f"Καταχωρίστε τη χωριστή απάντηση ΤΚΧ για το οικόπεδο {lot['lot_no']}.")
        c.execute("UPDATE notices SET state='Δημοσιευμένη',updated_at=? WHERE id=?",(stamp,identifier))
        audit(c,"notice",identifier,"Δημοσίευση",f"Οριστικοποιήθηκαν {len(lots)} οικόπεδα")
        return {"id":identifier,"state":"Δημοσιευμένη"}
    if pieces == ["applications"]:
        notice_id=int(required(value,"notice_id","Γνωστοποίηση"));notice=get(c,"notices",notice_id)
        if notice["state"]!="Δημοσιευμένη": raise Problem(400,"Η γνωστοποίηση πρέπει να δημοσιευθεί πρώτα.")
        area_id=int(required(value,"area_id","Κοινότητα")); area(c,area_id)
        if area_id not in {x["area_id"] for x in notice_offers(c,notice_id)}:
            raise Problem(400,"Η κοινότητα δεν περιλαμβάνεται στη συγκεκριμένη γνωστοποίηση.")
        identity=str(required(value,"identity_no","Αριθμός ταυτότητας")).strip().upper()
        name=str(required(value,"full_name","Ονοματεπώνυμο")).strip()
        if len(identity)>60 or len(name)>180:raise Problem(400,"Πολύ μεγάλα στοιχεία ταυτότητας.")
        existing=c.execute("SELECT * FROM people WHERE identity_no=?",(identity,)).fetchone()
        if existing:
            person_id=existing["id"]
            if existing["full_name"]!=name:
                raise Problem(409,"Η ταυτότητα ανήκει ήδη σε άλλο ονοματεπώνυμο. Ελέγξτε την καταχώριση.")
        else:
            person_id=c.execute("INSERT INTO people(identity_no,full_name,created_at,updated_at) VALUES(?,?,?,?)",(identity,name,stamp,stamp)).lastrowid
        if c.execute("SELECT 1 FROM applications WHERE notice_id=? AND area_id=? AND person_id=?",
                     (notice_id,area_id,person_id)).fetchone():
            raise Problem(409,"Υπάρχει ήδη αίτηση του ίδιου προσώπου για αυτή την κοινότητα και γνωστοποίηση.")
        received=str(value.get("received_at") or today())
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",received): raise Problem(400,"Μη έγκυρη ημερομηνία παραλαβής.")
        state="Εκπρόθεσμη" if notice["start_date"] and notice["deadline"] and not (notice["start_date"]<=received<=notice["deadline"]) else "Καταχωρισμένη"
        preference=value.get("preference")
        if preference not in (None,""):
            preference=int(preference)
            if preference<1 or preference>20:raise Problem(400,"Η σειρά προτίμησης πρέπει να είναι θετικός αριθμός.")
        else:preference=None
        cur=c.execute("""INSERT INTO applications(notice_id,area_id,person_id,received_at,protocol_no,family_type,preference,
          state,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
          (notice_id,area_id,person_id,received,str(value.get("protocol_no","")).strip(),
           str(value.get("family_type","")).strip(),preference,state,str(value.get("notes","")).strip(),stamp,stamp))
        identifier=cur.lastrowid
        code=f"ΑΙ-ΛΕΥ-{datetime.now(TZ):%Y}-{identifier:06d}"
        c.execute("UPDATE applications SET application_no=? WHERE id=?",(code,identifier))
        audit(c,"application",identifier,"Παραλαβή",f"{name} · {area(c,area_id)['name']} · {state}")
        return {"id":identifier,"application_no":code,"state":state}
    if len(pieces)==4 and pieces[0] in ("cases","applications") and pieces[2]=="sections":
        entity="case" if pieces[0]=="cases" else "application"
        identifier=int(pieces[1]);get(c,pieces[0],identifier)
        code=pieces[3]
        if not re.fullmatch(r"(?:[1-9]|10)(?:\.[0-9]+){0,2}",code):raise Problem(400,"Μη έγκυρη αρίθμηση ενότητας.")
        if (entity=="case" and code not in CASE_SECTIONS) or (entity=="application" and code not in APPLICATION_SECTIONS):
            raise Problem(400,"Η ενότητα ανήκει σε άλλο τύπο εγγραφής.")
        if entity=="case" and get(c,"cases",identifier)["flow"]=="legacy" and code not in ("8.8",):
            raise Problem(400,"Για παλαιά αδιάθετα εφαρμόζεται η 8.8 πριν από τη γνωστοποίηση.")
        data=value
        if entity=="application" and code=="10.4":
            data={"criteria":value,"summary":summary(value)}
            c.execute("UPDATE applications SET criteria=?,updated_at=? WHERE id=?",(dump(value),stamp,identifier))
        old=c.execute("SELECT data FROM sections WHERE entity=? AND entity_id=? AND code=?",(entity,identifier,code)).fetchone()
        c.execute("INSERT INTO section_history(entity,entity_id,code,previous_data,new_data,changed_at) VALUES(?,?,?,?,?,?)",
                  (entity,identifier,code,old[0] if old else None,dump(data),stamp))
        c.execute("""INSERT INTO sections(entity,entity_id,code,data,updated_at) VALUES(?,?,?,?,?)
          ON CONFLICT(entity,entity_id,code) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at""",
          (entity,identifier,code,dump(data),stamp))
        old_status=obj(old[0]).get("status") if old else None
        transition=f" · κατάσταση {old_status or '—'} → {data['status']}" if isinstance(data,dict) and data.get("status")!=old_status and data.get("status") else ""
        audit(c,entity,identifier,"Ενημέρωση ενότητας",code+transition)
        return {"saved":True,"updated_at":stamp,"summary":summary(value) if code=="10.4" else None}
    if len(pieces)==3 and pieces[0]=="applications" and pieces[2]=="allocate":
        identifier=int(pieces[1]); app=get(c,"applications",identifier)
        if app["allocated_lot_id"] is not None:raise Problem(409,"Η αίτηση έχει ήδη κατανομή οικοπέδου.")
        if app["committee_decision"]!="Εγκρίνεται":raise Problem(409,"Απαιτείται καταχωρισμένη έγκριση Επιτροπής.")
        lot_id=int(required(value,"lot_id","Οικόπεδο"));lot=get(c,"lots",lot_id)
        offer=c.execute("""SELECT 1 FROM notice_lots nl JOIN lots l ON l.id=nl.lot_id
          JOIN cases x ON x.id=l.case_id WHERE nl.notice_id=? AND nl.lot_id=? AND x.area_id=?""",
          (app["notice_id"],lot_id,app["area_id"])).fetchone()
        if not offer or lot["status"]!="available":raise Problem(409,"Το οικόπεδο δεν είναι διαθέσιμο για αυτή την αίτηση.")
        other=c.execute("""SELECT ap.application_no FROM applications ap WHERE ap.person_id=? AND ap.allocated_lot_id IS NOT NULL AND ap.id<>?""",
                        (app["person_id"],identifier)).fetchone()
        if other:raise Problem(409,f"Το ίδιο πρόσωπο έχει ήδη κατανομή στην {other[0]}.")
        c.execute("UPDATE applications SET allocated_lot_id=?,updated_at=? WHERE id=?",(lot_id,stamp,identifier))
        c.execute("UPDATE lots SET status='awarded',updated_at=? WHERE id=?",(stamp,lot_id))
        audit(c,"application",identifier,"Κατανομή",f"Οικόπεδο {lot['lot_no']} · υπόθεση {lot['case_id']}")
        return {"allocated":True,"lot_id":lot_id}
    if pieces == ["files"]:
        entity=required(value,"entity","Τύπος φακέλου")
        if entity not in ("case","notice","application"):raise Problem(400,"Μη έγκυρος τύπος εγγράφου.")
        identifier=int(required(value,"entity_id","Αριθμός φακέλου"))
        get(c,{"case":"cases","notice":"notices","application":"applications"}[entity],identifier)
        name=Path(str(required(value,"name","Όνομα αρχείου"))).name
        if not name or len(name)>200:raise Problem(400,"Μη έγκυρο όνομα αρχείου.")
        try: blob=base64.b64decode(required(value,"base64","Αρχείο"),validate=True)
        except (ValueError,TypeError) as exc:raise Problem(400,"Μη έγκυρο αρχείο.") from exc
        if not blob or len(blob)>20*1024*1024:raise Problem(413,"Το αρχείο πρέπει να είναι έως 20 MB.")
        mime=mimetypes.guess_type(name)[0] or "application/octet-stream"
        if mime not in ("application/pdf","image/png","image/jpeg","image/tiff"):
            raise Problem(400,"Επιτρέπονται PDF, PNG, JPG ή TIFF.")
        UPLOADS.mkdir(parents=True,exist_ok=True)
        digest=hashlib.sha256(blob).hexdigest()
        stored=f"{digest[:20]}-{os.urandom(6).hex()}"
        (UPLOADS/stored).write_bytes(blob)
        cur=c.execute("""INSERT INTO files(entity,entity_id,original_name,mime,stored_name,sha256,size,label,uploaded_at)
          VALUES(?,?,?,?,?,?,?,?,?)""",(entity,identifier,name,mime,stored,digest,len(blob),str(value.get("label","")).strip(),stamp))
        audit(c,entity,identifier,"Επισύναψη αρχείου",name)
        return {"id":cur.lastrowid,"name":name,"sha256":digest}
    raise Problem(404,"Άγνωστη ενέργεια.")


def api_put(c, pieces, value):
    if not isinstance(value,dict):raise Problem(400,"Μη έγκυρα δεδομένα.")
    stamp=now()
    if len(pieces)==2 and pieces[0]=="cases":
        identifier=int(pieces[1]);record=get(c,"cases",identifier)
        allowed={"received_at","email","council_ref","state","notes"}
        fields={k:str(v).strip() if v is not None else None for k,v in value.items() if k in allowed}
        if record["flow"]=="legacy": fields.pop("council_ref",None)
        if not fields:raise Problem(400,"Δεν δόθηκαν πεδία.")
        c.execute("UPDATE cases SET "+",".join(f"{k}=?" for k in fields)+",updated_at=? WHERE id=?",(*fields.values(),stamp,identifier))
        audit(c,"case",identifier,"Ενημέρωση στοιχείων",changes(record,fields))
        return {"saved":True}
    if len(pieces)==2 and pieces[0]=="lots":
        identifier=int(pieces[1]);record=get(c,"lots",identifier)
        allowed={"lot_no","sheet_plan","registration_no","title_no","title_status","area_sqm","general_value",
                 "valuation_value","valuation_date","valuation_ref","location","status","notes"}
        fields={k:money(v) if k in ("general_value","valuation_value") else str(v).strip() if v is not None else None for k,v in value.items() if k in allowed}
        published=c.execute("""SELECT 1 FROM notice_lots nl JOIN notices n ON n.id=nl.notice_id
          WHERE nl.lot_id=? AND n.state='Δημοσιευμένη' LIMIT 1""",(identifier,)).fetchone()
        fixed={"lot_no","sheet_plan","registration_no","title_no","title_status","area_sqm","general_value","valuation_value","valuation_date","valuation_ref","location"}
        if published and any(k in fields and fields[k]!=record[k] for k in fixed):
            raise Problem(409,"Τα στοιχεία προσφερόμενου οικοπέδου είναι σταθερά μετά τη δημοσίευση. Απαιτείται διορθωτική διαδικασία.")
        if "status" in fields and fields["status"] not in LOT_STATUSES:raise Problem(400,"Μη έγκυρη κατάσταση οικοπέδου.")
        if record["status"]=="awarded" and ("status" in fields and fields["status"]!="awarded"):
            raise Problem(409,"Δεν επιτρέπεται αλλαγή κατάστασης κατανεμημένου οικοπέδου χωρίς εγκεκριμένη διαδικασία.")
        if not fields:raise Problem(400,"Δεν δόθηκαν πεδία.")
        try:c.execute("UPDATE lots SET "+",".join(f"{k}=?" for k in fields)+",updated_at=? WHERE id=?",(*fields.values(),stamp,identifier))
        except sqlite3.IntegrityError as exc:raise Problem(409,"Διπλός αριθμός οικοπέδου στην υπόθεση.") from exc
        audit(c,"case",record["case_id"],"Ενημέρωση οικοπέδου",f"{record['lot_no']}: {changes(record,fields)}")
        return as_lot(get(c,"lots",identifier))
    if len(pieces)==2 and pieces[0]=="notices":
        identifier=int(pieces[1]);record=get(c,"notices",identifier)
        if record["state"]!="Προσχέδιο":raise Problem(409,"Η δημοσιευμένη γνωστοποίηση παραμένει αμετάβλητη.")
        allowed={"publication_date","start_date","deadline","submission_address","contact","notes"}
        fields={k:str(v).strip() if v is not None else None for k,v in value.items() if k in allowed}
        if not fields:raise Problem(400,"Δεν δόθηκαν πεδία.")
        c.execute("UPDATE notices SET "+",".join(f"{k}=?" for k in fields)+",updated_at=? WHERE id=?",(*fields.values(),stamp,identifier))
        audit(c,"notice",identifier,"Ενημέρωση προσχεδίου",changes(record,fields))
        return {"saved":True}
    if len(pieces)==2 and pieces[0]=="applications":
        identifier=int(pieces[1]);record=get(c,"applications",identifier)
        allowed={"protocol_no","family_type","preference","state","committee_decision","rank_no","notes","data"}
        fields={k:v for k,v in value.items() if k in allowed}
        if not fields:raise Problem(400,"Δεν δόθηκαν πεδία.")
        if "data" in fields:
            if not isinstance(fields["data"],dict):raise Problem(400,"Μη έγκυρα στοιχεία αίτησης.")
            fields["data"]=dump(fields["data"])
        if "committee_decision" in fields and fields["committee_decision"] not in ("Εκκρεμεί","Εγκρίνεται","Απορρίπτεται"):
            raise Problem(400,"Μη έγκυρη απόφαση Επιτροπής.")
        if "preference" in fields and fields["preference"] not in (None,""):
            fields["preference"]=int(fields["preference"])
        if "rank_no" in fields and fields["rank_no"] not in (None,""):
            fields["rank_no"]=int(fields["rank_no"])
        c.execute("UPDATE applications SET "+",".join(f"{k}=?" for k in fields)+",updated_at=? WHERE id=?",(*fields.values(),stamp,identifier))
        audit(c,"application",identifier,"Ενημέρωση αίτησης",changes(record,fields))
        return {"saved":True}
    raise Problem(404,"Άγνωστη ενέργεια.")


class Handler(BaseHTTPRequestHandler):
    server_version="HousingNicosia/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n"%(self.log_date_time_string(),fmt%args))

    def response(self, code, payload):
        blob=dump(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Length",str(len(blob)))
        self.end_headers();self.wfile.write(blob)

    def parse(self):
        parsed=urlparse(self.path)
        return parsed.path,parse_qs(parsed.query)

    def body(self):
        try:length=int(self.headers.get("Content-Length","0"))
        except ValueError:raise Problem(400,"Μη έγκυρο μήκος αιτήματος.")
        if length<1 or length>MAX_BODY:raise Problem(413,"Μη έγκυρο μέγεθος αιτήματος.")
        try:return json.loads(self.rfile.read(length))
        except (UnicodeDecodeError,ValueError) as exc:raise Problem(400,"Μη έγκυρο JSON.") from exc

    def handle_request(self, method):
        try:
            path,query=self.parse()
            if path.startswith("/api/"):
                pieces=[p for p in path.split("/") if p][1:]
                with connection() as c:
                    if method=="GET":value=api_get(c,pieces,query)
                    elif method=="POST":value=api_post(c,pieces,self.body())
                    elif method=="PUT":value=api_put(c,pieces,self.body())
                    else:raise Problem(405,"Μη επιτρεπτή ενέργεια.")
                return self.response(200,value)
            if method!="GET":raise Problem(404,"Άγνωστη διεύθυνση.")
            if re.fullmatch(r"/files/\d+",path):
                identifier=int(path.rsplit("/",1)[-1])
                with connection() as c:item=get(c,"files",identifier)
                blob=(UPLOADS/item["stored_name"]).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type",item["mime"])
                self.send_header("X-Content-Type-Options","nosniff")
                self.send_header("Content-Disposition","attachment; filename=\"document\"")
                self.send_header("Content-Length",str(len(blob)))
                self.end_headers();self.wfile.write(blob)
                return
            files={"/":ROOT/"static"/"index.html","/app.js":ROOT/"static"/"app.js","/style.css":ROOT/"static"/"style.css"}
            files.update({f"/templates/{name}":ROOT/"templates"/name for name in (
                "appendix1.docx","appendix2.docx","appendix3.docx","appendix4.doc","notice.docx")})
            target=files.get(path)
            if not target:raise Problem(404,"Η σελίδα δεν βρέθηκε.")
            blob=target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",mimetypes.guess_type(target)[0] or "text/plain")
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Length",str(len(blob)))
            self.end_headers();self.wfile.write(blob)
        except Problem as exc:self.response(exc.code,{"error":exc.message})
        except (ValueError,TypeError,sqlite3.Error) as exc:
            self.response(400,{"error":str(exc)[:300]})
        except Exception:
            traceback.print_exc()
            self.response(500,{"error":"Εσωτερικό σφάλμα. Ελέγξτε το ημερολόγιο του εξυπηρετητή."})

    def do_GET(self):self.handle_request("GET")
    def do_POST(self):self.handle_request("POST")
    def do_PUT(self):self.handle_request("PUT")


if __name__=="__main__":
    init_db()
    port=int(os.getenv("PORT","8765"))
    server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    print(f"Στεγαστικό Λευκωσίας: http://127.0.0.1:{port} (Ctrl+C για διακοπή)",flush=True)
    server.serve_forever()
