"""
aint-send — post-email send command (Phase 1)

Wraps AINS resolve + TBZ pack + tcd send into a single
mail-like UX:

    aint-send remco.aint "hi remco"
    aint-send factory.aint --file config.json --intent config-update

Phase 1 = Python wrapper, no encryption yet (= TBZ Light).
Phase 2+ = TBZ Sealed (AES-256-GCM) + SAM binding + multi-recipient.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests


# ─────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────

# Public AInternet name service (= fallback when no local brain_api).
# Legacy alias brein.jaspervandemeent.nl still mirrors the same API
# and is recognised by route-truth checks below for back-compat.
PUBLIC_AINS_BASE = "https://api.ainternet.org"
LEGACY_AINS_BASE = "https://brein.jaspervandemeent.nl"
LOCAL_AINS_BASE = "http://127.0.0.1:8000"

_AINS_BASE_CACHE: Optional[str] = None

# Path to tibet-zip / tbz binary
TBZ_BIN = shutil.which("tbz") or shutil.which("tibet-zip")
TCD_BIN = shutil.which("tcd") or shutil.which("tibet-continuityd")


def _get_default_ains_base() -> str:
    """Route-aware default AINS base URL.

    Order of preference:
      1. Explicit `AINT_AINS_BASE` environment variable.
      2. Local brain_api at 127.0.0.1:8000 if reachable within 1s
         (= same-host short-circuit on JTel-brain itself).
      3. Public AInternet name service at brein.jaspervandemeent.nl
         (= external clients like a fresh pixel VM on 5G).

    Result is cached per-process so we probe localhost at most once.
    """
    global _AINS_BASE_CACHE
    if _AINS_BASE_CACHE is not None:
        return _AINS_BASE_CACHE

    env = os.environ.get("AINT_AINS_BASE")
    if env:
        _AINS_BASE_CACHE = env
        return env

    try:
        resp = requests.get(f"{LOCAL_AINS_BASE}/api/ipoll/status", timeout=1)
        if resp.status_code == 200:
            _AINS_BASE_CACHE = LOCAL_AINS_BASE
            return LOCAL_AINS_BASE
    except Exception:
        pass

    _AINS_BASE_CACHE = PUBLIC_AINS_BASE
    return PUBLIC_AINS_BASE


# Backwards-compat shim: some callers still import DEFAULT_AINS_BASE.
# It now resolves lazily on first attribute access from typical code paths.
DEFAULT_AINS_BASE = LOCAL_AINS_BASE


# ─────────────────────────────────────────────────────────────────
# AINS resolution
# ─────────────────────────────────────────────────────────────────

def resolve_aint(name: str, ains_base: Optional[str] = None) -> dict:
    """Resolve a .aint name → AINS record (raises on failure)."""
    if ains_base is None:
        ains_base = _get_default_ains_base()

    # Strip .aint suffix if present
    if name.endswith(".aint"):
        name = name[:-5]

    url = f"{ains_base}/api/ains/resolve/{urllib.parse.quote(name)}"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(
            f"AINS resolve failed for {name}.aint via {ains_base}: {e}"
        ) from e

    if data.get("status") != "found":
        raise RuntimeError(
            f"AINS: {name}.aint not found (status={data.get('status')})"
        )

    return data


# ─────────────────────────────────────────────────────────────────
# Envelope naming (= SSM filename-surface contract)
# ─────────────────────────────────────────────────────────────────

def make_envelope_name(
    sender: str,
    intent: str,
    priority: str = "normal",
    context: Optional[str] = None,
) -> str:
    """Build canonical envelope name:
    <time-fragment>.<intent>.<sender>.<priority>[.<context>].tza
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
    # Sanitize sender (strip .aint suffix, lowercase)
    if sender.endswith(".aint"):
        sender = sender[:-5]
    sender = sender.lower().replace("_", "-")

    parts = [ts, intent, sender, priority]
    if context:
        parts.append(context.lower().replace("_", "-"))

    return ".".join(parts) + ".tza"


# ─────────────────────────────────────────────────────────────────
# TBZ pack
# ─────────────────────────────────────────────────────────────────

