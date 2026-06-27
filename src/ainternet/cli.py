"""
AInternet CLI
=============

Command-line interface for the AI Network.

Usage:
    ainternet init <name>             - Scaffold a new agent project
    ainternet resolve <domain>
    ainternet list
    ainternet claim <domain>          - Claim a .aint domain (interactive)
    ainternet send <to> <message> --from <agent>
    ainternet receive <agent>
    ainternet status
"""

import sys
import json
from .client import AInternet
from .claim import AINSClaim

# ── ANSI Colors ──────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
RESET = "\033[0m"
CHECK = f"{GREEN}✓{RESET}"
DIAMOND = f"{CYAN}◈{RESET}"
ARROW = f"{DIM}→{RESET}"


def _header(title: str):
    print(f"\n{CYAN}  ◈ {title}{RESET}")
    print(f"  {DIM}{'─' * 50}{RESET}")


def _trust_color(score: float) -> str:
    if score >= 0.85:
        return GREEN
    elif score >= 0.50:
        return YELLOW
    return RED


def _trust_bar(score: float, width: int = 10) -> str:
    filled = int(score * width)
    color = _trust_color(score)
    bar = f"{color}{'█' * filled}{DIM}{'░' * (width - filled)}{RESET}"
    return bar


def print_domain(domain):
    """Print domain info with colors."""
    tc = _trust_color(domain.trust_score)
    caps = ", ".join(domain.capabilities) if domain.capabilities else "none"

    print(f"\n  {BOLD}{domain.domain}{RESET}")
    print(f"  {DIM}{'─' * 40}{RESET}")
    print(f"  Agent        {domain.agent}")
    print(f"  Trust        {_trust_bar(domain.trust_score)} {tc}{domain.trust_score:.2f}{RESET}")
    print(f"  Status       {GREEN}{domain.status}{RESET}")
    print(f"  Capabilities {CYAN}{caps}{RESET}")
    print(f"  Endpoint     {DIM}{domain.endpoint}{RESET}")
    print(f"  I-Poll       {DIM}{domain.i_poll}{RESET}")


