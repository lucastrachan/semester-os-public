"""Download the Hipo university-domains-list (MIT licence) and write
backend/data/us_schools.json, keyed by root .edu domain (last two labels).

Attribution: Hipo/university-domains-list, https://github.com/Hipo/university-domains-list
Licence: MIT
Run: python scripts/build_school_registry.py
"""
import json
import os
import urllib.request

URL = "https://raw.githubusercontent.com/Hipo/university-domains-list/master/world_universities_and_domains.json"
OUT = os.path.join(os.path.dirname(__file__), "..", "backend", "data", "us_schools.json")


def edu_root(domain: str) -> str | None:
    parts = domain.lower().strip().rstrip(".").split(".")
    if not parts or parts[-1] != "edu":
        return None
    return ".".join(parts[-2:]) if len(parts) >= 2 else None


def main():
    print("Downloading Hipo university dataset…")
    req = urllib.request.Request(URL, headers={"User-Agent": "SemesterOS-SchoolRegistry/1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    print(f"  {len(data)} institutions total")

    registry: dict[str, dict] = {}
    for school in data:
        if school.get("alpha_two_code") != "US":
            continue
        name = (school.get("name") or "").strip()
        domains = [d.strip().lower() for d in school.get("domains", []) if d.strip()]
        web_pages = school.get("web_pages") or []
        edu_domains = [d for d in domains if edu_root(d)]
        if not edu_domains:
            continue
        for d in edu_domains:
            root = edu_root(d)
            if root and root not in registry:
                registry[root] = {
                    "name": name,
                    "domains": edu_domains,
                    "webPage": web_pages[0] if web_pages else None,
                }

    out_path = os.path.normpath(OUT)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False, sort_keys=True)
    print(f"  Wrote {len(registry)} schools -> {out_path}")


if __name__ == "__main__":
    main()
