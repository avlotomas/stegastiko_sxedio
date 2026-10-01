"""Run the actual local HTTP server against an isolated temporary database."""

import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.url = f"http://127.0.0.1:{port}"
        cls.server = subprocess.Popen(
            [sys.executable, str(ROOT / "app.py")],
            cwd=ROOT,
            env={**os.environ, "HOUSING_DB": str(Path(cls.temp.name) / "test.sqlite3"), "PORT": str(port)},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        for _ in range(100):
            try:
                cls.call("/api/health")
                break
            except Exception:
                if cls.server.poll() is not None:
                    raise RuntimeError(cls.server.stderr.read().decode())
                time.sleep(0.05)
        else:
            raise RuntimeError("Local HTTP server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait(timeout=5)
        cls.server.stderr.close()
        cls.temp.cleanup()

    @classmethod
    def call(cls, route, method="GET", data=None):
        payload = None if data is None else json.dumps(data, ensure_ascii=False).encode()
        req = Request(cls.url + route, payload, method=method, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=4) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_two_flows_multi_community_multi_application(self):
        status, boot = self.call("/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertEqual(len(boot["areas"]), 102)
        a, b = boot["areas"][:2]
        self.assertEqual(self.call("/api/cases", "POST", {"area_id": 999999, "flow": "new"})[0], 400)

        _, old = self.call("/api/cases", "POST", {"area_id": a["id"], "flow": "legacy"})
        _, new = self.call("/api/cases", "POST", {"area_id": a["id"], "flow": "new", "email": "ks@example.org"})
        _, other = self.call("/api/cases", "POST", {"area_id": b["id"], "flow": "legacy"})
        self.assertNotEqual(old["case_no"], new["case_no"])
        self.assertEqual(self.call(f"/api/cases/{old['id']}/sections/1", "POST", {"interested": []})[0], 400)
        self.assertEqual(self.call(f"/api/cases/{old['id']}/sections/8.8", "POST", {"comments": "ανά οικόπεδο"})[0], 200)
        self.assertEqual(self.call(f"/api/cases/{new['id']}/sections/1", "POST", {"interested": [{"names": "Δοκιμή"}]})[0], 200)
        self.assertEqual(self.call(f"/api/cases/{new['id']}/sections/4", "POST", {"access": "Πρόσβαση από υφιστάμενη οδό"})[0], 200)

        _, l1 = self.call("/api/lots", "POST", {"case_id": old["id"], "lot_no": "Π-1", "title_status": "Υπάρχει τίτλος", "title_no": "Τ-1", "general_value": "100000"})
        _, l2 = self.call("/api/lots", "POST", {"case_id": old["id"], "lot_no": "Π-2", "title_status": "Δεν υπάρχει τίτλος", "valuation_ref": "ΤΚΧ-2", "valuation_value": "80000"})
        _, l3 = self.call("/api/lots", "POST", {"case_id": new["id"], "lot_no": "Ν-1", "title_status": "Υπάρχει τίτλος", "general_value": "120000"})
        _, l4 = self.call("/api/lots", "POST", {"case_id": other["id"], "lot_no": "Α-1", "title_status": "Δεν υπάρχει τίτλος", "valuation_ref": "ΤΚΧ-4", "valuation_value": "60000"})
        self.assertEqual([l1["disposal_price"], l2["disposal_price"], l3["disposal_price"], l4["disposal_price"]], ["25000.00", "20000.00", "30000.00", "15000.00"])
        self.assertEqual(self.call("/api/lots/2", "PUT", {"valuation_value": "84000"})[1]["disposal_price"], "21000.00")

        _, notice = self.call("/api/notices", "POST", {"lot_ids": [l1["id"], l2["id"], l3["id"], l4["id"]], "publication_date": "2026-09-27", "start_date": "2026-09-28", "deadline": "2026-10-31"})
        status, published = self.call(f"/api/notices/{notice['id']}/publish", "POST", {})
        self.assertEqual((status, published["state"]), (200, "Δημοσιευμένη"))
        self.assertEqual(self.call(f"/api/notices/{notice['id']}", "PUT", {"deadline": "2026-11-01"})[0], 409)
        self.assertEqual(self.call(f"/api/lots/{l1['id']}", "PUT", {"general_value": "200000"})[0], 409)
        _, detail = self.call(f"/api/notices/{notice['id']}")
        self.assertEqual(len(detail["offers"]), 4)
        self.assertEqual(len({x["area_id"] for x in detail["offers"]}), 2)
        self.assertEqual(len({x["case_id"] for x in detail["offers"] if x["area_id"] == a["id"]}), 2)

        person = {"notice_id": notice["id"], "identity_no": "TEST0001", "full_name": "Δοκιμαστικός Πολίτης", "received_at": "2026-10-01"}
        _, app_a = self.call("/api/applications", "POST", {**person, "area_id": a["id"], "preference": 1})
        _, app_b = self.call("/api/applications", "POST", {**person, "area_id": b["id"], "preference": 2})
        self.assertNotEqual(app_a["application_no"], app_b["application_no"])
        self.assertEqual(self.call("/api/applications", "POST", {**person, "area_id": a["id"]})[0], 409)
        _, application = self.call(f"/api/applications/{app_a['id']}")
        self.assertEqual(len(application["related"]), 1)
        self.assertEqual(application["related"][0]["area_id"], b["id"])
        self.assertEqual(self.call(f"/api/applications/{app_a['id']}/allocate", "POST", {"lot_id": l1["id"]})[0], 409)

        evidence = base64.b64encode(b"%PDF-1.4\nexample").decode()
        self.assertEqual(self.call("/api/files", "POST", {"entity": "application", "entity_id": app_a["id"], "name": "appendix3.pdf", "base64": evidence, "label": "Πρωτότυπο"})[0], 200)
        self.assertEqual(len(self.call(f"/api/applications/{app_a['id']}")[1]["files"]), 1)
        self.assertEqual(self.call(f"/api/applications/{app_a['id']}/sections/10.2.2", "POST", {"identity": {"state": "ΕΚΚΡΕΜΕΙ"}})[0], 200)
        self.assertEqual(self.call(f"/api/applications/{app_a['id']}/sections/10.2.2", "POST", {"identity": {"state": "ΠΡΟΣΚΟΜΙΣΤΗΚΕ"}})[0], 200)
        _, history = self.call(f"/api/history?entity=application&id={app_a['id']}")
        self.assertEqual(history[0]["previous_data"]["identity"]["state"], "ΕΚΚΡΕΜΕΙ")
        self.assertEqual(history[0]["new_data"]["identity"]["state"], "ΠΡΟΣΚΟΜΙΣΤΗΚΕ")
        self.assertEqual(self.call(f"/api/applications/{app_a['id']}/sections/10.4.6", "POST", {"incomes": [{"role": "Τέκνο", "salary": "1000"}]})[0], 200)
        criteria = {key: {"result": "ΠΛΗΡΟΥΤΑΙ", "notes": "Τεκμηριώθηκε"} for key in ("citizenship", "age", "residence", "property", "alienation", "income", "previous_aid")}
        _, result = self.call(f"/api/applications/{app_a['id']}/sections/10.4", "POST", criteria)
        self.assertEqual(result["summary"]["preliminary"], "Κατ’ αρχήν πληροί")
        self.assertEqual(self.call(f"/api/applications/{app_a['id']}", "PUT", {"committee_decision": "Εγκρίνεται"})[0], 200)
        self.assertEqual(self.call(f"/api/applications/{app_a['id']}/allocate", "POST", {"lot_id": l4["id"]})[0], 409)
        self.assertEqual(self.call(f"/api/applications/{app_a['id']}/allocate", "POST", {"lot_id": l1["id"]})[0], 200)
        self.assertEqual(self.call(f"/api/applications/{app_b['id']}", "PUT", {"committee_decision": "Εγκρίνεται"})[0], 200)
        self.assertEqual(self.call(f"/api/applications/{app_b['id']}/allocate", "POST", {"lot_id": l4["id"]})[0], 409)
        self.assertEqual(self.call(f"/api/applications/{app_a['id']}/allocate", "POST", {"lot_id": l2["id"]})[0], 409)
        self.assertEqual(self.call(f"/api/audit?entity=application&id={app_a['id']}")[0], 200)


if __name__ == "__main__":
    unittest.main()
