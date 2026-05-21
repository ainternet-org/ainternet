# Changelog

All notable changes to the `ainternet` package are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] — 2026-05-21

### Changed (BREAKING for fresh-claim flow — backward-compatible for sub-domain recovery)

- **Fresh `.aint` claim now requires Ed25519 proof-of-possession.**
  The `ainternet claim mybot` CLI flow (and any direct caller of
  `AINSClaim.quick()`) is now a two-step ceremony:

      1. POST /api/ainternet/claim/challenge {public_key, requested_name}
         → returns {challenge_id, sign_target, expires_at}
      2. Sign sign_target = "ainternet-claim:v1:{challenge_id}" locally
         with the Ed25519 private key behind the public_key.
      3. POST /api/ainternet/claim with the existing fields plus
         {challenge_id, signature}.

  The server verifies the signature against the public_key bound to
  the challenge and rejects (401) on missing / unknown / expired /
  bad signature, or (400) on name_mismatch / key_mismatch. The
  client-side `quick()` method handles all of this transparently —
  no behavioural change for users running `ainternet claim`.

- **Sub-domain recovery is unaffected.** When `requested_name`
  contains a dot (e.g. `storm.vandemeent`), the call short-circuits
  on the existing hardware_hash + prior ParentAttest device_rebind
  proof. No challenge/signature is required or expected on that
  path — and the new `/claim/challenge` endpoint refuses such names
  on principle.

### Why

The 21 May 2026 claim-routing review (Jasper) flagged that the
existing `/api/ainternet/claim` endpoint accepted any `public_key`
field without proof that the caller owns the matching private key.
The resulting AINS record carried a hollow public_key — anyone
could mint a `.aint` with a borrowed pubkey and the server would
record it as if the holder had proved possession.

The fix follows the principle laid out in the same review:

> *"als aint je persoonlijk id vc account is, [...] mag een taak
> niet zonder duidelijke opdrachtgever en locatie bestaan. [...]
> Een VC kan niet zonder hardware-koppeling, versleuteling en
> encryptie bestaan."*

Stage 1 (the claim itself) now matches the same Ed25519-signed
challenge-response discipline that Stages 2 (passkey-register) and
3 (device-link/complete) already require. One canonical ceremony,
no half/half claiming.

### Spec / cross-refs

- Sign-target prefix: `ainternet-claim:v1:` (matches the existing
  `ainternet-device-link:v1:` / `ainternet-auth` domain-separation
  convention).
- Challenge TTL: 60 seconds, single-use (consumed on first lookup).
- Signature + pubkey encoding: hex (preferred) or base64
  (auto-detected on the server via `_decode_key_material`).
- Server-side implementation: `brain_api/ainternet_claim.py`
  (`/api/ainternet/claim/challenge` + verify gate in `/claim`).

### Acknowledgements

Routing principle articulated by Jasper, 21 May 2026. The "split,
diff/sift, merge, allign" choreography around bilateral identity
events (also same day) anchored the choice not to invent a new
endpoint family but to extend the existing one with a precondition.

---

## [0.8.6] — 2026-05-14

### Added
- **`ainternet claim` now auto-registers with I-Poll** — after a successful
  AINS claim, the client posts the new identity to `/api/ipoll/register`
  so the agent is immediately known to the messaging layer. This closes
  the historical AINS↔I-Poll split-brain on the client side: fresh
  installs no longer need to wait for the server-side AINS-fallback in
  ``is_agent_approved`` to auto-promote them on first push. The
  registration is best-effort — server-side fallback still covers all
  failure modes — so claim itself never breaks. Result is echoed back
  as ``_ipoll_registered`` in the claim payload.

## [0.8.5] — 2026-05-14

### Fixed
- **`cmail` now sends the sender's session token** as
  `Authorization: Bearer …` on external POSTs to `/api/ipoll/push`.
  Previously every external client (e.g. a fresh pixel VM on 5G) got
  `401 Unauthorized` because AuthGuardMiddleware requires either a
  JWT or a 64-char hex .aint session token. `ainternet claim …` already
  writes that token to ``~/.ainternet/<clean>.session.json``; cmail
  now reads it via three lookup paths (direct match → strip-suffix
  match → scan-and-match by `domain` field). Local short-circuit
  through `127.0.0.1` continues to skip auth.

## [0.8.4] — 2026-05-14

### Fixed
- **`cmail` HTTP requests use the `requests` library** — Cloudflare in
  front of `brein.jaspervandemeent.nl` returns `403 Forbidden` to the
  default `Python-urllib/3.x` User-Agent, but accepts `python-requests`.
  The rest of the `ainternet` library already uses `requests`; the
  `post_send` module was the inconsistent stdlib-`urllib.request`
  hold-out and is now aligned. External clients (pixel 5G, etc.) now
  successfully resolve and notify through the public AInternet name
  service.

## [0.8.3] — 2026-05-14

### Fixed
- **`cmail` AINS-resolve also route-aware** — 0.8.2 fixed only the
  I-Poll notification step. The AINS resolve in `resolve_aint()` still
  defaulted to `127.0.0.1:8000`, causing `errno 111` on external
  clients (e.g. a fresh pixel VM on 5G) before the resolve even ran.
  The default AINS base is now `auto`:
    1. respect `$AINT_AINS_BASE` env var if set
    2. probe local brain_api (1s timeout) — use if reachable
    3. fall back to the public AInternet name service at
       `https://brein.jaspervandemeent.nl`
  The result is cached per-process so we probe localhost at most once.

