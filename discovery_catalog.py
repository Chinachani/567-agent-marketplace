"""Bounded files for an unbounded-by-total-size MCP discovery catalog.

Paths are relative to the catalog branch root. A client pins one Git revision,
then follows hash-checked category page chains; it never needs all details to
browse or search. See docs/mcp-catalog-v2.md for the consumer contract.
"""
import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from marketplace_contract import VERSION, validate_ability
from marketplace_sync import MCP_MAIN_CATEGORIES, MCP_FUNCTION_TAGS

DATA_ITEMS = 500
DATA_BYTES = 1024 * 1024
PAGE_ENTRIES = 64
INDEX_BYTES = 256 * 1024
FACET_FIELDS = ("tags", "runtimeMode", "platforms", "permissionScopes", "authentication", "publisherType")


class DiscoveryCapacityExceeded(ValueError):
    """The legacy whole-catalog contract was exceeded, not a malformed record."""


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def write_file(root, path, payload, limit):
    if len(payload) > limit:
        raise ValueError(f"Discovery file exceeds its byte limit: {path}")
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return {"path": path, "sizeBytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def facet_counts(records):
    counts = {field: Counter() for field in FACET_FIELDS}
    for item in records:
        for field in FACET_FIELDS:
            value = item.get("tags", []) if field == "tags" else item["mcpMetadata"].get(field, "unknown")
            values = value if isinstance(value, list) else [value]
            if len(values) > 32 or any(not isinstance(entry, str) or not entry or len(entry) > 128 for entry in values):
                raise ValueError(f"Invalid discovery facet: {field}")
            for entry in set(values):
                counts[field][entry] += 1
    return {field: dict(sorted(values.items())) for field, values in counts.items()}


def compact_record(record):
    item = copy.deepcopy(record)
    item.get("source", {}).pop("registryUpdatedAt", None)
    localized = item.get("detail", {}).get("i18n", {}).get("zh", {})
    for field in ("name", "description", "tags"):
        if field in localized and localized[field] == item.get(field):
            del localized[field]
    return item


def search_record(item, detail_path):
    summary = {key: item[key] for key in (
        "type", "slug", "name", "version", "configVersion", "category", "tags", "mcpMetadata"
    )}
    for key in ("classificationSource", "categoryI18n"):
        if key in item:
            summary[key] = item[key]
    summary.update({"description": item.get("description", "")[:320], "license": "", "author": "", "icon": "",
                    "detailShard": detail_path, "detail": {"i18n": {}}})
    for locale, data in item.get("detail", {}).get("i18n", {}).items():
        if locale not in {"en", "zh"}:
            continue
        values = {"name": data.get("name", item["name"]),
                  "description": data.get("description", item.get("description", ""))[:320]}
        summary["detail"]["i18n"][locale] = {key: value for key, value in values.items() if value != summary[key]}
    return summary


def _data_envelope(version, category, records):
    return {"schemaVersion": 2, "catalogVersion": version, "category": category, "abilities": records}


def _write_data_shards(root, version, category, records):
    entries = []
    details, summaries = [], []
    base_bytes = len(encode(_data_envelope(version, category, [])))
    detail_bytes = search_bytes = base_bytes

    def paths():
        suffix = f"mcp-{category}-{len(entries):06d}.json"
        return f"v2/shards/{suffix}", f"v2/search/{suffix}"

    def flush():
        detail_path, search_path = paths()
        detail = write_file(root, detail_path, encode(_data_envelope(version, category, details)), DATA_BYTES)
        search = write_file(root, search_path, encode(_data_envelope(version, category, summaries)), DATA_BYTES)
        entries.append({"count": len(details), "facets": facet_counts(details), "detail": detail, "search": search})

    for original in records:
        item = compact_record(original)
        summary = search_record(item, paths()[0])
        item_size, summary_size = len(encode(item)), len(encode(summary))
        if base_bytes + max(item_size, summary_size) > DATA_BYTES:
            raise ValueError(f"MCP discovery record is too large to publish: {item['slug']}")
        separator = 1 if details else 0
        if details and (len(details) >= DATA_ITEMS or detail_bytes + item_size + separator > DATA_BYTES
                        or search_bytes + summary_size + separator > DATA_BYTES):
            flush()
            details, summaries = [], []
            detail_bytes = search_bytes = base_bytes
            summary = search_record(item, paths()[0])
            summary_size = len(encode(summary))
            separator = 0
        details.append(item)
        summaries.append(summary)
        detail_bytes += item_size + separator
        search_bytes += summary_size + separator
    if details:
        flush()
    return entries


def _write_page_chain(root, version, category, entries):
    # Reserve ample room for a next-page descriptor before packing. Hashes are
    # filled from tail to head, so each hop can be independently verified.
    base = {"schemaVersion": 2, "catalogVersion": version, "category": category, "entries": [], "next": None}
    overhead = len(encode(base)) + 256
    groups, current = [], []
    size = overhead
    for entry in entries:
        addition = len(encode(entry)) + (1 if current else 0)
        if overhead + len(encode(entry)) > INDEX_BYTES:
            raise ValueError("Discovery page entry exceeds index byte limit")
        if current and (len(current) >= PAGE_ENTRIES or size + addition > INDEX_BYTES):
            groups.append(current)
            current, size = [], overhead
            addition = len(encode(entry))
        current.append(entry)
        size += addition
    if current:
        groups.append(current)
    following = None
    total_bytes = 0
    for number in reversed(range(len(groups))):
        payload = encode({**base, "entries": groups[number], "next": following})
        following = write_file(root, f"v2/pages/{category}/{number:06d}.json", payload, INDEX_BYTES)
        total_bytes += len(payload)
    return following, len(groups), total_bytes


def validate_discovery_manifest(manifest):
    """Validate before constructing any path, including the legacy output."""
    for key in ("discoveryVersion", "marketplaceVersion"):
        if not isinstance(manifest.get(key), str) or not VERSION.fullmatch(manifest[key]):
            raise ValueError(f"Invalid discovery {key}")
    groups = {}
    identities = set()
    records = manifest.get("discoveryAbilities", [])
    if not isinstance(records, list):
        raise ValueError("Invalid discovery records")
    for item in records:
        validate_ability(item)
        metadata = item.get("mcpMetadata")
        if item["type"] != "mcp" or not isinstance(metadata, dict) or metadata.get("installable") is not False:
            raise ValueError("Discovery records must be browse-only MCPs")
        for field in FACET_FIELDS[1:]:
            value = metadata.get(field)
            if field in {"platforms", "permissionScopes"}:
                if not isinstance(value, list) or not value:
                    raise ValueError(f"Invalid MCP metadata: {field}")
            elif not isinstance(value, str):
                raise ValueError(f"Invalid MCP metadata: {field}")
        if "configVersion" not in item or "tags" not in item:
            raise ValueError("Missing discovery presentation fields")
        if item["slug"] in identities:
            raise ValueError("Duplicate discovery slug")
        identities.add(item["slug"])
        category = item.get("category")
        if (category not in MCP_MAIN_CATEGORIES or len(item["tags"]) > 3
                or any(tag not in MCP_FUNCTION_TAGS for tag in item["tags"])):
            raise ValueError("Uncontrolled discovery classification")
        if "classificationSource" in item and item["classificationSource"] not in {"automatic", "maintainer"}:
            raise ValueError("Invalid discovery classification source")
        groups.setdefault(category, []).append(item)
    return groups


def build_paged_discovery(manifest, output_dir: Path, legacy: dict):
    """Publish every valid discovery record; only individual files are bounded."""
    groups = validate_discovery_manifest(manifest)
    version = manifest["discoveryVersion"]
    categories = {}
    total_bytes = {"search": 0, "detail": 0, "pages": 0}
    for category, records in sorted(groups.items()):
        records = sorted(records, key=lambda row: row["slug"])
        entries = _write_data_shards(output_dir, version, category, records)
        first_page, page_count, page_bytes = _write_page_chain(output_dir, version, category, entries)
        categories[category] = {"recordCount": len(records), "facets": facet_counts(records),
                                "pageCount": page_count, "shardCount": len(entries), "firstPage": first_page}
        total_bytes["pages"] += page_bytes
        for kind in ("search", "detail"):
            total_bytes[kind] += sum(entry[kind]["sizeBytes"] for entry in entries)
    index = {"schemaVersion": 2, "catalogVersion": version, "marketplaceVersion": manifest["marketplaceVersion"],
             "recordCount": sum(len(records) for records in groups.values()), "categories": categories, "totalBytes": total_bytes,
             "limits": {"dataItems": DATA_ITEMS, "dataBytes": DATA_BYTES, "pageEntries": PAGE_ENTRIES, "indexBytes": INDEX_BYTES},
             "legacy": legacy}
    write_file(output_dir, "v2/index.json", encode(index), INDEX_BYTES)
    return index


def preserve_legacy_snapshot(read_file, output_dir: Path):
    """Copy a verified, whole v1 snapshot. Never manufacture a truncated catalog.

    read_file returns bytes from one pinned Git revision (or a fixture). Files
    are copied into a staging directory; the caller discards it on any failure.
    """
    index_bytes = read_file("index.json")
    if len(index_bytes) > INDEX_BYTES:
        raise ValueError("Legacy index exceeds byte limit")
    index = json.loads(index_bytes)
    if (not isinstance(index, dict) or index.get("schemaVersion") != 1
            or not isinstance(index.get("catalogVersion"), str) or not VERSION.fullmatch(index["catalogVersion"])
            or not isinstance(index.get("marketplaceVersion"), str) or not VERSION.fullmatch(index["marketplaceVersion"])):
        raise ValueError("Invalid legacy index version")
    count = index.get("recordCount")
    if type(count) is not int or not 0 <= count <= 100_000:
        raise ValueError("Invalid legacy count")
    categories = index.get("categories")
    if not isinstance(categories, dict) or any(category not in MCP_MAIN_CATEGORIES or type(value) is not int
                                              or value <= 0 for category, value in categories.items()):
        raise ValueError("Invalid legacy categories")
    detail_locations = {}
    for field, prefix in (("shards", "shards"), ("searchShards", "search")):
        if field == "searchShards" and field not in index:
            continue
        descriptors = index.get(field)
        if not isinstance(descriptors, list) or len(descriptors) > 250:
            raise ValueError("Invalid legacy shards")
        paths, hashes, identities = set(), set(), set()
        counts, total_bytes = Counter(), 0
        for shard in descriptors:
            if not isinstance(shard, dict):
                raise ValueError("Invalid legacy shard descriptor")
            category = shard.get("category")
            path = shard.get("path", "")
            if (not isinstance(category, str) or category not in categories or not isinstance(path, str)
                    or not re.fullmatch(rf"{prefix}/mcp-{re.escape(category)}-[0-9]{{4,6}}\.json", path) or path in paths):
                raise ValueError("Invalid legacy shard path")
            size, item_count = shard.get("sizeBytes"), shard.get("count")
            if type(size) is not int or not 0 < size <= 1024 * 1024 or type(item_count) is not int or not 0 < item_count <= 500:
                raise ValueError("Invalid legacy shard bounds")
            total_bytes += size
            if total_bytes > 100 * 1024 * 1024:
                raise ValueError("Legacy snapshot exceeds byte capacity")
            payload = read_file(path)
            if len(payload) != size or hashlib.sha256(payload).hexdigest() != shard.get("sha256"):
                raise ValueError("Legacy shard integrity mismatch")
            if shard["sha256"] in hashes:
                raise ValueError("Duplicate legacy shard digest")
            hashes.add(shard["sha256"])
            body = json.loads(payload)
            if (not isinstance(body, dict) or body.get("schemaVersion") != 1 or body.get("catalogVersion") != index["catalogVersion"]
                    or body.get("category") != category or not isinstance(body.get("abilities"), list)
                    or len(body["abilities"]) != item_count):
                raise ValueError("Legacy shard envelope mismatch")
            for row in body["abilities"]:
                if not isinstance(row, dict) or not isinstance(row.get("mcpMetadata"), dict):
                    raise ValueError("Invalid legacy discovery record")
                if any(field not in row for field in ("description", "configVersion", "license", "author", "category", "tags", "detail")):
                    raise ValueError("Missing legacy presentation fields")
                validate_ability(row if prefix == "shards" else {**row, "source": {"path": "mcps/discovery"}})
                if (row["type"] != "mcp" or row.get("mcpMetadata", {}).get("installable") is not False
                        or row.get("category") != category or row["slug"] in identities):
                    raise ValueError("Invalid legacy discovery record")
                if prefix == "shards":
                    detail_locations[row["slug"]] = (path, row["version"], category)
                elif detail_locations.get(row["slug"]) != (row.get("detailShard"), row["version"], category):
                    raise ValueError("Legacy search/detail identity mismatch")
                identities.add(row["slug"])
            paths.add(path)
            counts[category] += item_count
            write_file(output_dir, path, payload, DATA_BYTES)
        if sum(counts.values()) != count or counts != Counter(categories):
            raise ValueError("Legacy category/count mismatch")
    write_file(output_dir, "index.json", index_bytes, INDEX_BYTES)
    return index
