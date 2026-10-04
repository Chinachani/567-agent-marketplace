import tempfile
import unittest
import subprocess
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

    def test_existing_anbeime_entries_are_preserved_but_classified(self):
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
            self.assertEqual(preserved[0]["category"], "Security")
            self.assertEqual(preserved[0]["source"]["repository"], "anbeime/skill")


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


if __name__ == "__main__":
    unittest.main()
