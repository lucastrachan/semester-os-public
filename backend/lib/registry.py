"""US school registry (Hipo/university-domains-list, MIT licence).
Lookup is by root .edu domain: students.x.edu -> x.edu.
The JSON is loaded once (Lambda warm start) and treated as read-only.
"""
import json
import os

_DATA = os.path.join(os.path.dirname(__file__), "..", "data", "us_schools.json")
_registry: dict | None = None


def _load() -> dict:
    global _registry
    if _registry is None:
        with open(_DATA, encoding="utf-8") as f:
            _registry = json.load(f)
    return _registry


def edu_root(domain: str) -> str | None:
    """Return the registrable .edu domain, or None if domain is not .edu.
    students.x.edu -> x.edu"""
    parts = domain.lower().strip().rstrip(".").split(".")
    if not parts or parts[-1] != "edu":
        return None
    return ".".join(parts[-2:]) if len(parts) >= 2 else None


def is_edu(domain: str) -> bool:
    return edu_root(domain) is not None


def lookup(domain: str) -> dict | None:
    """Return {name, domains, webPage} for an .edu domain root, or None."""
    root = edu_root(domain)
    if not root:
        return None
    return _load().get(root)