## [0.8.2] — 2026-05-14

### Fixed
- **`cmail` works from external hosts** — the I-Poll notification step
  previously assumed a brain_api on `127.0.0.1:8000` whenever the
  resolved endpoint matched our hostname. On external clients (e.g.
  a fresh Pixel VM on 5G) this caused `errno 111 Connection refused`.
  The new route-aware logic tries local first with a 1-second probe
  and falls back to the resolved external URL when no local brain_api
  is reachable. (Codex Observation 2, cmail-first-cap-findings.)
- **Sealed manifest schema aligned with control plane** — the
  `aint-manifest.json` inside the TBZ envelope now reports
  `schema = aint-send-v2`, matching the I-Poll notification metadata.
  Previously the sealed object advertised v1 while the control plane
  advertised v2, creating cross-plane schema drift on every cap.
  (Codex Observation 3.)

## [0.8.1] — 2026-05-14

### Added
- **`cmail` and `aint-send` console-scripts** — `ainternet` now installs
  two additional CLI entry-points alongside the existing `ainternet`
  command:
  - `cmail <recipient>.aint "body"` — user-facing Continuity Messaging
    send. Resolves the recipient via local AINS, packs a sealed TBZ/TZA
    envelope into `/var/lib/tibet/inbox/`, and emits an I-Poll
    notification with `schema=aint-send-v2` metadata.
  - `aint-send` — protocol-purist alias of `cmail` for scripts.
- This release positions AInternet as the open network layer for
  **Continuity Messaging** — `cmail` is the human-facing shorthand
  ("email is for messages; cmail is for continuity"). Formal terminology
  remains: Continuity Messaging (category), Continuity Envelope (object),
  Continuity Envelope Protocol (draft title).

### Notes
- This release is the entry-point fix only. A schema drift between
  control-plane (`aint-send-v2`) and sealed-manifest (`aint-send-v1`)
  has been identified during the first live cmail cap on 2026-05-14
  and will be addressed in 0.8.2.

## [0.8.0] — 2026-05-02

### Added
- **UPIP Birth Bundle** — `ainternet claim <name>` now writes a local
  identity-birth bundle to `~/.ainternet/birth/<resolved_identity>.upip.birth.json`
  (chmod `0600`). The bundle follows the AInternet UPIP Birth Spec
  (Codex) with five layers: L1 STATE, L2 DEPS, L3 PROCESS, L4 RESULT,
  L5 VERIFY. The L5 layer carries a SHA256 birth hash over the canonical
  JSON of the bundle minus the hash itself, plus the public key as
  `attestation`. The CLI output now includes a `Birth proof:` line so
  users see exactly where their birth bundle landed.
- `AINSClaim.quick()` return dict now exposes `_birth_path` and
  `_birth_hash` alongside the existing `_identity_path` and
  `_session_path` keys. Best-effort: a failed birth-bundle write never
  breaks the claim itself.

### Why
The mini-slice gives every fresh `.aint` claim a local-first provenance
artifact without forcing users into Zenodo/tibet-vault flows. Sets up
later extensions (export to vault, child/guardian claim approval, buddy
persona birth events) without changing the user-visible claim flow.

## [0.7.4] — 2026-04-30

### Fixed
- `__init__.py` `__version__` now matches `pyproject.toml` (was stuck on `0.7.2`
  while the published version was `0.7.3`). Anyone reading
  `ainternet.__version__` at runtime now sees the correct release.
- Module docstring no longer claims "Pick a free name, get `mybot.aint`" —
  free claims return a unique suffixed identity such as
  `mybot-a3f9e28b.aint` and the docstring now says so explicitly.

### Changed (per AInternet Claim Copy Spec)
- `ainternet claim <name>` CLI output now always shows the *exact* `.aint`
  identity returned and explicitly labels it as **Clean identity** vs
  **Free unique identity**. Suffixed claims include guidance to use the
  returned address everywhere (Python, MCP, mobile, browser).
- The `Next steps` snippet uses the *returned* identity in
  `AInternet(agent_id=...)` instead of the requested base name, so
  copy-pasting the example from the CLI output works on the first try.

### Notes
The clean-vs-suffixed ambiguity in earlier 0.7.x output was a real source
of onboarding friction — users could believe they had `mybot.aint` while
actually being assigned `mybot-a3f9e28b.aint`. The fix is purely cosmetic
in its code footprint but unblocks the question "what address do I use
now?" for first-time claimers.

## [0.7.3] — 2026-04-29

### Added
- `ainternet claim <name>` defaults to the new instant hardware-bound
  flow (`--quick` is now implicit). The previous default — social-proof
  verification via GitHub gist or similar — is now opt-in via `--slow`.
- `claim.quick(domain=...)` method on the SDK side: posts hardware hash
  + Ed25519 public key to `/api/ainternet/claim`, returns
  `actual_domain`, `tier`, and a session token in one round-trip.
- Persists identity at `~/.ainternet/{domain}.json` and session at
  `~/.ainternet/.session.json`.

### Changed
- Onboarding-funnel friction reduced from three hops (start → verify →
  complete) to one for first-time claimers. Social-proof remains
  available for users who want a higher trust score from day one.
