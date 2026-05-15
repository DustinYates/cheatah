"""Update BSS Telnyx AI assistants to send the registration link earlier.

Removes the address/birthdate gate that's causing drop-off in the BSS voice/SMS
agents. Replaces three sections in the assistant prompt:

  1. PROACTIVE REGISTRATION LINK OFFER (or REGISTRATION OFFER)
  2. REGISTRATION INFO COLLECTION  -> renamed OPTIONAL POST-LINK ENRICHMENT
  3. MANDATORY PRE-TEXT REQUIREMENTS (relaxed)

New flow: as soon as level + location + a picked class_id are known, fire
send_registration_link immediately. Address/birthdate become OPTIONAL post-link
enrichment.

Usage:
    # Step 1 — back up current prompts and show a diff (no changes pushed):
    uv run python scripts/update_bss_registration_flow.py --dry-run

    # Step 2 — push the changes (only after reviewing the diff):
    uv run python scripts/update_bss_registration_flow.py --apply

Backups go to docs/bss_prompt_backups/<timestamp>/<assistant_name>.txt
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import httpx
from cryptography.fernet import Fernet, InvalidToken

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# ----- Load .env without depending on the full app -----------------------------

def _load_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = _load_dotenv(REPO_ROOT / ".env")
DATABASE_URL = ENV.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
FIELD_ENCRYPTION_KEY = ENV.get("FIELD_ENCRYPTION_KEY") or os.environ.get("FIELD_ENCRYPTION_KEY")

# DATABASE_URL/FIELD_ENCRYPTION_KEY only required if we have to decrypt the API key.
# If TELNYX_API_KEY is set in env or .env, those aren't needed.


# ----- Decrypt the per-tenant Telnyx API key from Supabase ---------------------

def _decrypt(encrypted: str) -> str:
    """Match app/core/encryption.py: 'enc:' prefix + Fernet."""
    if not encrypted:
        return ""
    if encrypted.startswith("enc:"):
        encrypted = encrypted[4:]
    f = Fernet(FIELD_ENCRYPTION_KEY.encode() if isinstance(FIELD_ENCRYPTION_KEY, str) else FIELD_ENCRYPTION_KEY)
    try:
        return f.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        # Maybe stored as plaintext (legacy)
        return encrypted


async def _get_telnyx_api_key(tenant_id: int = 3) -> str:
    """Get the Telnyx API key.

    Order of precedence:
      1. TELNYX_API_KEY env var (or in .env)
      2. Decrypt from tenant_sms_configs.telnyx_api_key in Supabase
    """
    # 1. env var / .env
    env_key = ENV.get("TELNYX_API_KEY") or os.environ.get("TELNYX_API_KEY")
    if env_key:
        print("Using TELNYX_API_KEY from environment.")
        return env_key

    # 2. Supabase
    print(f"No TELNYX_API_KEY in env; decrypting from tenant_sms_configs (tenant_id={tenant_id})...")
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    async_url = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(async_url, echo=False)
    try:
        async with engine.connect() as conn:
            row = await conn.execute(
                text("SELECT telnyx_api_key FROM tenant_sms_configs WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
            r = row.first()
            if not r or not r[0]:
                raise RuntimeError(f"No telnyx_api_key found for tenant_id={tenant_id}")
            return _decrypt(r[0])
    finally:
        await engine.dispose()


# ----- Telnyx API ----------------------------------------------------------------

TELNYX_BASE = "https://api.telnyx.com/v2"


async def list_assistants(api_key: str) -> list[dict]:
    """List all AI assistants visible to this API key."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{TELNYX_BASE}/ai/assistants",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        body = r.json()
        # Telnyx returns either {"data": [...]} or a bare list depending on endpoint
        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body


