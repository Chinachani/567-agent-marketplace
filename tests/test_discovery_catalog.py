import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import discovery_catalog as catalog
import sync_marketplace as sync


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mcp-catalog-v2"


def record(slug="blender-example", category="cad-3d"):
    item = sync.write_mcp_record({"slug": slug, "name": "Blender", "description": "建模工具"}, {}, {}, {})
    item["category"] = category
    item["mcpMetadata"]["runtimeMode"] = "stdio"
    return item


def manifest(records, version="2"):
    return {"marketplaceVersion": "1", "discoveryVersion": version, "discoveryAbilities": records}


class DiscoveryCatalogTests(unittest.TestCase):
    def read_checked(self, root, descriptor, limit):
        payload = (root / descriptor["path"]).read_bytes()
        self.assertLessEqual(len(payload), limit)
        self.assertEqual(len(payload), descriptor["sizeBytes"])
        self.assertEqual(hashlib.sha256(payload).hexdigest(), descriptor["sha256"])
        return json.loads(payload)

    def walk_catalog(self, root):
        index = json.loads((root / "v2/index.json").read_bytes())
        self.assertEqual(index["schemaVersion"], 2)
        self.assertLessEqual((root / "v2/index.json").stat().st_size, index["limits"]["indexBytes"])
        found, summaries, visited = {}, {}, set()
        totals = {"search": 0, "detail": 0, "pages": 0}
        for category, info in index["categories"].items():
            following = info["firstPage"]
            pages = shards = count = 0
            category_rows = []
            while following:
                self.assertNotIn(following["path"], visited)
                visited.add(following["path"])
                page = self.read_checked(root, following, index["limits"]["indexBytes"])
                totals["pages"] += following["sizeBytes"]
                self.assertEqual(page["schemaVersion"], 2)
                self.assertEqual(page["catalogVersion"], index["catalogVersion"])
                self.assertEqual(page["category"], category)
                self.assertLessEqual(len(page["entries"]), index["limits"]["pageEntries"])
                pages += 1
                for entry in page["entries"]:
                    rows = {}
                    for kind in ("search", "detail"):
                        data = self.read_checked(root, entry[kind], index["limits"]["dataBytes"])
                        totals[kind] += entry[kind]["sizeBytes"]
                        self.assertEqual(data["schemaVersion"], 2)
                        self.assertEqual(data["catalogVersion"], index["catalogVersion"])
                        self.assertEqual(data["category"], category)
                        rows[kind] = data["abilities"]
                        self.assertEqual(len(rows[kind]), entry["count"])
                        self.assertLessEqual(entry["count"], index["limits"]["dataItems"])
                    self.assertEqual([row["slug"] for row in rows["search"]], [row["slug"] for row in rows["detail"]])
                    self.assertEqual(entry["facets"], catalog.facet_counts(rows["detail"]))
                    for summary, detail in zip(rows["search"], rows["detail"]):
                        self.assertEqual(summary["detailShard"], entry["detail"]["path"])
                        self.assertEqual(summary["mcpMetadata"], detail["mcpMetadata"])
                        self.assertFalse(detail["mcpMetadata"]["installable"])
                        self.assertNotIn(detail["slug"], found)
                        found[detail["slug"]] = detail
                        summaries[summary["slug"]] = summary
                    category_rows.extend(rows["detail"])
                    shards += 1
                    count += entry["count"]
                following = page["next"]
            self.assertEqual((pages, shards, count), (info["pageCount"], info["shardCount"], info["recordCount"]))
            self.assertEqual(info["facets"], catalog.facet_counts(category_rows))
        self.assertEqual(len(found), index["recordCount"])
        self.assertEqual(totals, index["totalBytes"])
        return index, found, summaries

    def test_paginated_category_walk_verifies_every_record_and_digest(self):
        records = [record(f"item-{number}") for number in range(7)] + [record("web", "web-search")]
        records[0]["source"]["registryUpdatedAt"] = "2026-11-03"
        records[0]["mcpMetadata"]["permissionScopes"] = ["filesystem", "filesystem"]
        original = copy.deepcopy(records)
        with tempfile.TemporaryDirectory() as temp, patch.object(catalog, "DATA_ITEMS", 2), patch.object(catalog, "PAGE_ENTRIES", 2):
            root = Path(temp)
            catalog.build_paged_discovery(manifest(records), root, {"status": "current"})
            index, found, summaries = self.walk_catalog(root)
            self.assertEqual(index["categories"]["cad-3d"]["pageCount"], 2)
            self.assertEqual(index["categories"]["cad-3d"]["facets"]["permissionScopes"]["filesystem"], 1)
            self.assertEqual(set(found), {row["slug"] for row in records})
            self.assertNotIn("registryUpdatedAt", found["item-0"]["source"])
            self.assertNotIn("description", summaries["item-0"]["detail"]["i18n"]["zh"])
            self.assertEqual(summaries["item-0"]["description"], "建模工具")
        self.assertEqual(records, original)

    def test_search_and_details_both_split_at_utf8_byte_limit(self):
        records = [record(f"item-{number}") for number in range(4)]
        # A long English summary plus all filter fields can exceed a compact
        # detail payload. Both families must drive splitting independently.
        for row in records:
            row["description"] = "中文" * 300
            row["detail"]["i18n"]["en"] = {"description": "English " * 60}
        with tempfile.TemporaryDirectory() as temp, patch.object(catalog, "DATA_BYTES", 3400):
            root = Path(temp)
            catalog.build_paged_discovery(manifest(records), root, {})
            index, _, _ = self.walk_catalog(root)
            self.assertGreater(index["categories"]["cad-3d"]["shardCount"], 1)

    def test_summary_size_can_force_split_even_when_details_fit(self):
        rows = [record("first"), record("second")]
        for row in rows:
            row["source"] = {"path": "mcps/discovery"}
            row["detail"] = {}
            row.pop("categoryI18n")
        data = [catalog.compact_record(row) for row in rows]
        summaries = [catalog.search_record(row, "v2/shards/mcp-cad-3d-000000.json") for row in data]
        envelope = {"schemaVersion": 2, "catalogVersion": "2", "category": "cad-3d", "abilities": data}
        detail_bytes = len(catalog.encode(envelope))
        self.assertGreater(len(catalog.encode({**envelope, "abilities": summaries})), detail_bytes)
        with tempfile.TemporaryDirectory() as temp, patch.object(catalog, "DATA_BYTES", detail_bytes):
            root = Path(temp)
            catalog.build_paged_discovery(manifest(rows), root, {})
            index, _, _ = self.walk_catalog(root)
            self.assertEqual(index["categories"]["cad-3d"]["shardCount"], 2)

    def test_page_byte_budget_splits_before_entry_count_limit(self):
        rows = [record(f"item-{number}") for number in range(6)]
        with tempfile.TemporaryDirectory() as temp, patch.object(catalog, "DATA_ITEMS", 1), patch.object(catalog, "INDEX_BYTES", 1800):
            root = Path(temp)
            catalog.build_paged_discovery(manifest(rows), root, {})
            index, _, _ = self.walk_catalog(root)
            self.assertGreater(index["categories"]["cad-3d"]["pageCount"], 1)
            self.assertEqual(index["limits"]["pageEntries"], 64)

    def test_legacy_capacity_freezes_exact_complete_snapshot_while_v2_grows(self):
        for constant in ("DISCOVERY_MAX_RECORDS", "DISCOVERY_MAX_BYTES", "DISCOVERY_MAX_SHARDS"):
            with self.subTest(constant=constant), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                old = root / "old"
                old.mkdir()
                sync.build_discovery_distribution(manifest([record("old")], "1"), old)
                old_files = {path.relative_to(old).as_posix(): path.read_bytes() for path in old.rglob("*.json")}
                records = [record("new-one"), record("new-two")]
                with patch.object(sync, constant, 0):
                    index = sync.build_catalog_distribution(manifest(records), root / "output", old_files.__getitem__)
                self.assertEqual(index["legacy"], {"status": "frozen", "reason": "capacity-exceeded", "path": "index.json", "catalogVersion": "1", "recordCount": 1})
                for path, payload in old_files.items():
                    if path != "classification-suggestions.json":
                        self.assertEqual((root / "output" / path).read_bytes(), payload)
                _, found, _ = self.walk_catalog(root / "output")
                self.assertEqual(set(found), {"new-one", "new-two"})

    def test_normal_publication_never_reads_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            def unexpected(path):
                self.fail(f"Unexpected previous read: {path}")
            index = sync.build_catalog_distribution(manifest([record()]), Path(temp), unexpected)
            self.assertEqual(index["legacy"]["status"], "current")
            legacy = json.loads((Path(temp) / "index.json").read_bytes())
            self.assertEqual(legacy["recordCount"], index["recordCount"])
            self.walk_catalog(Path(temp))

    def test_invalid_legacy_snapshot_is_discarded_without_losing_v2(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            previous = root / "previous"
            previous.mkdir()
            sync.build_discovery_distribution(manifest([record("old")], "1"), previous)
            files = {path.relative_to(previous).as_posix(): path.read_bytes() for path in previous.rglob("*.json")}
            broken_hash = {**files, "shards/mcp-cad-3d-0000.json": b"bad"}
            bad_path_index = json.loads(files["index.json"])
            bad_path_index["shards"][0]["path"] = "../escape.json"
            bad_path = {**files, "index.json": catalog.encode(bad_path_index)}
            malformed = {"index.json": b"[]"}
            search_path = "search/mcp-cad-3d-0000.json"
            search = json.loads(files[search_path])
            search["abilities"][0]["detailShard"] = "shards/mcp-cad-3d-9999.json"
            wrong_locator = {**files, search_path: catalog.encode(search)}
            index = json.loads(files["index.json"])
            index["searchShards"][0].update(sizeBytes=len(wrong_locator[search_path]), sha256=hashlib.sha256(wrong_locator[search_path]).hexdigest())
            wrong_locator["index.json"] = catalog.encode(index)
            for number, snapshot in enumerate((broken_hash, bad_path, malformed, wrong_locator, {})):
                def reader(path):
                    if path not in snapshot:
                        raise FileNotFoundError(path)
                    return snapshot[path]
                output = root / f"output-{number}"
                with self.subTest(number=number), patch.object(sync, "DISCOVERY_MAX_RECORDS", 0):
                    result = sync.build_catalog_distribution(manifest([record()]), output, reader)
                    self.assertEqual(result["legacy"]["status"], "unavailable")
                    self.assertFalse((output / "index.json").exists())
                    self.assertFalse((output / "shards").exists())
                    self.walk_catalog(output)
            self.assertFalse((root / "escape.json").exists())

    def test_invalid_current_records_cannot_be_hidden_by_legacy_fallback(self):
        invalid = record()
        invalid["mcpMetadata"]["installable"] = True
        unknown_category = {**record(), "category": "../escape"}
        cases = [[invalid], [unknown_category], [record(), record()], [{**record(), "description": "中" * 20001}]]
        for records in cases:
            with self.subTest(records=len(records)), tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(ValueError):
                    sync.build_catalog_distribution(manifest(records), Path(temp))
                self.assertEqual(list(Path(temp).iterdir()), [])

    def test_empty_catalog_and_deterministic_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sync.build_catalog_distribution(manifest([]), root / "empty")
            self.walk_catalog(root / "empty")
            rows = [record("two"), record("one")]
            for name, records in (("first", rows), ("second", rows[::-1])):
                catalog.build_paged_discovery(manifest(records), root / name, {})
            first = {path.relative_to(root / "first"): path.read_bytes() for path in (root / "first").rglob("*.json")}
            second = {path.relative_to(root / "second"): path.read_bytes() for path in (root / "second").rglob("*.json")}
            self.assertEqual(first, second)

    def test_git_snapshot_reader_pins_revision_before_reading_files(self):
        with patch.object(subprocess, "check_output", side_effect=["a" * 40 + "\n", b"index", b"shard"]) as command:
            reader = sync.previous_catalog_reader()
            self.assertEqual(reader("index.json"), b"index")
            self.assertEqual(reader("shards/mcp-cad-3d-0000.json"), b"shard")
        self.assertEqual(command.call_count, 3)
        for call in command.call_args_list[1:]:
            self.assertTrue(call.args[0][-1].startswith("a" * 40 + ":"))

    def test_committed_fixture_is_a_complete_reproducible_contract(self):
        _, records, _ = self.walk_catalog(FIXTURE)
        with tempfile.TemporaryDirectory() as temp:
            generated = Path(temp)
            source = json.loads((FIXTURE / "input.json").read_bytes())
            catalog.build_paged_discovery(source, generated, {"status": "unavailable", "reason": "fixture-only"})
            self.assertEqual(set(records), {row["slug"] for row in source["discoveryAbilities"]})
            expected = {path.relative_to(FIXTURE): path.read_bytes() for path in (FIXTURE / "v2").rglob("*.json")}
            actual = {path.relative_to(generated): path.read_bytes() for path in generated.rglob("*.json")}
            self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
