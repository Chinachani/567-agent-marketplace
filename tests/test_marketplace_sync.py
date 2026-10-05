import hashlib
import gzip
import tempfile
import unittest
import subprocess
import json
from unittest.mock import patch
from datetime import date
from pathlib import Path

from marketplace_sync import (
    classify_skill,
    copy_skill_resources,
    next_marketplace_version,
    parse_frontmatter,
    render_skill_document,
    package_digest,
    publish_staged_paths,
    skill_files,
    SKILL_SOURCES,
    unique_slug,
)
import sync_marketplace


class MarketplaceSyncTests(unittest.TestCase):
    def setUp(self):
        sync_marketplace.TRANSLATION_CACHE.clear()

    def test_translation_retry_respects_retry_after_header(self):
        error = sync_marketplace.urllib.error.HTTPError(
            "https://api.example.test/chat/completions",
            503,
            "Service Unavailable",
            {"Retry-After": "7"},
            None,
        )
        self.assertEqual(sync_marketplace._translation_retry_delay(error, 0), 7.0)

    def test_manifest_serializer_keeps_entries_compact_and_round_trips(self):
        manifest = {
            "schemaVersion": 3,
            "name": "test",
            "abilities": [
                {"type": "mcp", "slug": "first", "detail": {"i18n": {"en": {"name": "First"}}}},
                {"type": "skill", "slug": "second"},
            ],
        }
        serialized = sync_marketplace.serialize_manifest(manifest)
        self.assertEqual(json.loads(serialized), manifest)
        self.assertIn('    {"type":"mcp","slug":"first"', serialized)
        self.assertLess(len(serialized.encode()), len(json.dumps(manifest, indent=2, ensure_ascii=False).encode()))

    def test_manifest_serializer_rejects_files_over_safe_push_limit(self):
        with patch.object(sync_marketplace, "MAX_MANIFEST_BYTES", 10):
            with self.assertRaisesRegex(ValueError, "Shard the discovery catalog"):
                sync_marketplace.serialize_manifest({"schemaVersion": 3, "abilities": [{"slug": "too-large"}]})

    def test_frontmatter_reads_folded_description(self):
        fields, body = parse_frontmatter(
            "---\nname: example\ndescription: >-\n  A useful first line\n  with a continuation.\nversion: 2.0\n---\n# Body\n"
        )
        self.assertEqual(fields["description"], "A useful first line with a continuation.")
        self.assertEqual(fields["version"], "2.0")
        self.assertIn("# Body", body)

    def test_skill_discovery_keeps_github_plugin_skills_and_skips_hidden_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "skills" / "visible").mkdir(parents=True)
            (root / ".github" / "plugins" / "visible-plugin").mkdir(parents=True)
            (root / ".github" / "plugins" / ".hidden").mkdir(parents=True)
            (root / "skills" / "visible" / "SKILL.md").write_text("# visible", encoding="utf-8")
            (root / ".github" / "plugins" / "visible-plugin" / "SKILL.md").write_text("# plugin", encoding="utf-8")
            (root / ".github" / "plugins" / ".hidden" / "SKILL.md").write_text("# hidden", encoding="utf-8")
            discovered = skill_files(root, ("skills", ".github/plugins"))
            self.assertEqual({path.parent.name for path in discovered}, {"visible", "visible-plugin"})

    def test_category_classification_uses_skill_metadata(self):
        self.assertEqual(classify_skill("figma-review", "Figma Review", "Review a UI design", "skills/figma"), "Design")
        self.assertEqual(classify_skill("meeting-notes", "Meeting Notes", "Summarize meetings", "skills/notes"), "Productivity")

    def test_category_classification_covers_common_upstream_skill_titles(self):
        samples = (
            ("deploy", "Deploy", "IaC execution and health verification", "Development"),
            ("wiki-vitepress", "Wiki Vitepress", "Build a static site", "Web"),
            ("agent-supply-chain", "Agent Supply Chain", "Verify plugin integrity", "Security"),
            ("qdrant-monitoring", "Qdrant Monitoring", "Tune query performance", "Database"),
            ("arize-evaluator", "Arize Evaluator", "Run model evaluations", "Research"),
            ("power-bi-dax-optimization", "Power BI DAX Optimization", "Improve formulas", "Data"),
            ("create-readme", "Create Readme", "Generate a project overview", "Documents"),
            ("memory-merger", "Memory Merger", "Merge lessons into instructions", "Productivity"),
            ("wechat-hotspot-publisher", "Wechat Hotspot Publisher", "Publish selected content", "Writing"),
            ("doublecheck", "Doublecheck", "Evidence-backed verification with web search", "Research"),
            ("playwright-automation-fill-in-form", "Playwright Automation Fill In Form", "Automate a form using MCP", "Development"),
            ("csharp-async", "Csharp Async", "Best practices for async code", "Development"),
            ("spring-boot-testing", "Spring Boot Testing", "Testing techniques", "Development"),
            ("phoenix-evals", "Phoenix Evals", "Build evaluators for LLM apps", "Research"),
            ("context-engineering", "Context Engineering", "Improve agent context", "Productivity"),
            ("apple-appstore-reviewer", "Apple Appstore Reviewer", "Review app code against store requirements", "Development"),
            ("from-the-other-side-wiggins", "From The Other Side Wiggins", "Narrative and synthesis profile", "Writing"),
            ("suggest-awesome-github-copilot-skills", "Suggest Awesome Github Copilot Skills", "Suggest relevant skills", "Productivity"),
            ("vardoger-analyze", "Vardoger Analyze", "Personalize the Copilot assistant", "Productivity"),
        )
        for slug, name, description, expected in samples:
            with self.subTest(slug=slug):
                self.assertEqual(classify_skill(slug, name, description, "skills/example"), expected)

    def test_category_classification_prefers_title_and_respects_word_boundaries(self):
        self.assertEqual(
            classify_skill("design-review", "Design Review", "Check security compliance", "skills/example"),
            "Design",
        )
        self.assertEqual(classify_skill("metadata-cleanup", "Metadata Cleanup", "Clean metadata", "skills/example"), "Skills")
        self.assertEqual(classify_skill("database-guide", "Database Guide", "Use a data store", "skills/example"), "Database")

    def test_slug_collision_gets_deterministic_source_suffix(self):
        used = {"code-review"}
        self.assertEqual(unique_slug("code-review", "microsoft/skills", used), "code-review-microsoft")

    def test_resource_copy_preserves_nested_files_but_not_symlinks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            destination = root / "destination"
            (source / "references").mkdir(parents=True)
            (source / "references" / "guide.md").write_text("guide", encoding="utf-8")
            (source / ".private").write_text("hidden", encoding="utf-8")
            external = root / "outside.txt"
            external.write_text("outside", encoding="utf-8")
            (source / "external.txt").symlink_to(external)
            copy_skill_resources(source, destination)
            self.assertEqual((destination / "references" / "guide.md").read_text(encoding="utf-8"), "guide")
            self.assertFalse((destination / ".private").exists())
            self.assertFalse((destination / "external.txt").exists())

    def test_catalog_version_changes_only_when_abilities_change(self):
        abilities = [{"slug": "one"}]
        today = date(2026, 10, 4)
        previous = {"marketplaceVersion": "2026.10.04.1", "abilities": abilities}
        self.assertEqual(next_marketplace_version(abilities, previous, today), "2026.10.04.1")
        self.assertEqual(next_marketplace_version(abilities + [{"slug": "two"}], previous, today), "2026.10.04.2")

    def test_automatic_sources_have_declared_mit_licenses(self):
        self.assertEqual(
            {source["repository"] for source in SKILL_SOURCES},
            {"microsoft/skills", "github/awesome-copilot", "addyosmani/agent-skills"},
        )
        self.assertTrue(all(source["license"] == "MIT" for source in SKILL_SOURCES))

    def test_skill_mirror_writes_category_resources_and_upstream_attribution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "upstream"
            skill_dir = source_root / "skills" / "ui-review"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: ui-review\ndescription: Review user interface designs\nversion: 1.2.0\n---\n# Review\n",
                encoding="utf-8",
            )
            (skill_dir / "references").mkdir()
            (skill_dir / "references" / "guide.md").write_text("guide", encoding="utf-8")
            (source_root / "LICENSE").write_text("MIT License", encoding="utf-8")
            destination_root = root / "generated"
            original_destination = sync_marketplace.SKILLS_DEST_DIR
            sync_marketplace.SKILLS_DEST_DIR = destination_root
            try:
                ability = sync_marketplace.write_skill(
                    {
                        "repository": "microsoft/skills",
                        "display_name": "Microsoft",
                        "license": "MIT",
                        "license_file": "LICENSE",
                    },
                    source_root,
                    skill_dir / "SKILL.md",
                    set(),
                )
            finally:
                sync_marketplace.SKILLS_DEST_DIR = original_destination

            self.assertEqual(ability["category"], "Design")
            self.assertEqual(ability["source"]["repository"], "microsoft/skills")
            self.assertEqual((destination_root / "ui-review" / "references" / "guide.md").read_text(encoding="utf-8"), "guide")
            self.assertEqual((destination_root / "ui-review" / "UPSTREAM-LICENSE.txt").read_text(encoding="utf-8"), "MIT License")
            self.assertIn("microsoft/skills", (destination_root / "ui-review" / "ATTRIBUTION.md").read_text(encoding="utf-8"))

    def test_unchanged_english_description_reuses_previous_translation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = root / "skills" / "ui-review"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: ui-review\ndescription: Review user interface designs\n---\n# Review\n",
                encoding="utf-8",
            )
            destination_root = root / "generated"
            original_destination = sync_marketplace.SKILLS_DEST_DIR
            original_api_key = sync_marketplace.API_KEY
            original_translate = sync_marketplace.translate_to_chinese
            sync_marketplace.SKILLS_DEST_DIR = destination_root
            sync_marketplace.API_KEY = "test-key"
            sync_marketplace.translate_to_chinese = lambda _text: self.fail("translation should be reused")
            try:
                ability = sync_marketplace.write_skill(
                    {"repository": "microsoft/skills", "display_name": "Microsoft", "license": "MIT"},
                    root,
                    skill_dir / "SKILL.md",
                    set(),
                    {
                        "ui-review": {
                            "description": "复核界面设计",
                            "detail": {
                                "i18n": {
                                    "en": {"description": "Review user interface designs"},
                                    "zh": {"description": "复核界面设计"},
                                }
                            },
                        }
                    },
                )
            finally:
                sync_marketplace.SKILLS_DEST_DIR = original_destination
                sync_marketplace.API_KEY = original_api_key
                sync_marketplace.translate_to_chinese = original_translate

            self.assertEqual(ability["description"], "复核界面设计")

    def test_unlicensed_anbeime_entries_are_quarantined(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = root / "security-review"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# old", encoding="utf-8")
            original_destination = sync_marketplace.SKILLS_DEST_DIR
            sync_marketplace.SKILLS_DEST_DIR = root
            try:
                preserved = sync_marketplace.preserve_legacy_anbeime_abilities(
                    {
                        "abilities": [
                            {
                                "type": "skill",
                                "slug": "security-review",
                                "name": "Security Review",
                                "description": "Check security and privacy",
                                "author": "anbeime / 567 Agent",
                                "source": {"path": "skills/security-review"},
                            }
                        ]
                    },
                    set(),
                )
            finally:
                sync_marketplace.SKILLS_DEST_DIR = original_destination
            self.assertEqual(preserved, [])


    def test_frontmatter_handles_bom_crlf_quotes_and_delimiter(self):
        fields, body = parse_frontmatter('\ufeff---\r\nname: "quoted\\nname"\r\ndescription: plain # comment\r\n---\r\nBody')
        self.assertEqual(fields["name"], "quoted\nname")
        self.assertEqual(fields["description"], "plain")
        self.assertEqual(body, "Body")
        self.assertEqual(parse_frontmatter("---\nname: x\n---invalid\nBody")[0], {})

    def test_classification_does_not_match_word_fragments_or_repository_names(self):
        self.assertEqual(classify_skill("meeting-notes", "Meeting Notes", "Build meeting summaries", ".github/skills/meeting-notes"), "Productivity")
        self.assertEqual(classify_skill("frontend-design", "Frontend Design", "Create UI designs with secure code", "skills/frontend-design"), "Design")
        self.assertEqual(classify_skill("image-editor", "Image Editor", "Create pictures", ".github/plugins/image-editor"), "Media")

    def test_discovery_does_not_traverse_symlinked_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "outside").mkdir()
            (root / "outside" / "SKILL.md").write_text("# external")
            (root / "skills").mkdir()
            (root / "skills" / "linked").symlink_to(root / "outside", target_is_directory=True)
            self.assertEqual(skill_files(root, ("skills",)), [])

    def test_package_digest_changes_when_only_supporting_file_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "SKILL.md").write_text("# unchanged")
            support = root / "helper.py"
            support.write_text("old")
            before = package_digest(root)
            support.write_text("new")
            self.assertNotEqual(package_digest(root), before)

    def test_publisher_rolls_back_every_output_on_partial_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_one, old_two = root / "one", root / "two"
            new_one, new_two = root / "staged-one", root / "staged-two"
            for path, text in ((old_one, "old one"), (old_two, "old two"), (new_one, "new one"), (new_two, "new two")):
                path.write_text(text)
            original = Path.rename
            def fail_second(path, target):
                if path == new_two:
                    raise OSError("simulated replace failure")
                return original(path, target)
            with patch.object(Path, "rename", fail_second):
                with self.assertRaises(OSError):
                    publish_staged_paths([(new_one, old_one), (new_two, old_two)], root / "backup")
            self.assertEqual(old_one.read_text(), "old one")
            self.assertEqual(old_two.read_text(), "old two")

    def test_unknown_skill_license_requires_review(self):
        with self.assertRaises(ValueError):
            sync_marketplace.resolve_skill_license(Path("/missing"), "Proprietary")

    def test_license_reference_resolves_local_apache_license(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "LICENSE.txt").write_text("Apache License\nVersion 2.0")
            self.assertEqual(sync_marketplace.resolve_skill_license(root, "Complete terms in LICENSE.txt"), "Apache-2.0")

    def test_failed_translation_is_retried_and_stale_resources_are_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill = root / "upstream" / "skills" / "design-review"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: design-review\ndescription: Review UI design\n---\n# Body")
            generated = root / "generated"
            source = {"repository": "microsoft/skills", "display_name": "Microsoft", "license": "MIT"}
            with patch.object(sync_marketplace, "SKILLS_DEST_DIR", generated):
                with patch.object(sync_marketplace, "translate_to_chinese", return_value="Review UI design"):
                    first = sync_marketplace.write_skill(source, root / "upstream", skill / "SKILL.md", set())
                (generated / first["slug"] / "obsolete.txt").write_text("remove me")
                with patch.object(sync_marketplace, "translate_to_chinese", return_value="复核界面设计") as translate:
                    second = sync_marketplace.write_skill(source, root / "upstream", skill / "SKILL.md", {first["slug"]}, {first["slug"]: first})
                translate.assert_called_once()
                self.assertEqual(second["description"], "复核界面设计")
                self.assertFalse((generated / first["slug"] / "obsolete.txt").exists())
                self.assertEqual(second["configVersion"], first["configVersion"] + 1)
                with patch.object(sync_marketplace, "translate_to_chinese", side_effect=AssertionError("must reuse cache")):
                    third = sync_marketplace.write_skill(source, root / "upstream", skill / "SKILL.md", {second["slug"]}, {second["slug"]: second})
                self.assertEqual(third, second)

    def test_existing_slug_survives_new_source_collision_and_upstream_name_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill = root / "upstream" / "skills" / "review"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: renamed-review\ndescription: Review code\n---\n# Body")
            old = {"type": "skill", "slug": "code-review-microsoft", "configVersion": 3, "source": {"repository": "microsoft/skills", "upstreamPath": "skills/review/SKILL.md"}}
            with patch.object(sync_marketplace, "SKILLS_DEST_DIR", root / "generated"), patch.object(sync_marketplace, "API_KEY", ""):
                item = sync_marketplace.write_skill({"repository": "microsoft/skills", "display_name": "Microsoft", "license": "MIT"}, root / "upstream", skill / "SKILL.md", {"code-review", old["slug"]}, {old["slug"]: old})
            self.assertEqual(item["slug"], old["slug"])
            self.assertEqual(item["configVersion"], 4)

    def test_upstream_failure_leaves_all_existing_outputs_unchanged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "skills" / "legacy").mkdir(parents=True)
            (root / "skills" / "legacy" / "SKILL.md").write_text("old skill")
            (root / "mcps").mkdir()
            (root / "marketplace.json").write_text('{"marketplaceVersion":"1","abilities":[]}')
            (root / "mcp-curation.json").write_text("{}")
            before = package_digest(root)
            with patch.object(sync_marketplace, "REPO_ROOT", root), patch.object(sync_marketplace, "SKILLS_DEST_DIR", root / "skills"), patch.object(sync_marketplace, "MCPS_DEST_DIR", root / "mcps"), patch.object(sync_marketplace, "checkout_source", side_effect=subprocess.CalledProcessError(1, "git clone")):
                with self.assertRaises(subprocess.CalledProcessError):
                    sync_marketplace.main()
            self.assertEqual(package_digest(root), before)

    def test_mirror_preserves_tool_permissions_and_nested_runtime_metadata(self):
        original = "---\nname: old\ndescription: >-\n  original text\nallowed-tools: Bash Read\ncompatibility: Requires Python\nmetadata:\n  author: Original Author\n  version: 2.0\n---\n# Body\n"
        rendered = render_skill_document(original, {"name": "new", "description": "中文说明"})
        self.assertIn("allowed-tools: Bash Read", rendered)
        self.assertIn("compatibility: Requires Python", rendered)
        self.assertIn("metadata:\n  author: Original Author\n  version: 2.0", rendered)
        self.assertNotIn("original text", rendered)
        self.assertEqual(parse_frontmatter(rendered)[0]["name"], "new")
        self.assertEqual(parse_frontmatter(original)[0]["metadata.author"], "Original Author")
        self.assertEqual(parse_frontmatter(original)[0]["metadata.version"], "2.0")

    def test_skipped_update_keeps_the_previous_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill = root / "upstream" / "skills" / "review"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: code-review\ndescription: Review code\n---\n# Body")
            source = {"repository": "microsoft/skills", "display_name": "Microsoft", "license": "MIT"}
            destination = root / "generated"
            with patch.object(sync_marketplace, "SKILLS_DEST_DIR", destination), patch.object(sync_marketplace, "API_KEY", ""):
                first = sync_marketplace.write_skill(source, root / "upstream", skill / "SKILL.md", set())
                before = package_digest(destination / first["slug"])
                with patch.object(sync_marketplace, "copy_skill_resources", side_effect=ValueError("oversized resource")):
                    second = sync_marketplace.write_skill(source, root / "upstream", skill / "SKILL.md", {first["slug"]}, {first["slug"]: first})
            self.assertIsNone(second)
            self.assertEqual(package_digest(destination / first["slug"]), before)
            self.assertEqual([path.name for path in destination.iterdir()], [first["slug"]])

    def test_curated_python_mcps_use_python_packages(self):
        mcps = {item["slug"]: item for item in sync_marketplace.CURATED_MCPS}
        self.assertEqual(mcps["fetch"]["server"], {"type": "stdio", "command": "uvx", "args": ["mcp-server-fetch"]})
        self.assertIn("--db-path", mcps["sqlite"]["server"]["args"])

    def test_official_mcp_upstreams_are_explicit_and_supported(self):
        upstreams = {item["slug"]: item for item in sync_marketplace.MCP_UPSTREAM_SERVERS}
        self.assertEqual(set(upstreams), {"filesystem", "fetch", "memory", "git", "sequential-thinking", "time"})
        curated = {item["slug"] for item in sync_marketplace.CURATED_MCPS}
        self.assertTrue(set(upstreams).issubset(curated))

    def test_mcp_upstream_package_metadata_maps_to_pinned_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            npm_dir = root / "src" / "memory"
            npm_dir.mkdir(parents=True)
            (npm_dir / "package.json").write_text(json.dumps({
                "name": "@modelcontextprotocol/server-memory",
                "version": "1.2.3",
                "description": "A memory MCP server",
                "license": "SEE LICENSE IN LICENSE",
            }), encoding="utf-8")
            npm = sync_marketplace.read_mcp_upstream_server(root, {
                "slug": "memory", "path": "src/memory", "name": "Memory",
                "category": "System", "tags": ["memory"],
            })
            self.assertEqual(npm["server"], {
                "type": "stdio", "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory@1.2.3"],
            })

            python_dir = root / "src" / "git"
            python_dir.mkdir(parents=True)
            (python_dir / "pyproject.toml").write_text(
                '[project]\nname = "mcp-server-git"\nversion = "2.3.4"\n'
                'description = "A Git MCP server"\nlicense = { text = "MIT" }\n',
                encoding="utf-8",
            )
            python_server = sync_marketplace.read_mcp_upstream_server(root, {
                "slug": "git", "path": "src/git", "name": "Git",
                "category": "Development", "tags": ["git"],
            })
            self.assertEqual(python_server["server"], {
                "type": "stdio", "command": "uvx", "args": ["mcp-server-git==2.3.4"],
            })

    def test_mcp_translations_reuse_unchanged_cache_and_refresh_changed_text(self):
        previous = {
            "filesystem": {
                "description": "本地文件操作服务",
                "detail": {"i18n": {
                    "en": {"description": "Filesystem operations"},
                    "zh": {"description": "本地文件操作服务"},
                }},
            }
        }
        servers = {
            "filesystem": {"description_en": "Filesystem operations"},
            "git": {"description_en": "Read and search Git repositories"},
        }
        with patch.object(sync_marketplace, "API_KEY", "test-key"), patch.object(
            sync_marketplace, "translate_to_chinese", return_value="读取并搜索 Git 仓库"
        ) as translate:
            translated = sync_marketplace.translate_mcp_descriptions(servers, previous)
        self.assertEqual(translated, {
            "filesystem": "本地文件操作服务",
            "git": "读取并搜索 Git 仓库",
        })
        translate.assert_called_once_with("Read and search Git repositories")

    def test_translation_batches_translate_all_pending_items_past_old_limit(self):
        texts = [f"English description {index}" for index in range(1005)]
        with patch.object(sync_marketplace, "API_KEY", "test-key"), \
             patch.object(sync_marketplace, "MAX_TRANSLATIONS_PER_SYNC", 200_000), \
             patch.object(sync_marketplace, "TRANSLATION_BATCH_ITEMS", 24), \
             patch.object(sync_marketplace, "_translate_batch", side_effect=lambda group: [f"中文 {text}" for text in group]) as batch:
            translated = sync_marketplace.translate_texts(texts, "test descriptions")
        self.assertEqual(len(translated), len(texts))
        self.assertTrue(all(value.startswith("中文 ") for value in translated))
        self.assertEqual(sum(len(call.args[0]) for call in batch.call_args_list), len(texts))

    def test_translation_batch_parses_json_array_without_reordering(self):
        content = json.dumps([
            {"id": 1, "translation": "第二条中文"},
            {"id": 0, "translation": "第一条中文"},
        ], ensure_ascii=False)
        with patch.object(sync_marketplace, "_request_translation", return_value=content):
            self.assertEqual(
                sync_marketplace._translate_batch(["First description", "Second description"]),
                ["第一条中文", "第二条中文"],
            )

    def test_translation_batch_falls_back_when_ids_are_missing_or_duplicated(self):
        invalid_responses = (
            json.dumps([{"id": 0, "translation": "第一条中文"}, {"id": 0, "translation": "错位中文"}], ensure_ascii=False),
            json.dumps([{"id": 0, "translation": "第一条中文"}], ensure_ascii=False),
        )
        for response in invalid_responses:
            with self.subTest(response=response), \
                 patch.object(sync_marketplace, "_request_translation", return_value=response), \
                 patch.object(sync_marketplace, "translate_to_chinese", side_effect=["第一条中文", "第二条中文"]) as translate:
                self.assertEqual(
                    sync_marketplace._translate_batch(["First description", "Second description"]),
                    ["第一条中文", "第二条中文"],
                )
                self.assertEqual(translate.call_count, 2)

    def test_translation_cache_reuses_only_exact_source_hash(self):
        source = "A stable source description"
        changed = "A changed source description"
        key = hashlib.sha256(source.encode("utf-8")).hexdigest()
        sync_marketplace.TRANSLATION_CACHE[key] = "稳定的源描述"
        with patch.object(sync_marketplace, "API_KEY", "test-key"), patch.object(
            sync_marketplace, "TRANSLATION_CHECKPOINT_BATCHES", 1
        ), patch.object(sync_marketplace, "_translate_batch", return_value=["已翻译的新描述"]) as batch, patch.object(
            sync_marketplace, "_persist_translation_checkpoint"
        ) as persist:
            self.assertEqual(
                sync_marketplace.translate_texts([source, changed], "test descriptions"),
                ["稳定的源描述", "已翻译的新描述"],
            )
        batch.assert_called_once_with([changed])
        persist.assert_called_once_with()

    def test_translation_checkpoint_loads_only_valid_chinese_values(self):
        source = "A resumable source"
        key = hashlib.sha256(source.encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "translation-cache.json.gz"
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                json.dump({key: "可恢复的译文", "bad": "English only"}, handle)
            sync_marketplace.load_translation_checkpoint(path)
        self.assertEqual(sync_marketplace.TRANSLATION_CACHE, {key: "可恢复的译文"})

    def test_mcp_translation_includes_localized_name_and_description(self):
        servers = {
            "academic-research": {
                "name_en": "Academic Research Intelligence MCP",
                "description_en": "Academic paper search and citation analysis.",
            }
        }
        with patch.object(sync_marketplace, "API_KEY", "test-key"), patch.object(
            sync_marketplace,
            "translate_texts",
            return_value=["学术论文搜索与引文分析。", "学术研究智能 MCP"],
        ) as translate:
            localized = sync_marketplace.translate_mcp_fields(servers, {})
        self.assertEqual(localized["academic-research"], {
            "name": "学术研究智能 MCP",
            "description": "学术论文搜索与引文分析。",
        })
        translate.assert_called_once_with(
            ["Academic paper search and citation analysis.", "Academic Research Intelligence MCP"],
            "MCP names/descriptions",
        )

    def test_mcp_record_uses_chinese_name_and_description_for_default_display(self):
        discovery = {
            "name_en": "Academic Research Intelligence MCP",
            "description_en": "Academic paper search and citation analysis.",
            "version": "1.0.0",
            "identity": "registry:academic-research",
            "aliasIdentity": "academic-research",
            "repository": "https://github.com/example/academic-research",
            "sources": ["official-mcp-registry"],
            "registryName": "io.github.example/academic-research",
            "registry": {},
        }
        mcp = {
            "slug": "academic-research",
            "name": discovery["name_en"],
            "description": discovery["description_en"],
            "discovery": discovery,
        }
        with patch.object(sync_marketplace, "REPO_ROOT", Path(__file__).resolve().parents[1]):
            record = sync_marketplace.write_mcp_record(mcp, {}, {
                "academic-research": {
                    "name": "学术研究智能 MCP",
                    "description": "学术论文搜索与引文分析。",
                }
            }, {})
        self.assertEqual(record["name"], "学术研究智能 MCP")
        self.assertEqual(record["description"], "学术论文搜索与引文分析。")
        self.assertEqual(record["detail"]["i18n"]["en"]["name"], "Academic Research Intelligence MCP")

    def test_translation_batch_falls_back_to_single_item_requests_when_json_is_invalid(self):
        with patch.object(sync_marketplace, "_request_translation", return_value="not json"), patch.object(
            sync_marketplace, "translate_to_chinese", side_effect=["第一条译文", "第二条译文"]
        ) as translate:
            result = sync_marketplace._translate_batch(["First description", "Second description"])
        self.assertEqual(result, ["第一条译文", "第二条译文"])
        self.assertEqual(translate.call_count, 2)

    def test_mcp_package_update_pins_runtime_and_bumps_config_version(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "mcps"
            mcp = {
                "slug": "git", "name": "Git 仓库工具", "category": "Development",
                "tags": ["Git", "MCP"], "description": "Git 服务",
                "upstream": {
                    "path": "src/git", "package": "mcp-server-git",
                    "package_version": "0.6.2", "description_en": "A Git MCP server",
                    "server": {"type": "stdio", "command": "uvx", "args": ["mcp-server-git==0.6.2"]},
                },
            }
            with patch.object(sync_marketplace, "MCPS_DEST_DIR", destination):
                first = sync_marketplace.write_mcp_record(mcp, {}, {"git": "Git 服务"})
                config = json.loads((destination / "git" / "mcp.json").read_text(encoding="utf-8"))
                self.assertEqual(config["server"]["args"], ["mcp-server-git==0.6.2"])

                updated = dict(mcp)
                updated["upstream"] = {**mcp["upstream"], "package_version": "0.6.3",
                    "server": {"type": "stdio", "command": "uvx", "args": ["mcp-server-git==0.6.3"]}}
                second = sync_marketplace.write_mcp_record(updated, {"git": first}, {"git": "Git 服务"})
            self.assertEqual(first["configVersion"], 1)
            self.assertEqual(second["configVersion"], 2)
            self.assertEqual(second["version"], "0.6.3")
            self.assertEqual(second["source"]["repository"], "modelcontextprotocol/servers")

    def test_unreviewed_mcp_has_automatic_browsing_hints_but_is_not_installable(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "mcps"
            candidate = {
                "identity": "github:example/blender-mcp",
                "name_en": "Blender MCP",
                "description_en": "Control Blender models with an MCP server",
                "version": "1.0.0",
                "repository": "https://github.com/example/blender-mcp",
                "sources": ["TensorBlock", "punkpeye"],
                "runtimeMode": "stdio",
                "authentication": "unknown",
                "registryName": "io.github.example/blender-mcp",
            }
            with patch.object(sync_marketplace, "MCPS_DEST_DIR", destination):
                record = sync_marketplace.write_mcp_record({
                    "slug": "blender-mcp",
                    "name": "Blender MCP",
                    "description": candidate["description_en"],
                    "discovery": candidate,
                }, {}, {})
            self.assertEqual(record["type"], "mcp")
            self.assertEqual(record["category"], "cad-3d")
            self.assertEqual(record["tags"], ["3d-modeling", "blender"])
            self.assertEqual(record["mcpMetadata"], {
                "runtimeMode": "stdio", "platforms": ["unknown"],
                "permissionScopes": ["unknown"], "authentication": "unknown",
                "publisherType": "unknown", "installable": False,
            })
            self.assertEqual(record["icon"], "")
            self.assertEqual(record["classificationSource"], "automatic")
            self.assertEqual(record["source"]["path"], "mcps/discovery")
            self.assertFalse(destination.exists())
            self.assertEqual(
                sync_marketplace.suggest_mcp_classification("Blender MCP", candidate["description_en"])["category"],
                "cad-3d",
            )

    def test_mcp_discovery_merges_sources_without_collapsing_distinct_servers_in_one_repo(self):
        registry = {
            "servers": [
                {"server": {"name": "io.github.foo/demo-mcp", "title": "Demo MCP", "description": "Demo", "version": "1.0.0", "repository": {"url": "https://github.com/foo/demo-mcp"}}, "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active"}}},
                {"server": {"name": "io.github.foo/demo-mcp/extra", "title": "Extra MCP", "description": "Extra", "version": "1.0.0", "repository": {"url": "https://github.com/foo/demo-mcp"}}, "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active"}}},
            ],
            "metadata": {},
        }
        hq = [{"name": "Demo MCP", "url": "https://github.com/foo/demo-mcp", "description": "Demo from HQ"}]
        tensor = [{"name": "Demo MCP", "description": "Demo from TensorBlock", "links": {"repo": "https://github.com/foo/demo-mcp"}}]
        with patch.object(sync_marketplace, "fetch_json", side_effect=[registry, hq, tensor]), patch.object(
            sync_marketplace, "fetch_text", return_value="- [Demo MCP](https://github.com/foo/demo-mcp) - Punkpeye entry"
        ):
            candidates = sync_marketplace.collect_mcp_candidates()
        demo = next(item for item in candidates if item["name_en"] == "Demo MCP")
        self.assertEqual(set(demo["sources"]), {"official-mcp-registry", "mcpHQ", "TensorBlock", "punkpeye"})
        self.assertEqual(len(candidates), 2)

    def test_registry_sync_uses_updated_since_watermark_after_bootstrap(self):
        response = {"servers": [], "metadata": {}}
        previous = {"mcp-one": {"type": "mcp", "source": {"registryUpdatedAt": "2026-10-01T12:00:00Z"}}}
        with patch.object(sync_marketplace, "fetch_json", return_value=response) as fetch:
            self.assertEqual(sync_marketplace.registry_servers(previous), [])
        requested_url = fetch.call_args.args[0]
        self.assertIn("version=latest", requested_url)
        self.assertIn("updated_since=2026-10-01T11%3A55%3A00.000Z", requested_url)

    def test_discovery_links_require_https_without_embedded_credentials(self):
        self.assertEqual(sync_marketplace.safe_https_url("https://github.com/example/server"), "https://github.com/example/server")
        self.assertEqual(sync_marketplace.safe_https_url("http://example.com/server"), "")
        self.assertEqual(sync_marketplace.safe_https_url("https://user:token@example.com/server"), "")

    def test_registry_deleted_entry_is_removed_unless_another_feed_still_lists_it(self):
        previous = {
            "demo-mcp": {
                "type": "mcp", "slug": "demo-mcp", "name": "Demo MCP", "description": "Demo",
                "version": "1.0.0", "license": "", "author": "",
                "mcpMetadata": {"runtimeMode": "stdio", "authentication": "unknown"},
                "detail": {"i18n": {"en": {"name": "Demo MCP", "description": "Demo"}}},
                "source": {"registryName": "io.github.example/demo-mcp", "registryUpdatedAt": "2026-10-01T12:00:00Z"},
            },
        }
        deleted = {
            "servers": [{"server": {"name": "io.github.example/demo-mcp", "title": "Demo MCP", "version": "1.0.0"},
                         "_meta": {"io.modelcontextprotocol.registry/official": {"status": "deleted", "updatedAt": "2026-10-03T12:00:00Z"}}}],
            "metadata": {},
        }
        with patch.object(sync_marketplace, "fetch_json", side_effect=[deleted, [], []]), patch.object(
            sync_marketplace, "fetch_text", return_value=""
        ):
            self.assertEqual(sync_marketplace.collect_mcp_candidates(previous), [])

    def test_automatic_mcp_classification_prefers_title_and_respects_word_boundaries(self):
        classify = sync_marketplace.suggest_mcp_classification
        self.assertEqual(classify("GitHub MCP", "Search for Blender images")["category"], "developer-tools")
        self.assertEqual(classify("Digital bridge", "Connect ordinary services"), {"category": "uncategorized", "tags": []})
        self.assertNotIn("git", classify("Code assistant", "Help with code")["tags"])

    def test_reviewed_category_overrides_automatic_hints_without_approving_installation(self):
        item = {"slug": "blender-sample", "name": "Blender MCP", "description": "Control Blender"}
        record = sync_marketplace.write_mcp_record(item, {}, {}, {"blender-sample": {"category": "developer-tools", "tags": ["developer-tools"], "installable": False}})
        self.assertEqual(record["category"], "developer-tools")
        self.assertEqual(record["classificationSource"], "maintainer")
        self.assertFalse(record["mcpMetadata"]["installable"])

    def test_discovery_distribution_is_independently_verifiable_and_respects_utf8_byte_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            records = [sync_marketplace.write_mcp_record({"slug": f"blender-{i}", "name": "Blender", "description": "中文建模" * 30}, {}, {}, {}) for i in range(5)]
            manifest = {"marketplaceVersion": "1", "discoveryVersion": "2026.10.4", "discoveryAbilities": records}
            with patch.object(sync_marketplace, "DISCOVERY_SHARD_ITEMS", 2), patch.object(sync_marketplace, "DISCOVERY_SHARD_BYTES", 3000):
                index = sync_marketplace.build_discovery_distribution(manifest, Path(temp))
            loaded = []
            for shard in index["shards"]:
                body = (Path(temp) / shard["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), shard["sha256"])
                self.assertEqual(len(body), shard["sizeBytes"])
                self.assertLessEqual(len(body), 3000)
                payload = json.loads(body)
                self.assertEqual(payload["catalogVersion"], index["catalogVersion"])
                self.assertEqual(len(payload["abilities"]), shard["count"])
                self.assertLessEqual(shard["count"], 2)
                loaded.extend(payload["abilities"])
            self.assertEqual(index["recordCount"], 5)
            self.assertEqual(loaded, records)
            self.assertTrue(all(item["icon"] == "" and not item["mcpMetadata"]["installable"] for item in loaded))

    def test_discovery_distribution_rejects_one_record_larger_than_a_shard(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(sync_marketplace, "DISCOVERY_SHARD_BYTES", 150):
            with self.assertRaisesRegex(ValueError, "too large"):
                sync_marketplace.build_discovery_distribution({"marketplaceVersion": "1", "discoveryVersion": "1", "discoveryAbilities": [{"slug": "huge", "category": "uncategorized", "description": "中" * 100}]}, Path(temp))


if __name__ == "__main__":
    unittest.main()
