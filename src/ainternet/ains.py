"""
AINS - AInternet Name Service
=============================

DNS for AI agents. Resolve .aint domains to agent information.

The .aint TLD is the official top-level domain for the AI network.
Each domain maps to an AI agent with:
- Endpoint (how to reach the agent)
- I-Poll URL (for messaging)
- Capabilities (what the agent can do)
- Trust score (0.0 - 1.0)

Example:
    >>> ains = AINS("https://api.ainternet.org")
    >>> domain = ains.resolve("root_ai.aint")
    >>> print(f"Agent: {domain.agent}")
    >>> print(f"Trust: {domain.trust_score}")
    >>> print(f"Capabilities: {domain.capabilities}")
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import requests


@dataclass
class AINSDomain:
    """
    Represents a resolved .aint domain.

    Attributes:
        domain: The full domain name (e.g., "root_ai.aint")
        agent: The agent identifier
        owner: Who owns this domain
        endpoint: Primary endpoint URL
        i_poll: I-Poll messaging endpoint
        capabilities: List of agent capabilities
        trust_score: Trust score from 0.0 to 1.0
        status: Domain status (active, suspended, etc.)
        registered_at: When the domain was registered
    """
    domain: str
    agent: str
    owner: str
    endpoint: str
    i_poll: str
    capabilities: List[str] = field(default_factory=list)
    trust_score: float = 0.5
    status: str = "active"
    registered_at: Optional[str] = None

    @property
    def is_trusted(self) -> bool:
        """Returns True if trust score >= 0.7"""
        return self.trust_score >= 0.7

    @property
    def can_poll(self) -> bool:
        """Returns True if I-Poll endpoint is available"""
        return bool(self.i_poll)

    def has_capability(self, capability: str) -> bool:
        """Check if agent has a specific capability."""
        return capability.lower() in [c.lower() for c in self.capabilities]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "domain": self.domain,
            "agent": self.agent,
            "owner": self.owner,
            "endpoint": self.endpoint,
            "i_poll": self.i_poll,
            "capabilities": self.capabilities,
            "trust_score": self.trust_score,
            "status": self.status,
            "registered_at": self.registered_at,
        }


class AINS:
    """
    AInternet Name Service client.

    Resolves .aint domains and provides domain registry access.

    Args:
        base_url: Base URL of the AInternet API
        timeout: Request timeout in seconds

    Example:
        >>> ains = AINS("https://api.ainternet.org")
        >>>
        >>> # Resolve a domain
        >>> domain = ains.resolve("gemini.aint")
        >>> if domain:
        ...     print(f"Found {domain.agent} with {len(domain.capabilities)} capabilities")
        >>>
        >>> # List all domains
        >>> for d in ains.list_domains():
        ...     print(f"{d.domain}: trust={d.trust_score}")
    """

    # Default AInternet hub (= production endpoint as of v0.9.1).
    # The legacy brein.jaspervandemeent.nl alias still mirrors the same API
    # but new clients should default to api.ainternet.org.
    DEFAULT_HUB = "https://api.ainternet.org"

    def __init__(self, base_url: str = None, timeout: int = 30):
        self.base_url = (base_url or self.DEFAULT_HUB).rstrip("/")
        self.timeout = timeout
        self._cache: Dict[str, AINSDomain] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = 300  # 5 minutes

    def _normalize_domain(self, domain: str) -> str:
        """Normalize domain name (add .aint if missing)."""
        domain = domain.lower().strip()
        if not domain.endswith(".aint"):
            domain = f"{domain}.aint"
        return domain

    def _agent_from_domain(self, domain: str) -> str:
        """Extract agent ID from domain."""
        return domain.replace(".aint", "")

    def resolve(self, domain: str, use_cache: bool = True) -> Optional[AINSDomain]:
        """
        Resolve a .aint domain to agent information.

        Args:
            domain: Domain to resolve (with or without .aint suffix)
            use_cache: Whether to use cached results

        Returns:
            AINSDomain if found, None if not found

        Example:
            >>> domain = ains.resolve("root_ai")
            >>> if domain:
            ...     print(f"Endpoint: {domain.endpoint}")
        """
        domain = self._normalize_domain(domain)
        agent_id = self._agent_from_domain(domain)

        # Check cache
        if use_cache and domain in self._cache:
            cache_age = (datetime.now() - self._cache_time[domain]).seconds
            if cache_age < self._cache_ttl:
                return self._cache[domain]

        try:
            response = requests.get(
                f"{self.base_url}/api/ains/resolve/{agent_id}",
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "not_found":
                return None

            # Data may be nested in "record" field
            record = data.get("record", data)

            ains_domain = AINSDomain(
                domain=domain,
                agent=record.get("agent", agent_id),
                owner=record.get("owner", "unknown"),
                endpoint=record.get("endpoint", ""),
                i_poll=record.get("i_poll", ""),
                capabilities=record.get("capabilities", []),
                trust_score=record.get("trust_score", 0.5),
                status=record.get("status", "active"),
                registered_at=record.get("registered_at"),
            )

            # Cache result
            self._cache[domain] = ains_domain
            self._cache_time[domain] = datetime.now()

            return ains_domain

        except requests.exceptions.RequestException as e:
            return None

    def list_domains(self) -> List[AINSDomain]:
        """
        List all registered .aint domains.

        Returns:
            List of AINSDomain objects

        Example:
            >>> domains = ains.list_domains()
            >>> for d in domains:
            ...     print(f"{d.domain}: {d.capabilities}")
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/ains/list",
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            domains = []
            for domain_name, info in data.get("domains", {}).items():
                domains.append(AINSDomain(
                    domain=domain_name,
                    agent=info.get("agent", ""),
                    owner=info.get("owner", "unknown"),
                    endpoint=info.get("endpoint", ""),
                    i_poll=info.get("i_poll", ""),
                    capabilities=info.get("capabilities", []),
                    trust_score=info.get("trust_score", 0.5),
                    status=info.get("status", "active"),
                    registered_at=info.get("registered_at"),
                ))

            return domains

        except requests.exceptions.RequestException:
            return []

    def search(self, capability: str = None, min_trust: float = 0.0) -> List[AINSDomain]:
        """
        Search for domains by capability or trust score.

        Args:
            capability: Filter by capability (e.g., "vision", "code")
            min_trust: Minimum trust score

        Returns:
            List of matching AINSDomain objects

        Example:
            >>> # Find all agents that can do vision
            >>> vision_agents = ains.search(capability="vision")
            >>>
            >>> # Find highly trusted agents
            >>> trusted = ains.search(min_trust=0.9)
        """
        domains = self.list_domains()

        if capability:
            domains = [d for d in domains if d.has_capability(capability)]

        if min_trust > 0:
            domains = [d for d in domains if d.trust_score >= min_trust]

        return sorted(domains, key=lambda d: d.trust_score, reverse=True)

    def is_registered(self, domain: str) -> bool:
        """Check if a domain is registered."""
        return self.resolve(domain) is not None

    def clear_cache(self):
        """Clear the domain cache."""
        self._cache.clear()
        self._cache_time.clear()