def pack_envelope(
    payload_path: Path,
    output_path: Path,
    verbose: bool = False,
) -> dict:
    """Pack a payload as TBZ envelope. Returns metadata dict."""
    if not TBZ_BIN:
        raise RuntimeError(
            "tbz binary not found. Install: cargo install tibet-zip-cli"
        )

    # tbz pack expects a directory; create a temp dir with the payload
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        # If payload is a file, copy it into tmpdir
        if payload_path.is_file():
            shutil.copy(payload_path, tmpdir_path / payload_path.name)
        elif payload_path.is_dir():
            # Already a dir, copy contents
            for child in payload_path.iterdir():
                if child.is_file():
                    shutil.copy(child, tmpdir_path / child.name)
        else:
            raise RuntimeError(f"payload not found: {payload_path}")

        # tbz pack <dir> -o <output>
        result = subprocess.run(
            [TBZ_BIN, "pack", str(tmpdir_path), "-o", str(output_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"tbz pack failed:\n{result.stderr}"
            )

        if verbose:
            print(result.stdout, file=sys.stderr)

        # Extract signing key from output if possible
        signing_key = None
        for line in result.stdout.splitlines():
            if "Ed25519 public" in line or "Signing key" in line:
                signing_key = line.strip()

        return {
            "envelope_path": str(output_path),
            "size_bytes": output_path.stat().st_size,
            "signing_key": signing_key,
        }


# ─────────────────────────────────────────────────────────────────
# Transport (Phase 1 = local + same-host)
# ─────────────────────────────────────────────────────────────────

def deliver_local(envelope_path: Path, inbox: Path) -> Path:
    """Deliver envelope to local inbox path (= same-host short-circuit)."""
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / envelope_path.name
    shutil.move(str(envelope_path), str(dest))
    return dest


def deliver_via_tcd(
    envelope_path: Path,
    target: str,
    verbose: bool = False,
) -> str:
    """Hand off to `tcd send` for cross-host or JIS-DID delivery."""
    if not TCD_BIN:
        raise RuntimeError(
            "tcd binary not found. Install: pip install tibet-continuityd"
        )

    # tcd send <envelope> --to <target>
    result = subprocess.run(
        [TCD_BIN, "send", str(envelope_path), "--to", target],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"tcd send failed:\n{result.stderr}")

    if verbose:
        print(result.stdout, file=sys.stderr)

    return result.stdout


def _find_session_token(sender: str) -> Optional[str]:
    """Find this sender's .aint session token, if any.

    The `ainternet claim` flow writes a session-token sidecar at
    ``~/.ainternet/<clean>.session.json`` where ``clean`` is the local
    label of the .aint domain. The actual full domain (e.g.
    ``pixel-test-d1b67733.aint``) lives inside that file under
    ``domain``, so we scan all session-json files and match.

    Returns the 64-char hex session token, or None if not found.

    Lookup order:
      1. ``~/.ainternet/<sender>.session.json``
      2. ``~/.ainternet/<sender-without-hash>.session.json``
      3. scan every ``*.session.json`` and match its ``domain`` field

    Auth is only needed for the public AInternet route — local
    brain_api short-circuit (=127.0.0.1) skips this requirement.
    """
    home = Path.home() / ".ainternet"
    if not home.exists():
        return None

    sender_clean = sender.replace(".aint", "").strip().lower()
    sender_full = f"{sender_clean}.aint"

    direct = home / f"{sender_clean}.session.json"
    if direct.exists():
        try:
            data = json.loads(direct.read_text())
            tok = data.get("session_token")
            if tok:
                return tok
        except Exception:
            pass

    if "-" in sender_clean:
        head = sender_clean.rsplit("-", 1)[0]
        cand = home / f"{head}.session.json"
        if cand.exists():
            try:
                data = json.loads(cand.read_text())
                if data.get("domain") == sender_full or data.get("domain", "").startswith(sender_clean):
                    tok = data.get("session_token")
                    if tok:
                        return tok
            except Exception:
                pass

    for session_file in home.glob("*.session.json"):
        try:
            data = json.loads(session_file.read_text())
            if data.get("domain") == sender_full:
                tok = data.get("session_token")
                if tok:
                    return tok
        except Exception:
            continue

    return None


def _resolve_ipoll_url(ipoll_endpoint: str) -> str:
    """Route-aware ipoll URL resolution.

    If the resolved endpoint claims our brain_api hostname AND a local
    brain_api is actually reachable, use 127.0.0.1:8000 (= legitimate
    same-host short-circuit). Otherwise use the resolved external URL.

    This replaces a brittle hostname-substring match with an actual
    route-truth check (Codex' Observation 2, cmail-first-cap-findings
    2026-05-14): locality must be derived from route truth, not from
    string coincidence.
    """
    if (
        "brein.jaspervandemeent.nl" in ipoll_endpoint
        or "api.ainternet.org" in ipoll_endpoint
    ):
        try:
            resp = requests.get(
                "http://127.0.0.1:8000/api/ipoll/status", timeout=1
            )
            if resp.status_code == 200:
                return "http://127.0.0.1:8000/api/ipoll/push"
        except Exception:
            pass
    # External path: append /push if endpoint omits it
    if not ipoll_endpoint.endswith("/push"):
        return ipoll_endpoint.rstrip("/") + "/push"
    return ipoll_endpoint


def notify_via_ipoll(
    sender: str,
    recipient: str,
    envelope_name: str,
    intent: str,
    body_preview: str,
    ipoll_endpoint: str,
    verbose: bool = False,
) -> dict:
    """Send I-Poll notification to recipient that a sealed envelope arrived.

    Phase 2: I-Poll = control plane (= "you've got cmail").
    Plus the envelope itself sits in local inbox (= data plane).
    Plus continuityd later picks it up + makes continuity decision
    (= decision plane).
    """
    ipoll_url = _resolve_ipoll_url(ipoll_endpoint)

    payload = {
        "from_agent": sender,
        "to_agent": recipient.replace(".aint", ""),
        "content": f"📬 cmail: {intent} — {body_preview[:100]}",
        "poll_type": "PUSH",
        "metadata": {
            "envelope_name": envelope_name,
            "intent": intent,
            "tbz_envelope_ref": f"/var/lib/tibet/inbox/{envelope_name}",
            "schema": "aint-send-v2",
        },
    }

    headers = {}
    if "127.0.0.1" not in ipoll_url and "localhost" not in ipoll_url:
        token = _find_session_token(sender)
        if token:
            headers["Authorization"] = f"Bearer {token}"
            if verbose:
                print(f"  → Auth: Bearer {token[:8]}… (.aint session)", file=sys.stderr)
        elif verbose:
            print(
                f"  → Auth: none found for {sender} "
                f"(=> external POST will likely 401)",
                file=sys.stderr,
            )

    try:
        resp = requests.post(ipoll_url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        if verbose:
            print(f"  → I-Poll notify: {result.get('id', '?')}", file=sys.stderr)
        return {
            "ipoll_message_id": result.get("id"),
            "tibet_token_id": result.get("tibet_token_id"),
            "delivery": result.get("delivery", "unknown"),
            "auto_responded": result.get("auto_responded", False),
            "sandbox_response": result.get("sandbox_response"),
        }
    except Exception as e:
        return {"error": str(e), "ipoll_url": ipoll_url}


# ─────────────────────────────────────────────────────────────────
# Main flow
# ─────────────────────────────────────────────────────────────────

def aint_send(
    recipient: str,
    body: Optional[str] = None,
    file: Optional[Path] = None,
    intent: str = "message",
    priority: str = "normal",
    context: Optional[str] = None,
    sender: str = "root_idd",
    ains_base: Optional[str] = None,
    verbose: bool = False,
    json_output: bool = False,
) -> dict:
    """Send a post-email envelope to a .aint recipient.

    Returns dict with:
      - resolved (AINS record)
      - envelope_name
      - envelope_path
      - delivery (where it went)
      - receipt (transport output)
    """
    steps = []

    # Step 1: Resolve
    if verbose:
        print(f"  → Resolving {recipient}...", file=sys.stderr)
    resolved = resolve_aint(recipient, ains_base)
    steps.append({"step": "resolve", "status": "ok", "agent": resolved["record"]["agent"]})

    # Step 2: Build payload
    if verbose:
        print(f"  → Building payload...", file=sys.stderr)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        if file:
            payload_file = Path(file)
            if not payload_file.exists():
                raise RuntimeError(f"file not found: {file}")
            # Will be packed directly
            payload_source = payload_file
        elif body:
            # Write inline body to a file
            payload_file = tmpdir_path / "body.txt"
            payload_file.write_text(body)
            payload_source = payload_file
        else:
            raise RuntimeError("must provide either body or --file")

        # Also create a manifest with intent/recipient metadata
        manifest_file = tmpdir_path / "aint-manifest.json"
        manifest_file.write_text(json.dumps({
            "schema": "aint-send-v2",
            "sender": sender,
            "recipient": recipient,
            "intent": intent,
            "priority": priority,
            "context": context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ains_endpoint": resolved.get("services", {}).get("ipoll"),
        }, indent=2))

        # Step 3: Envelope name
        envelope_name = make_envelope_name(sender, intent, priority, context)
        envelope_path = Path(tempfile.gettempdir()) / envelope_name

        # Step 4: Pack
        if verbose:
            print(f"  → Packing {envelope_name}...", file=sys.stderr)

        # Pack tmpdir (= contains body + manifest)
        if payload_source != payload_file:
            shutil.copy(payload_source, tmpdir_path / payload_source.name)

        pack_meta = pack_envelope(tmpdir_path, envelope_path, verbose=verbose)
        steps.append({"step": "pack", "status": "ok", **pack_meta})

    # Step 5: Determine transport
    record = resolved["record"]
    endpoint = record.get("endpoint", "")

    delivery = {"method": "unknown", "target": None}

    # Phase 2 routing:
    # 1. Envelope (= data plane) → always to local inbox first
    # 2. I-Poll notification (= control plane) → if endpoint reachable
    # 3. Local inbox kopie blijft als audit-shadow + continuityd pickup

    inbox = Path("/var/lib/tibet/inbox")
    dest = deliver_local(envelope_path, inbox)
    delivery = {"method": "local-inbox", "target": str(dest)}

    # Try I-Poll notification (= control plane signal to recipient)
    ipoll_endpoint = resolved.get("services", {}).get("ipoll")
    is_self = recipient.replace(".aint", "") == sender

    if ipoll_endpoint and not is_self:
        body_preview = body if body else f"file: {Path(file).name if file else '?'}"
        if verbose:
            print(f"  → Notifying via I-Poll: {ipoll_endpoint}", file=sys.stderr)
        ipoll_result = notify_via_ipoll(
            sender=sender,
            recipient=recipient,
            envelope_name=envelope_name,
            intent=intent,
            body_preview=body_preview,
            ipoll_endpoint=ipoll_endpoint,
            verbose=verbose,
        )
        delivery["ipoll_notify"] = ipoll_result
        if "error" not in ipoll_result:
            delivery["method"] = "local-inbox + ipoll-notify"

    steps.append({"step": "deliver", "status": "ok", **delivery})

    return {
        "recipient": recipient,
        "envelope_name": envelope_name,
        "resolved": resolved,
        "delivery": delivery,
        "steps": steps,
        "phase": "2-ipoll-notify",
    }


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="aint-send",
        description="Send a post-email envelope to a .aint recipient",
        epilog="Phase 1: TBZ Light (signed+compressed). Phase 2: TBZ Sealed + SAM.",
    )
    parser.add_argument("recipient", help="Recipient .aint domain (e.g. jasper.aint)")
    parser.add_argument("body", nargs="?", default=None, help="Inline message body")
    parser.add_argument("--file", help="Send a file instead of inline body")
    parser.add_argument("--intent", default="message", help="Intent declaration (default: message)")
    parser.add_argument("--priority", default="normal",
                        choices=["log-only", "background", "normal", "urgent"])
    parser.add_argument("--context", default=None, help="Optional context tag")
    parser.add_argument("--sender", default=os.environ.get("AINT_SENDER", "root_idd"),
                        help="Sender .aint identity (default: $AINT_SENDER or root_idd)")
    parser.add_argument("--ains-base", default=None,
                        help="AINS endpoint base "
                             "(default: auto — local brain_api if "
                             "reachable, otherwise brein.jaspervandemeent.nl)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show each pipeline step on stderr")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")

    args = parser.parse_args()

    if not args.body and not args.file:
        parser.error("must provide either body text or --file")

    try:
        result = aint_send(
            recipient=args.recipient,
            body=args.body,
            file=Path(args.file) if args.file else None,
            intent=args.intent,
            priority=args.priority,
            context=args.context,
            sender=args.sender,
            ains_base=args.ains_base,
            verbose=args.verbose,
            json_output=args.json,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"✓ Resolved      {args.recipient} → {result['resolved']['record']['agent']}")
            print(f"✓ Envelope      {result['envelope_name']}")
            print(f"✓ Delivered     {result['delivery']['method']}")
            print(f"                {result['delivery']['target']}")
            if "note" in result['delivery']:
                print(f"  Note:         {result['delivery']['note']}")
        return 0

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
