"""Publisher boundary shared by package manifests and browse-only discovery records.

The fixture is also validated with the desktop Zod schemas. Rejected fields are
reported by name only: upstream input can contain credentials or terminal codes.
"""
import re
from pathlib import PurePosixPath

SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def validate_ability(item):
    if not isinstance(item, dict) or item.get("type") not in {"skill", "mcp"}:
        raise ValueError("unsupported ability type")
    for field, pattern in (("slug", SLUG), ("version", VERSION)):
        if not isinstance(item.get(field), str) or not pattern.fullmatch(item[field]):
            raise ValueError(f"invalid {field}")
    limits = {"name": 512, "description": 20000, "license": 256,
              "author": 512, "icon": 2048, "category": 128}
    for field, limit in limits.items():
        value = item.get(field, "")
        if not isinstance(value, str) or len(value) > limit or (field == "name" and not value):
            raise ValueError(f"invalid {field}")
    version = item.get("configVersion", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError("invalid configVersion")
    tags = item.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 16 or any(not isinstance(tag, str) or len(tag) > 128 for tag in tags):
        raise ValueError("invalid tags")
    labels = item.get("categoryI18n", {})
    if not isinstance(labels, dict) or any(not isinstance(value, str) for value in labels.values()):
        raise ValueError("invalid categoryI18n")
    source = item.get("source", {})
    path = source.get("path") if isinstance(source, dict) else None
    if not isinstance(path, str) or not path or "\\" in path or "\0" in path or ":" in path or path.startswith("/") or ".." in PurePosixPath(path).parts:
        raise ValueError("invalid source.path")
    if item["type"] == "mcp" and "config" in item:
        raise ValueError("MCP config belongs in mcp.json")
    detail = item.get("detail", {})
    if not isinstance(detail, dict):
        raise ValueError("invalid detail")
    locales = detail.get("i18n", {})
    if not isinstance(locales, dict):
        raise ValueError("invalid detail.i18n")
    for locale in [detail, *locales.values()]:
        if not isinstance(locale, dict):
            raise ValueError("invalid detail locale")
        for field in ("name", "description", "content"):
            if field in locale and not isinstance(locale[field], str):
                raise ValueError(f"invalid detail.{field}")
        meta = locale.get("meta", [])
        if not isinstance(meta, list):
            raise ValueError("invalid detail.meta")
        for link in meta:
            if not isinstance(link, dict) or not isinstance(link.get("value"), str) or not link["value"]:
                raise ValueError("invalid detail.meta entry")
            if "key" in link and link["key"] not in {"homepage", "repository", "docs", "license"}:
                raise ValueError("invalid detail.meta key")
        # Generated records do not emit rich presentation blocks/showcases.
        if locale.get("blocks") or locale.get("showcases"):
            raise ValueError("unsupported generated presentation blocks")
    return item


def validate_manifest(manifest):
    if manifest.get("schemaVersion") != 3:
        raise ValueError("invalid schemaVersion")
    for field in ("name", "marketplaceVersion", "minAppVersion", "repository"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise ValueError(f"invalid manifest {field}")
    if not VERSION.fullmatch(manifest["marketplaceVersion"]) or not SLUG.fullmatch(manifest["name"]):
        raise ValueError("invalid manifest identity")
    if not re.fullmatch(r"\d+\.\d+\.\d+", manifest["minAppVersion"]):
        raise ValueError("invalid minAppVersion")
    if not manifest["repository"].startswith("https://github.com/"):
        raise ValueError("invalid repository")
    seen = set()
    for item in manifest.get("abilities", []):
        validate_ability(item)
        if item["slug"] in seen:
            raise ValueError("duplicate ability slug")
        seen.add(item["slug"])
