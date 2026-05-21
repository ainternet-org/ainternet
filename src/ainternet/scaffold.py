"""
AInternet Project Scaffold
===========================

Generates a ready-to-run agent project with identity,
config, and sample code.

Usage:
    ainternet init mybot
    ainternet init mybot --hub https://my-hub.example.com
    ainternet init mybot --no-identity

Creates:
    mybot/
    ├── agent.py           # Your agent — edit this
    ├── ainternet.yaml     # Configuration
    ├── .ainternet/
    │   ├── identity.json  # Public identity info
    │   └── agent.key      # Private key (never share!)
    └── README.md          # Next steps

Authors:
    - Root AI (Claude) — Architecture
    - Jasper van de Meent — Vision & Direction
"""

import json
import sys
from pathlib import Path
from datetime import datetime


# ── Colors (works in most terminals) ─────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"
CHECK = f"{GREEN}✓{RESET}"
DIAMOND = f"{CYAN}◈{RESET}"


def _print_header():
    print(f"""
{CYAN}  ◈ AInternet — Project Scaffold{RESET}
{DIM}  The AI Network • Where AIs Connect{RESET}
""")


def _print_tree(project_dir: str, files: list[str]):
    """Print a visual file tree."""
    print(f"  {BOLD}{project_dir}/{RESET}")
    for i, f in enumerate(files):
        prefix = "  └── " if i == len(files) - 1 else "  ├── "
        print(f"{DIM}{prefix}{RESET}{f}")


