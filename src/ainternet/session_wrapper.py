"""Session wrapper — a runtime's signed actor context, key OUTSIDE the model context.

A volatile runtime (Codex's CLI, the home-agent, root_idd, ...) acts AS a durable `.aint`
by SIGNING each request with an Ed25519 key this wrapper holds on disk. The key is loaded by
THIS code and lives in the wrapper instance — it is NEVER placed in the model's prompt or
context, so prompt-injection cannot exfiltrate what the model never sees (API != actor:
attribution lands on the key/identity, not on the volatile process).

It produces the `X-Agent-ID` / `X-Challenge` / `X-Signature` headers the brain's JIS-001 M2M
path verifies (`identity_verify.verify_identity_request`): challenge is `{nonce}:{unix_ts}`
(fresh within a short window, anti-replay), signature is base64 Ed25519 over the challenge.

AUTHORIZATION RULE: trust is structure, not a score. Authorization MUST depend ONLY on the JIS
signature, TIBET provenance, causal forward-only order, and MUX lane policy — never on a posture
score (the `x-jis-posture-hint`/`x-jis-trust` value is UX, never a decision input).

This is the client side of the identity-binding flagship. Codex's CLI is the first runtime to
use it (the plot twist: the agent that diagnosed its own actor-fiction gets bound first); the
same wrapper generalizes to every runtime that announces.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


class SessionWrapper:
    """Holds a runtime's signing key (off-context) and emits signed actor-context headers."""

    def __init__(self, agent_id: str, keyfile: str | Path):
        self.agent_id = agent_id
        # The private key lives here, loaded from disk by the wrapper — never in a prompt.
        self._sk = self._load_key(Path(keyfile))

    @staticmethod
    def _materialize_sealed(path: Path) -> dict:
        """Unseal a TBZ-sealed (.tza) keyfile through the Airlock at LOAD time.

        The at-rest form is never a plain bearer file. The plaintext exists only ephemerally
        in a tmpdir wiped before this returns; the materialize is the login/fetch moment (the
        runtime pulls a *sealed* envelope and opens it behind the gate, not a flat object).
        Full bearer-elimination = TPM sign-inside; on a software box this is the defense-in-depth
        tier: tamper-evident envelope + Airlock + a custodian key that gates the unseal.
        """
        custodian = os.environ.get("AINT_KEY_CUSTODIAN")
        if not custodian or not Path(custodian).exists():
            raise ValueError("sealed keyfile needs AINT_KEY_CUSTODIAN (recipient privkey path)")
        cpath = Path(custodian)
        try:  # custodian = a key.json with a private_key field, or a raw hex file
            priv_hex = json.loads(cpath.read_text(encoding="utf-8")).get("private_key")
        except Exception:
            priv_hex = cpath.read_text(encoding="utf-8").strip()
        if not priv_hex:
            raise ValueError(f"no private key in custodian {cpath}")
        tmp = Path(tempfile.mkdtemp(prefix="aint-mat-"))
        try:
            hexf = tmp / "cust.hex"
            hexf.write_text(priv_hex, encoding="utf-8")
            hexf.chmod(0o600)
            subprocess.run(
                ["tbz", "unpack", str(path), "--as", str(hexf), "-o", str(tmp), "--no-preview"],
                check=True, capture_output=True,
            )
            inner = next(p for p in tmp.iterdir() if p.name.endswith(".json"))
            return json.loads(inner.read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _load_key(path: Path) -> Ed25519PrivateKey:
        data = path.read_bytes()
        if data[:3] == b"TBZ" or path.suffix == ".tza":
            d = SessionWrapper._materialize_sealed(path)
        else:
            d = json.loads(data.decode("utf-8"))
        raw = d.get("private_key") or d.get("secret_key") or d.get("seed")
        if not raw:
            raise ValueError(f"no private key field in {path}")
        for decode in (base64.b64decode, bytes.fromhex):
            try:
                b = decode(raw)
            except Exception:
                continue
            if len(b) in (32, 64):
                return Ed25519PrivateKey.from_private_bytes(b[:32])
        raise ValueError("unrecognised Ed25519 private key encoding")

    @property
    def public_key_hex(self) -> str:
        return self._sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    def fresh_challenge(self) -> str:
        """`{nonce}:{unix_ts}` — the brain's is_fresh_challenge() reads the trailing timestamp."""
        return f"{secrets.token_hex(8)}:{int(time.time())}"

    def sign(self, message: str) -> str:
        """Base64 Ed25519 signature over the exact message bytes."""
        return base64.b64encode(self._sk.sign(message.encode("utf-8"))).decode("ascii")

    def actor_headers(self, challenge: str | None = None) -> dict:
        """The signed actor context for one request: X-Agent-ID / X-Challenge / X-Signature.

        JIS says: this runtime is acting as <agent_id>. TIBET can then record '<agent_id> did X
        in session Y' instead of 'the sandbox did X'. AINS resolves <agent_id> -> key/caps/inbox.
        """
        ch = challenge or self.fresh_challenge()
        return {
            "X-Agent-ID": self.agent_id,
            "X-Challenge": ch,
            "X-Signature": self.sign(ch),
        }

    @classmethod
    def from_env(cls, agent_id: str | None = None) -> "SessionWrapper | None":
        """Build a wrapper from AINT_AGENT_ID + AINT_KEYFILE, or None if not configured.

        Opt-in by design: with no keyfile env set, returns None so callers stay unsigned and
        unchanged. Set both env vars (e.g. for Codex's CLI: AINT_AGENT_ID=codex.aint and
        AINT_KEYFILE=/srv/jtel-stack/brain_api/data/agent_keys/codex.key.json) and every request
        that honours actor_headers() carries a fresh signed proof.
        """
        # AINT_AGENT_ID is the deliberate signing identity (the registry-canonical .aint) and wins
        # over a caller's display agent_id (e.g. "codex" vs the registry key "codex.aint").
        aid = os.environ.get("AINT_AGENT_ID") or agent_id
        keyfile = os.environ.get("AINT_KEYFILE")
        if not (aid and keyfile and Path(keyfile).exists()):
            return None
        try:
            return cls(aid, keyfile)
        except Exception:
            return None
