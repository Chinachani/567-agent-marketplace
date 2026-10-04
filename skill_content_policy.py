"""Conservative distribution checks; not a promise that a skill is safe."""
import ipaddress
import re
from pathlib import Path

# Report rule identifiers, never matching values (including into CI logs).
KEY_PATTERN = re.compile(r"\b(?:cztei_[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{32,})\b")
HTTP_HOST = re.compile(r"http://(\d{1,3}(?:\.\d{1,3}){3})(?=[:/\s\"']|$)")
REMOTE_HEARTBEAT = re.compile(r"fetch\s+[^\n]{0,100}heartbeat\.md[^\n]{0,100}(?:follow|obey|execute)", re.I)


def scan_skill_tree(root: Path):
    findings = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            findings.append((path.relative_to(root).as_posix(), "symlink"))
            continue
        if not path.is_file():
            continue
        if path.stat().st_size > 10 * 1024 * 1024:
            findings.append((path.relative_to(root).as_posix(), "oversized-content"))
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        rules = set()
        if KEY_PATTERN.search(text):
            rules.add("credential-literal")
        if REMOTE_HEARTBEAT.search(text):
            rules.add("remote-heartbeat-instructions")
        for match in HTTP_HOST.finditer(text):
            try:
                if ipaddress.ip_address(match[1]).is_global:
                    rules.add("plaintext-ip-endpoint")
            except ValueError:
                rules.add("invalid-ip-endpoint")
        findings.extend((path.relative_to(root).as_posix(), rule) for rule in sorted(rules))
    return findings


def redistribution_allowed(item, root: Path):
    # Legacy source has no repository license. An old MIT label is not evidence.
    source = item.get("source", {}).get("repository", "")
    if source in {"anbeime/skill", "https://github.com/anbeime/skill"} or item.get("author") == "anbeime / 567 Agent":
        return False
    return not scan_skill_tree(root)
