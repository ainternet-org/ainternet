"""
ainternet.attach — open your enclave from anywhere.

The portable, remote half of `attach`: every command is a signed probe.v1 frame POSTed to
<hub>/arena.probe. No broker, no local enclave, no 172.16.x — pure HTTP + an Ed25519 signature
over the same canonical the network verifies. Only the session key from YOUR claim opens the lane;
denied is indistinguishable from nonexistent (dark by default). Works from any machine that has
Python + cryptography — that's the whole point: from any browser/box in the world, bring up your
line and open your enclave.

This module is REMOTE-only on purpose (the local/broker-side `--fresh` spin-up lives in the enclave
tooling). Pair it with an arena claim to get a fresh session key + target.
"""

import json
import time
import secrets
import urllib.request
import urllib.error

DEFAULT_HUB = "https://api.ainternet.org"
PROBE_KIND = "org.ainternet.redstone.probe.v1"
PROBE_RESULT_KIND = "org.ainternet.redstone.probe-result.v1"
PROBE_OPS = ("health", "audit", "capture", "resolve", "get", "window", "relate", "route", "pty")
_US = "\x1f"


def _canonical(frame: dict) -> bytes:
    """US(0x1f)-join of sorted `key=compact-json(value)`, excluding `sig`. Byte-exact with the
    network's verifier — do not 'improve' the separators or ordering."""
    return _US.join(
        "%s=%s" % (k, json.dumps(frame[k], separators=(",", ":"), sort_keys=True, ensure_ascii=False))
        for k in sorted(frame) if k != "sig"
    ).encode("utf-8")


def _load_key(path_or_hex: str):
    """Load an Ed25519 private key from a FILE (64-char hex / PEM / raw 32 bytes) OR directly from a
    64-char hex seed passed on the command line (so the key from the browser claim page works inline)."""
    import os
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    v = (path_or_hex or "").strip()
    if v and not os.path.exists(v):
        if len(v) == 64 and all(c in "0123456789abcdefABCDEF" for c in v):
            return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(v))
        raise SystemExit("  --key: not a file and not a 64-char hex seed: %r" % v)
    raw = open(v, "rb").read()
    s = raw.strip()
    if len(s) == 64 and all(c in b"0123456789abcdefABCDEF" for c in s):
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(s.decode()))
    try:
        return serialization.load_pem_private_key(raw, password=None)
    except Exception:
        return Ed25519PrivateKey.from_private_bytes(s[:32])


def _probe(probe_url, raint, priv, pub, op, arg=""):
    """Build, sign, POST one probe.v1 frame. Returns the probe-result dict, or None on dark."""
    frame = {
        "kind": PROBE_KIND, "raint": raint, "op": op, "arg": arg or "",
        "session_pubkey": pub, "issued_at": int(time.time()),
        "nonce": "probe-%s" % secrets.token_hex(12),
    }
    frame["sig"] = "ed25519:" + priv.sign(_canonical(frame)).hex()
    req = urllib.request.Request(probe_url, data=json.dumps(frame).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "ainternet-attach/1"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=20) as r:
            txt = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return None
    try:
        res = json.loads(txt)
    except Exception:
        return None
    return res if isinstance(res, dict) and res.get("kind") == PROBE_RESULT_KIND else None


def _show(res):
    """Dark stays dark (print nothing). Otherwise print the surface payload."""
    if not res:
        return
    st, data = res.get("status"), res.get("data")
    if st is None:
        return
    if isinstance(data, dict):
        if data.get("result") == "0x0000":
            return
        print("  " + json.dumps(data, indent=2).replace("\n", "\n  "))
    elif data and str(data).strip():
        print("  %s" % data)


HELP = """  probe lane — not a shell; every call lands in /audit:
    health · audit · capture · resolve <name> · get <path> · window
    relate <peer> [surfaces] · route <peer> <surface> [intent] · pty [subject] [ttl]
    help · quit"""


def attach_remote(raint, key_path, hub=DEFAULT_HUB):
    """Open the identity-gated probe lane to `raint` over <hub>/arena.probe, using your session key."""
    from cryptography.hazmat.primitives import serialization
    priv = _load_key(key_path)
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    base = hub.rstrip("/")
    probe_url = base if base.endswith("/arena.probe") else base + "/arena.probe"
    res = _probe(probe_url, raint, priv, pub, "health")
    if res is None:
        print("\n  the door stayed dark — this session key isn't bound to %s, or the window has closed." % raint)
        print("  remote attach is identity-gated: only the key from YOUR claim opens it.")
        return 2
    ident = ((res.get("data") or {}).get("identity") or {}) if isinstance(res.get("data"), dict) else {}
    print("\n⛴  attached (remote) → %s" % ident.get("aint", raint))
    print("   %s · not a shell · every call lands in /audit" % probe_url)
    print(HELP)
    while True:
        try:
            line = input("\nraint> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\ndetached. the rig keeps its own audit; nothing followed you out."); return 0
        if not line:
            continue
        cmd, _, arg = line.partition(" ")
        cmd, arg = cmd.lower(), arg.strip()
        if cmd in ("quit", "exit", "q"):
            print("detached. the rig keeps its own audit; nothing followed you out."); return 0
        if cmd == "help":
            print(HELP); continue
        if cmd not in PROBE_OPS:
            print("  unknown command: %s   (try: help)" % cmd); continue
        r = _probe(probe_url, raint, priv, pub, cmd, arg)
        if cmd == "window" and r:
            print("  %ss left" % (r.get("data") or {}).get("window_s_left", "?")); continue
        _show(r)   # dark → nothing