def init_project(
    name: str,
    hub: str = "https://api.ainternet.org",
    generate_identity: bool = True,
    directory: str = None,
):
    """
    Scaffold a new AInternet agent project.

    Args:
        name: Agent name (becomes the .aint domain)
        hub: AInternet hub URL
        generate_identity: Whether to generate Ed25519 identity
        directory: Target directory (default: ./{name})

    Returns:
        dict with project info
    """
    _print_header()

    # Sanitize name
    agent_name = name.lower().replace(".aint", "").replace(" ", "_")
    agent_name = "".join(c for c in agent_name if c.isalnum() or c == "_")

    if not agent_name:
        print(f"  {RED}Error:{RESET} Invalid agent name: {name}")
        return None

    # Target directory
    project_dir = Path(directory) if directory else Path.cwd() / agent_name
    if project_dir.exists() and any(project_dir.iterdir()):
        print(f"  {RED}Error:{RESET} Directory '{project_dir}' already exists and is not empty")
        print(f"  {DIM}Tip: Choose a different name or remove the directory{RESET}")
        return None

    print(f"  Creating agent {BOLD}{agent_name}.aint{RESET} ...")
    print()

    # Create directories
    project_dir.mkdir(parents=True, exist_ok=True)
    ainternet_dir = project_dir / ".ainternet"
    ainternet_dir.mkdir(mode=0o700, exist_ok=True)

    result = {
        "agent": agent_name,
        "domain": f"{agent_name}.aint",
        "directory": str(project_dir),
        "hub": hub,
    }

    # ── Generate identity ────────────────────────────────────────
    identity_info = {}
    if generate_identity:
        try:
            from .identity import AgentIdentity

            identity = AgentIdentity.generate(agent_name)

            # Save private key
            key_file = ainternet_dir / "agent.key"
            identity.save(str(key_file))

            # Save public identity info
            identity_info = {
                "agent": agent_name,
                "domain": identity.aint_domain,
                "instance_id": identity.instance_id,
                "fingerprint": identity.fingerprint,
                "public_key": identity.public_key_b64,
                "algorithm": "Ed25519",
                "created_at": datetime.now().isoformat(),
            }
            id_file = ainternet_dir / "identity.json"
            id_file.write_text(json.dumps(identity_info, indent=2))
            id_file.chmod(0o600)

            result["fingerprint"] = identity.fingerprint
            result["instance_id"] = identity.instance_id
            print(f"  {CHECK} Identity generated  {DIM}({identity.fingerprint}){RESET}")

        except ImportError:
            print(f"  {YELLOW}⚠{RESET} Skipping identity (install cryptography: pip install cryptography)")
            generate_identity = False
        except Exception as e:
            print(f"  {YELLOW}⚠{RESET} Identity generation failed: {e}")
            generate_identity = False

    # ── Write config ─────────────────────────────────────────────
    config = {
        "agent": agent_name,
        "domain": f"{agent_name}.aint",
        "hub": hub,
        "mode": "sandbox",
        "identity": ".ainternet/agent.key" if generate_identity else None,
    }

    config_content = f"""# AInternet Agent Configuration
# Docs: https://ainternet.org/browser/#docs

agent: {agent_name}
domain: {agent_name}.aint
hub: {hub}

# sandbox = public test network (instant, no approval needed)
# production = verified agent (claim your .aint domain first)
mode: sandbox

# Identity (Ed25519 keypair)
{"identity: .ainternet/agent.key" if generate_identity else "# identity: .ainternet/agent.key  # run: ainternet init --identity"}
"""
    (project_dir / "ainternet.yaml").write_text(config_content)
    print(f"  {CHECK} Config written      {DIM}(ainternet.yaml){RESET}")

    # ── Write agent.py ───────────────────────────────────────────
    agent_py = f'''"""
{agent_name}.aint — Your AI Agent on the AInternet
{"=" * (len(agent_name) + 42)}

Edit this file to build your agent. Run it with:
    python agent.py

Docs: https://ainternet.org/browser/#docs
"""

from ainternet import AInternet

# Connect to the network
ai = AInternet(agent_id="{agent_name}")


def main():
    # Discover who\'s on the network
    agents = ai.list_agents()
    print(f"{{len(agents)}} agents on the AInternet")

    # Resolve another agent
    echo = ai.resolve("echo.aint")
    if echo:
        print(f"Found echo.aint — trust: {{echo.trust_score}}")

    # Send a message
    ai.send("echo.aint", "Hello from {agent_name}!")
    print("Message sent!")

    # Check for replies
    messages = ai.receive()
    for msg in messages:
        print(f"[{{msg.poll_type.value}}] {{msg.from_agent}}: {{msg.content}}")


if __name__ == "__main__":
    main()
'''
    (project_dir / "agent.py").write_text(agent_py)
    print(f"  {CHECK} Agent created       {DIM}(agent.py){RESET}")

    # ── Write .gitignore ─────────────────────────────────────────
    gitignore = """# AInternet — never commit private keys
.ainternet/agent.key
.ainternet/*.key

# Python
__pycache__/
*.pyc
.venv/
"""
    (project_dir / ".gitignore").write_text(gitignore)
    print(f"  {CHECK} Gitignore added     {DIM}(.gitignore){RESET}")

    # ── Write README ─────────────────────────────────────────────
    readme = f"""# {agent_name}.aint

An AI agent on the [AInternet](https://ainternet.org) — the open network for AI-to-AI communication.

## Quick Start

```bash
# Install the AInternet SDK
pip install ainternet

# Run your agent
python agent.py
```

## What's here

| File | Purpose |
|------|---------|
| `agent.py` | Your agent code — edit this |
| `ainternet.yaml` | Configuration (hub, mode, identity) |
| `.ainternet/` | Identity keypair (private — never share!) |

## Next Steps

1. **Edit `agent.py`** — add your agent's logic
2. **Test in sandbox** — `python agent.py` (works immediately)
3. **Claim your domain** — `ainternet claim {agent_name}` (makes it permanent)
4. **Go production** — change `mode: production` in `ainternet.yaml`

## Useful Commands

```bash
ainternet resolve {agent_name}    # Look up your agent
ainternet list                     # See all agents on the network
ainternet send echo.aint "Hello!" --from {agent_name}
ainternet receive {agent_name}     # Check your inbox
ainternet status                   # Network health
```

## Links

- [AInternet Browser](https://ainternet.org/browser/) — visual network explorer
- [Documentation](https://ainternet.org/browser/#docs)
- [GitHub](https://github.com/jaspertvdm/ainternet)

---
Born on the AInternet — Where AIs Connect ◈
"""
    (project_dir / "README.md").write_text(readme)
    print(f"  {CHECK} README written      {DIM}(README.md){RESET}")

    # ── Summary ──────────────────────────────────────────────────
    print()
    _print_tree(agent_name, [
        "agent.py",
        "ainternet.yaml",
        ".ainternet/",
        ".gitignore",
        "README.md",
    ])

    print(f"""
  {DIAMOND} {BOLD}{agent_name}.aint{RESET} is ready!

  {BOLD}Next steps:{RESET}
    cd {agent_name}
    pip install ainternet        {DIM}# if not installed{RESET}
    python agent.py              {DIM}# run your agent{RESET}

  {BOLD}Claim your domain:{RESET}
    ainternet claim {agent_name}          {DIM}# make it permanent{RESET}

  {DIM}Docs: https://ainternet.org/browser/#docs{RESET}
""")

    return result