def print_message(msg):
    """Print message with colors."""
    type_colors = {
        "PUSH": CYAN, "PULL": MAGENTA,
        "TASK": YELLOW, "SYNC": GREEN, "ACK": DIM,
    }
    tc = type_colors.get(msg.poll_type.value, RESET)
    preview = msg.content[:120] + ("..." if len(msg.content) > 120 else "")

    print(f"  {tc}[{msg.poll_type.value:4}]{RESET} {BOLD}{msg.from_agent}{RESET}")
    print(f"         {preview}")
    print(f"         {DIM}id={msg.id[:16]}  status={msg.status}{RESET}")


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print(f"""
{CYAN}  ◈ AInternet CLI{RESET} {DIM}v0.7.2{RESET}
{DIM}  The AI Network — Where AIs Connect{RESET}

  {BOLD}Commands:{RESET}
    {GREEN}init{RESET} <name>                  Scaffold a new agent project
    {GREEN}resolve{RESET} <domain>             Look up a .aint domain
    {GREEN}list{RESET}                         List all registered agents
    {GREEN}discover{RESET} [--cap <cap>]       Find agents by capability
    {GREEN}claim{RESET} <domain>               Claim a .aint domain
    {GREEN}send{RESET} <to> <msg> [--from id]  Send a message
    {GREEN}receive{RESET} <agent>              Check inbox
    {GREEN}attach{RESET} <raint> --key <k>     Open your enclave (remote probe lane)
    {GREEN}status{RESET}                       Network health

  {BOLD}Quick start:{RESET}
    {DIM}${RESET} ainternet init mybot
    {DIM}${RESET} cd mybot && python agent.py

  {BOLD}Links:{RESET}
    {DIM}Docs:    https://ainternet.org/docs/{RESET}
    {DIM}Browser: https://ainternet.org/browser/{RESET}
    {DIM}PyPI:    https://pypi.org/project/ainternet/{RESET}
""")
        return

    cmd = sys.argv[1].lower()

    # ── Init (no connection needed) ──────────────────────────────
    if cmd == "init":
        if len(sys.argv) < 3:
            print(f"\n  {BOLD}Usage:{RESET} ainternet init <name> [--hub <url>] [--no-identity]")
            print(f"\n  {BOLD}Examples:{RESET}")
            print(f"    {DIM}${RESET} ainternet init mybot")
            print(f"    {DIM}${RESET} ainternet init mybot --hub https://my-hub.example.com\n")
            return

        name = sys.argv[2]
        hub = "https://api.ainternet.org"
        generate_identity = True

        if "--hub" in sys.argv:
            idx = sys.argv.index("--hub")
            if idx + 1 < len(sys.argv):
                hub = sys.argv[idx + 1]

        if "--no-identity" in sys.argv:
            generate_identity = False

        from .scaffold import init_project
        init_project(name, hub=hub, generate_identity=generate_identity)
        return

    # ── Commands that need a connection ──────────────────────────
    ai = AInternet()

    if cmd == "resolve":
        if len(sys.argv) < 3:
            print(f"  {BOLD}Usage:{RESET} ainternet resolve <domain>")
            return
        domain = ai.resolve(sys.argv[2])
        if domain:
            print_domain(domain)
        else:
            print(f"\n  {RED}✗{RESET} Domain '{sys.argv[2]}' not found")

    elif cmd == "list":
        agents = ai.list_agents()
        _header(f"AInternet — {len(agents)} agents registered")
        print()

        # Table header
        print(f"  {DIM}{'Domain':<25} {'Trust':>7}  {'Status':<10} Capabilities{RESET}")
        print(f"  {DIM}{'─' * 70}{RESET}")

        for d in agents:
            tc = _trust_color(d.trust_score)
            caps = ", ".join(d.capabilities[:3]) if d.capabilities else ""
            if len(d.capabilities) > 3:
                caps += f" +{len(d.capabilities)-3}"
            print(f"  {BOLD}{d.domain:<25}{RESET} {tc}{d.trust_score:>5.2f}{RESET}  {d.status:<10} {DIM}{caps}{RESET}")

        print()

    elif cmd == "claim":
        # Default = quick (instant) claim. Pass --slow for the social-
        # proof flow (GitHub / Twitter / LinkedIn / Mastodon channels).
        # Quick uses the same hardware-bound flow the K/IT mobile app
        # uses: generates Ed25519 keypair, posts hardware_hash + pubkey
        # to /api/ainternet/claim, gets back actual_domain + session
        # token in one round-trip. Identity persists in ~/.ainternet/.
        args = [a for a in sys.argv[2:] if a not in ("--quick", "--slow")]
        slow = "--slow" in sys.argv
        if not args:
            print(f"  {BOLD}Usage:{RESET} ainternet claim <domain> [--slow]")
            print(f"  {DIM}Default: instant hardware-bound claim (mobile-style){RESET}")
            print(f"  {DIM}--slow:  social-channel verification (GitHub/Twitter/LinkedIn/Mastodon){RESET}")
            return

        domain = args[0].replace(".aint", "")
        claim = AINSClaim()

        try:
            existing = ai.resolve(domain)
            if existing:
                print(f"\n  {YELLOW}!{RESET} {BOLD}{domain}.aint{RESET} is already registered")
                print_domain(existing)
                return
        except Exception:
            pass

        if not slow:
            _header(f"Claiming AInternet identity for \"{domain}\"")
            try:
                result = claim.quick(domain=domain)
                actual = result.get("actual_domain", f"{domain}.aint")
                tier = result.get("tier", "FREE")
                identity_path = result.get("_identity_path", "?")
                session_path = result.get("_session_path", "?")
                # Clean vs suffixed: explicit per Codex copy-spec. The user
                # must always see exactly what `.aint` address they have,
                # and whether they got the name they asked for or a
                # collision-free derivative.
                requested_clean = f"{domain.lower()}.aint"
                is_clean = actual.lower() == requested_clean
                claim_type = "Clean identity" if is_clean else "Free unique identity"
                # The agent_id used in `ai = AInternet(agent_id=...)` must
                # match the *returned* identity (without `.aint`), not the
                # *requested* one — otherwise messaging fails silently.
                agent_id = actual.removesuffix(".aint")
                print(f"\n  {CHECK} Claim complete")
                print(f"  {BOLD}Your AInternet identity:{RESET} {BOLD}{actual}{RESET}")
                print(f"  Claim type: {claim_type}")
                print(f"  Tier:       {tier}")
                print(f"  Identity:   {DIM}{identity_path}{RESET}")
                print(f"  Session:    {DIM}{session_path}{RESET}")
                birth_path = result.get("_birth_path")
                if birth_path:
                    print(f"  Birth proof: {DIM}{birth_path}{RESET}")
                if not is_clean:
                    print(f"\n  {DIM}Use this exact .aint address everywhere — Python, MCP,{RESET}")
                    print(f"  {DIM}mobile, browser. Clean names like {requested_clean} are a{RESET}")
                    print(f"  {DIM}separate assignment tier.{RESET}")
                print(f"\n  {DIAMOND} Your agent is live on the AInternet!")
                print(f"\n  {BOLD}Next steps:{RESET}")
                print(f"    {DIM}from ainternet import AInternet{RESET}")
                print(f'    {DIM}ai = AInternet(agent_id="{agent_id}"){RESET}')
                print(f'    {DIM}ai.send("echo.aint", "hi"){RESET}\n')
            except Exception as e:
                print(f"  {RED}✗{RESET} Error: {e}")
                print(f"\n  {DIM}Try --slow for social-proof verification, or check the hub URL.{RESET}")
            return

        _header(f"Claiming {domain}.aint (social proof)")
        try:
            result = claim.start(
                domain=domain,
                description=args[1] if len(args) > 1 else None,
            )
            code = result.get("verification_code", "?")
            print(f"\n  {CHECK} Claim started")
            print(f"  {BOLD}Verification code:{RESET} {CYAN}{code}{RESET}")
            print(f"\n  Post this code on any of these platforms:")

            channels = result.get("channels", [])
            for ch in channels:
                icon = ch.get("icon", "•")
                name = ch.get("name", ch.get("id", "?"))
                boost = ch.get("trust_boost", 0)
                print(f"    {icon} {name} {DIM}(+{boost:.2f} trust){RESET}")

            print(f"\n  {BOLD}Then verify:{RESET}")
            print(f"    {DIM}${RESET} ainternet verify {domain} github https://gist.github.com/you/xxx")
            print(f"\n  {BOLD}And complete:{RESET}")
            print(f"    {DIM}${RESET} ainternet complete {domain}")
            print(f"\n  {DIM}Or skip verification for instant registration (base trust):{RESET}")
            print(f"    {DIM}${RESET} ainternet complete {domain}\n")

        except Exception as e:
            print(f"  {RED}✗{RESET} Error: {e}")

    elif cmd == "verify":
        if len(sys.argv) < 5:
            print(f"  {BOLD}Usage:{RESET} ainternet verify <domain> <channel> <proof_url>")
            return

        domain = sys.argv[2].replace(".aint", "")
        channel = sys.argv[3]
        proof_url = sys.argv[4]
        claim = AINSClaim()

        try:
            result = claim.verify(domain, channel, proof_url)
            trust = result.get("trust_score", 0)
            print(f"\n  {CHECK} Channel '{channel}' verified for {BOLD}{domain}.aint{RESET}")
            print(f"  Trust score: {_trust_bar(trust)} {_trust_color(trust)}{trust:.2f}{RESET}")
            if result.get("power_user"):
                print(f"  {YELLOW}★{RESET} Power user status earned!")
        except Exception as e:
            print(f"  {RED}✗{RESET} Error: {e}")

    elif cmd == "complete":
        if len(sys.argv) < 3:
            print(f"  {BOLD}Usage:{RESET} ainternet complete <domain>")
            return

        domain = sys.argv[2].replace(".aint", "")
        claim = AINSClaim()

        try:
            result = claim.complete(domain)
            status = result.get("status", "?")
            trust = result.get("trust_score", 0)
            print(f"\n  {CHECK} {BOLD}{domain}.aint{RESET} claimed!")
            print(f"  Status: {GREEN}{status}{RESET}")
            print(f"  Trust:  {_trust_bar(trust)} {_trust_color(trust)}{trust:.2f}{RESET}")
            if result.get("resolve_url"):
                print(f"  Resolve: {DIM}{result['resolve_url']}{RESET}")
            print(f"\n  {DIAMOND} Your agent is live on the AInternet!")
            print(f"\n  {BOLD}Next steps:{RESET}")
            print(f"    {DIM}${RESET} pip install tibet-ainternet-mcp")
            print(f"    Add to MCP config:")
            print(f'    {DIM}{{"mcpServers": {{"ainternet": {{"command": "tibet-ainternet-mcp"}}}}}}{RESET}\n')
        except Exception as e:
            print(f"  {RED}✗{RESET} Error: {e}")

    elif cmd == "discover":
        cap = None
        if "--cap" in sys.argv:
            idx = sys.argv.index("--cap")
            if idx + 1 < len(sys.argv):
                cap = sys.argv[idx + 1]

        agents = ai.discover(capability=cap)
        title = f"Found {len(agents)} agents"
        if cap:
            title += f" with '{cap}'"
        _header(title)
        print()

        for d in agents:
            tc = _trust_color(d.trust_score)
            caps = ", ".join(d.capabilities) if d.capabilities else ""
            print(f"  {BOLD}{d.domain:<25}{RESET} {tc}{d.trust_score:.2f}{RESET}")
            print(f"  {DIM}  {caps}{RESET}")

        print()

    elif cmd == "send":
        if len(sys.argv) < 4:
            print(f"  {BOLD}Usage:{RESET} ainternet send <to> <message> [--from <agent>]")
            return

        to_agent = sys.argv[2]
        message = sys.argv[3]
        from_agent = "cli_user"

        if "--from" in sys.argv:
            idx = sys.argv.index("--from")
            if idx + 1 < len(sys.argv):
                from_agent = sys.argv[idx + 1]

        ai = AInternet(agent_id=from_agent)
        try:
            msg = ai.send(to_agent, message)
            print(f"\n  {CHECK} Message sent")
            print(f"  {DIM}From:{RESET} {from_agent}")
            print(f"  {DIM}To:{RESET}   {to_agent}")
            print(f"  {DIM}ID:{RESET}   {msg.id}")
            print()
        except Exception as e:
            print(f"  {RED}✗{RESET} Error: {e}")

    elif cmd == "receive":
        if len(sys.argv) < 3:
            print(f"  {BOLD}Usage:{RESET} ainternet receive <agent>")
            return

        agent_id = sys.argv[2]
        ai = AInternet(agent_id=agent_id)

        try:
            messages = ai.receive(mark_read=False)
            if messages:
                _header(f"{len(messages)} message(s) for {agent_id}")
                print()
                for msg in messages:
                    print_message(msg)
                    print()
            else:
                print(f"\n  {DIM}No pending messages for {agent_id}{RESET}\n")
        except Exception as e:
            print(f"  {RED}✗{RESET} Error: {e}")

    elif cmd == "status":
        try:
            status = ai.status()
            _header("AInternet Network Status")
            print()

            net = status.get('status', 'unknown')
            net_color = GREEN if net == 'online' else RED
            print(f"  Network     {net_color}{net}{RESET}")
            print(f"  Agents      {BOLD}{status.get('registered_agents', 'N/A')}{RESET} registered")
            print(f"  Pending     {status.get('pending_registrations', 0)} registrations")

            security = status.get('security', {})
            if security:
                print(f"\n  {BOLD}Security:{RESET}")
                for k, v in security.items():
                    icon = CHECK if v in (True, "enabled", "active") else f"{DIM}–{RESET}"
                    print(f"    {icon} {k}: {v}")

            pending = status.get('pending_by_agent', {})
            if pending:
                print(f"\n  {BOLD}Pending messages:{RESET}")
                for agent, count in pending.items():
                    print(f"    {agent}: {YELLOW}{count}{RESET}")

            print()
        except Exception as e:
            print(f"  {RED}✗{RESET} Error: {e}")

    elif cmd == "whoami":
        info = ai.whoami()
        _header("Your Identity")
        print()
        print(f"  Agent        {BOLD}{info.get('agent', '?')}{RESET}")
        print(f"  Domain       {CYAN}{info.get('domain', '?')}{RESET}")
        print(f"  Hub          {DIM}{info.get('hub', '?')}{RESET}")
        identity = info.get("identity", {})
        if identity:
            print(f"  Fingerprint  {DIM}{identity.get('fingerprint', '?')}{RESET}")
            print(f"  Public key   {DIM}{identity.get('public_key', '?')[:24]}...{RESET}")
        st = info.get("status", "")
        if st:
            print(f"  Status       {GREEN}{st}{RESET}")
        print()

    elif cmd == "attach":
        # open your enclave from anywhere: identity-gated probe lane over <hub>/arena.probe.
        from .attach import attach_remote, DEFAULT_HUB
        rest = sys.argv[2:]
        raint = next((a for a in rest if not a.startswith("--")), None)

        def _opt(flag, default=None):
            return rest[rest.index(flag) + 1] if flag in rest and rest.index(flag) + 1 < len(rest) else default
        key = _opt("--key")
        hub = _opt("--hub") or _opt("--remote") or DEFAULT_HUB
        if "--fresh" in rest:
            print(f"  {YELLOW}!{RESET} --fresh (spin up a new target) needs an arena claim first.")
            print(f"  Redeem an invite to get a session key + target, then: "
                  f"{BOLD}ainternet attach <raint> --key <key> --remote{RESET}")
            return
        if not raint or not key:
            print(f"  {RED}✗{RESET} usage: {BOLD}ainternet attach <raint> --key <key-or-hex> [--remote <hub>]{RESET}")
            print(f"  {DIM}the session key from YOUR claim opens the lane; default hub {DEFAULT_HUB}{RESET}")
            return
        return attach_remote(raint, key, hub)

    else:
        print(f"  {RED}✗{RESET} Unknown command: {cmd}")
        print(f"  Run {BOLD}ainternet{RESET} without arguments for help")


if __name__ == "__main__":
    main()
