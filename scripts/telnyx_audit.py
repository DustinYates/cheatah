#!/usr/bin/env python3
"""Audit (and optionally repair) Telnyx messaging bindings against the DB.

Read-only by default:      TK=$TK python3 telnyx_audit.py
Apply the fixes it found:  TK=$TK python3 telnyx_audit.py --fix

Checks, per tenant:
  1. phone number -> messaging_profile_id      (where inbound SMS lands)
  2. phone number -> connection_id             (voice routing; reported only)
  3. assistant    -> default_messaging_profile (which profile the AI listens on)
  4. profile      -> webhook_url               (must be a route that handles
                                                message.received)

The June 2026 outage was #1 and #3 drifting onto ConvoPro's tenant-1 profile.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://api.telnyx.com/v2"
TK = os.environ.get("TK") or os.environ.get("TELNYX_API_KEY")
FIX = "--fix" in sys.argv

WEBHOOK = "https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/inbound"

# tenant_id, name, number, expected messaging profile, expected connection, assistant
TENANTS = [
    (1,   "ConvoPro",          "+12816990999", "40019bcc-29bb-4576-949f-8be8115f2de4", "2874870294063875315", "assistant-ed763aa1-a8af-4776-92aa-c4b0ed8f992d"),
    (3,   "BSS Cypress-Spring","+12817679141", "40019c06-bc41-4743-84d9-7f99d26d8773", "2883082129355310357", "assistant-109f3350-874f-4770-87d4-737450280441"),
    (237, "BSS Atlanta",       "+17707999831", "40019c4a-9c82-4afa-a490-37be397dc28c", "2891910628283254206", "assistant-ad815abc-af54-4c1e-a623-e04aff218a1b"),
    (330, "BSS Raleigh",       "+19842138486", "40019c72-d4a2-4a78-8c9d-e64cb80a5284", "2898326670731642034", "assistant-4c290c36-20eb-46dd-be44-54fda217e4de"),
    (342, "InsureUs",          "+12815353467", "40019c76-2df0-40b3-9af5-697e6e58b481", "2859645279680857439", "assistant-34b96367-9ac6-43a3-b903-b6daa29f5b41"),
    (343, "ExoticaFlowers",    "+12818578796", "40019c81-885a-48d8-ae09-019a09fe2619", None,                  "assistant-deea0094-e643-4060-bf7d-96b346bb0108"),
]

PROFILE_OWNER = {p: f"t{t} {n}" for t, n, _, p, _, _ in TENANTS}


def call(method, path, body=None):
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {TK}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        return {"_error": f"{e.code} {e.read()[:200].decode(errors='replace')}"}
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e)}


def owner(profile_id):
    """Name the tenant a profile belongs to - makes cross-tenant drift obvious."""
    return PROFILE_OWNER.get(profile_id, "UNKNOWN")


def main():
    if not TK:
        sys.exit("set TK to the Telnyx API key first:  export TK=$(gcloud secrets versions access latest --secret=telnyx-api-key --project=chatbots-466618)")

    drift = []
    stale_db = []
    for tid, name, number, want_profile, want_conn, assistant in TENANTS:
        print(f"\n=== t{tid} {name}  {number} ===")

        q = urllib.parse.quote(number, safe="")
        num = call("GET", f"/phone_numbers?filter%5Bphone_number%5D={q}")
        if num.get("_error") or not num.get("data"):
            print(f"  number    ! lookup failed: {num.get('_error', 'not found')}")
            continue
        n = num["data"][0]
        got_profile, got_conn, num_id = n.get("messaging_profile_id"), n.get("connection_id"), n["id"]

        a = call("GET", f"/ai/assistants/{assistant}")
        got_ap = None
        if a.get("_error"):
            print(f"  assistant ! {a['_error']}")
        else:
            got_ap = (a.get("messaging_settings") or {}).get("default_messaging_profile_id")

        # Number and assistant must agree with EACH OTHER for SMS to work at
        # all. When they agree but differ from the DB, Telnyx is the working
        # truth and the DB is stale - repairing toward the DB would break a
        # live number. Only repair when they actually disagree.
        agree = got_profile is not None and got_profile == got_ap
        num_ok, asst_ok = got_profile == want_profile, got_ap == want_profile

        print(f"  number -> profile     {'OK ' if num_ok else 'DRIFT'}  {got_profile} ({owner(got_profile)})")
        if not num_ok:
            print(f"                        expected {want_profile} ({owner(want_profile)})")
        print(f"  assistant -> profile  {'OK ' if asst_ok else 'DRIFT'}  {got_ap} ({owner(got_ap)})")

        if agree and not num_ok:
            print("  >> number and assistant AGREE on a profile the DB doesn't know.")
            print("     Telnyx is self-consistent and probably working - treating the DB")
            print("     as stale. NOT auto-fixed. Verify by texting the number, then run:")
            print(f"     update tenant_sms_configs set telnyx_messaging_profile_id='{got_profile}' where tenant_id={tid};")
            stale_db.append((tid, name, number, got_profile))
        elif not agree:
            print("  >> number and assistant DISAGREE - inbound SMS is broken here.")
            if not num_ok:
                drift.append(("number", tid, num_id, want_profile))
            if not asst_ok:
                drift.append(("assistant", tid, assistant, want_profile))

        if want_conn and got_conn != want_conn:
            print(f"  number -> connection  DRIFT  {got_conn} ({owner_conn(got_conn)})  expected {want_conn}")
            print("                        (voice - reported only, not auto-fixed)")

        # Audit the profile the number ACTUALLY uses, not the one the DB
        # claims - otherwise a stale DB row sends us auditing a dead profile.
        live_profile = got_profile or want_profile
        p = call("GET", f"/messaging_profiles/{live_profile}")
        if p.get("_error"):
            print(f"  profile   ! {p['_error']}")
        else:
            got_hook = (p.get("data") or {}).get("webhook_url")
            ok = got_hook == WEBHOOK
            print(f"  profile -> webhook    {'OK ' if ok else 'DRIFT'}  {got_hook}")
            if not ok:
                drift.append(("webhook", tid, live_profile, WEBHOOK))

    print(f"\n{'=' * 60}")
    if stale_db:
        print(f"{len(stale_db)} tenant(s) where Telnyx is self-consistent but the DB is stale:")
        for tid, name, number, prof in stale_db:
            print(f"  t{tid} {name} {number} -> {prof}   (verify by text, then update the DB)")
    print(f"{len(drift)} drifted binding(s) safe to repair")
    if not drift:
        return
    if not FIX:
        print("re-run with --fix to repair")
        return

    print("\napplying fixes...")
    for kind, tid, target, want in drift:
        if kind == "number":
            r = call("PATCH", f"/phone_numbers/{target}/messaging", {"messaging_profile_id": want})
        elif kind == "assistant":
            r = call("PATCH", f"/ai/assistants/{target}",
                     {"messaging_settings": {"default_messaging_profile_id": want,
                                             "delivery_status_webhook_url": WEBHOOK}})
        else:
            r = call("PATCH", f"/messaging_profiles/{target}", {"webhook_url": want})
        print(f"  t{tid} {kind}: {'ERROR ' + r['_error'] if r.get('_error') else 'fixed'}")


def owner_conn(conn_id):
    for t, n, _, _, c, _ in TENANTS:
        if c == conn_id:
            return f"t{t} {n}"
    return "UNKNOWN"


if __name__ == "__main__":
    main()