async def get_assistant(api_key: str, assistant_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{TELNYX_BASE}/ai/assistants/{assistant_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        body = r.json()
        return body.get("data", body)


async def patch_instructions(api_key: str, assistant_id: str, new_instructions: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.patch(
            f"{TELNYX_BASE}/ai/assistants/{assistant_id}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"instructions": new_instructions},
        )
        if r.status_code >= 400:
            print(f"  PATCH error {r.status_code}: {r.text[:500]}")
        r.raise_for_status()
        body = r.json()
        return body.get("data", body)


# ----- The replacement ----------------------------------------------------------

# Possible start markers (handle both the old "REGISTRATION OFFER" form and the
# newer "PROACTIVE REGISTRATION LINK OFFER" form)
START_MARKERS = [
    "PROACTIVE REGISTRATION LINK OFFER (REQUIRED FLOW)",
    "PROACTIVE REGISTRATION LINK OFFER",
    "REGISTRATION OFFER (REQUIRED FLOW)",
    "REGISTRATION OFFER",
]

# End marker = the section that starts AFTER MANDATORY PRE-TEXT REQUIREMENTS
END_MARKERS = [
    "LOCATION FLOW (REQUIRED)",
    "LOCATION FLOW",
]


NEW_BLOCK = """PROACTIVE REGISTRATION LINK OFFER (REQUIRED FLOW) Once the swimmer's level AND preferred location are both confirmed, walk the caller through the schedule using get_classes. Present 1-2 matching options, e.g. "I've got [class] on [day] at [time] - want me to grab that one?" The MOMENT the caller picks a specific class day/time (or even leans toward one), send the registration link IMMEDIATELY. Do NOT ask permission first. Do NOT collect contact info first. Do NOT ask for address or birthdate. Call send_registration_link right away with: to ({{telnyx_end_user_target}}), org_id "545911", location code (confirmed pool), type code (confirmed level), class_id (the picked class). Include first_name, last_name, email, address, students ONLY if the caller has already volunteered them - otherwise OMIT those fields. Then say: "Texting you the registration link now - your class is pre-selected, just add your contact info and payment on the form." Do NOT wait for the caller to ask for the link. Do NOT re-confirm before sending. === OPTIONAL POST-LINK ENRICHMENT === The link has already been sent. Any further info collection is OPTIONAL and only to help the caller - never to gate the link. You may offer ONCE: "If you'd like, share your email, home address, and the swimmer's date of birth and I can update the link to pre-fill them too. Or just fill them on the form - totally up to you." If they share info: call send_registration_link AGAIN with the additional fields included (same to, org_id, location, type, class_id plus the new fields). If they decline or stay quiet: say "Sounds good - everything you need is in that link" and move on. NEVER ask for address, birthdate, or gender BEFORE the link has been sent. NEVER re-pitch the enrichment offer if they already declined. NEVER refuse to end the call because address/birthdate weren't collected. === END OPTIONAL POST-LINK ENRICHMENT === MANDATORY PRE-TEXT REQUIREMENTS (STRICT GATE) Before using the send_registration_link tool, you MUST have ONLY: (1) Caller's preferred location (confirmed - required for URL), (2) Swimmer's recommended level (confirmed - required for type code), AND (3) a class_id picked from get_classes (so the form loads with a specific class). That's it. Name, email, address, birthdate, and gender are NO LONGER required to send the link. They can be added later by re-calling send_registration_link with the new fields included. If location is unknown, follow the LOCATION FLOW section below to ask for ZIP and map to a pool. If the caller says "just send me the link" - send it the moment location, level, and class_id are known. Do NOT ask for any other info first. If location is missing, ask only for ZIP. If level is missing, ask the 1-2 quick placement questions needed to pick a level. Then call send_registration_link. """


def find_first(text: str, candidates: list[str]) -> tuple[int, str] | None:
    for c in candidates:
        i = text.find(c)
        if i >= 0:
            return i, c
    return None


def build_new_prompt(orig: str) -> tuple[str | None, str]:
    """Returns (new_prompt, status_msg). new_prompt is None if no clean boundary."""
    s = find_first(orig, START_MARKERS)
    if s is None:
        return None, "no start marker found"
    s_idx, s_marker = s

    e = find_first(orig[s_idx:], END_MARKERS)
    if e is None:
        return None, "no end marker found after start"
    e_idx_rel, e_marker = e
    e_idx = s_idx + e_idx_rel

    new_text = orig[:s_idx] + NEW_BLOCK + orig[e_idx:]
    msg = (
        f"start='{s_marker}' @ {s_idx}, end='{e_marker}' @ {e_idx}, "
        f"replaced {e_idx - s_idx} chars with {len(NEW_BLOCK)} chars "
        f"(net {len(new_text) - len(orig):+d})"
    )
    return new_text, msg


# ----- Driver ------------------------------------------------------------------

BSS_NAME_PREFIXES = ("003_BSS", "004_BSS", "005_BSS")
BACKUP_DIR = REPO_ROOT / "docs" / "bss_prompt_backups"


async def main(apply: bool, only: str | None = None) -> None:
    print("=" * 70)
    print(f"BSS REGISTRATION FLOW UPDATE  ({'APPLY MODE' if apply else 'DRY RUN'})")
    print("=" * 70)

    api_key = await _get_telnyx_api_key(tenant_id=3)
    print(f"\nDecrypted Telnyx API key (prefix): {api_key[:8]}...")

    print("\nListing AI assistants...")
    assistants = await list_assistants(api_key)
    bss = [a for a in assistants if str(a.get("name", "")).startswith(BSS_NAME_PREFIXES)]
    if only:
        before = len(bss)
        bss = [a for a in bss if only.lower() in str(a.get("name", "")).lower()]
        print(f"Filter --only={only!r}: {before} -> {len(bss)} assistants")
    print(f"Found {len(assistants)} assistants total, {len(bss)} BSS:")
    for a in bss:
        print(f"  - {a.get('name')}  ({a.get('assistant_id') or a.get('id')})")

    if not bss:
        print("\nNo BSS assistants found - aborting.")
        return

    ts = time.strftime("%Y%m%d_%H%M%S")
    run_dir = BACKUP_DIR / ts
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nBackups will be written to: {run_dir}")

    summary: list[tuple[str, str]] = []

    for a in bss:
        aid = a.get("assistant_id") or a.get("id")
        name = a.get("name", aid)
        print(f"\n--- {name} ({aid}) ---")

        full = await get_assistant(api_key, aid)
        instructions = full.get("instructions") or ""
        print(f"  current instructions: {len(instructions)} chars")

        # Backup
        bak_path = run_dir / f"{name}__{aid}__BEFORE.txt"
        bak_path.write_text(instructions)
        print(f"  backup -> {bak_path.relative_to(REPO_ROOT)}")

        new_text, msg = build_new_prompt(instructions)
        if new_text is None:
            print(f"  SKIP: {msg}")
            summary.append((name, f"SKIPPED ({msg})"))
            continue

        print(f"  diff: {msg}")
        new_path = run_dir / f"{name}__{aid}__AFTER.txt"
        new_path.write_text(new_text)
        print(f"  proposed -> {new_path.relative_to(REPO_ROOT)}")

        if apply:
            print("  PATCHing assistant...")
            await patch_instructions(api_key, aid, new_text)
            print("  patched.")
            summary.append((name, "PATCHED"))
        else:
            summary.append((name, "DRY-RUN (would patch)"))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, status in summary:
        print(f"  {status:30s}  {name}")
    print(f"\nBackup directory: {run_dir}")
    if not apply:
        print("\nDry run only. Re-run with --apply to push changes.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Actually PATCH the assistants. Default is dry-run.")
    p.add_argument("--dry-run", action="store_true", help="Explicit dry-run (default).")
    p.add_argument("--only", type=str, default=None, help="Only operate on assistants whose name contains this substring (case-insensitive). E.g. --only Cypress")
    args = p.parse_args()
    asyncio.run(main(apply=args.apply, only=args.only))
