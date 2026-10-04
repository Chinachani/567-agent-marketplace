#!/usr/bin/env python3
import os
import json
import copy
from concurrent.futures import ThreadPoolExecutor
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from marketplace_sync import (
    CATEGORIES,
    SKILL_SOURCES,
    classify_skill,
    copy_skill_resources,
    next_marketplace_version,
    package_digest,
    publish_staged_paths,
    parse_frontmatter,
    render_skill_document,
    skill_files,
    slugify,
    unique_slug,
)

API_KEY = os.environ.get("API_567_KEY", "")
RAW_BASE_URL = (os.environ.get("API_567_BASE_URL") or "https://api.567.wiki/v1").rstrip("/")
COMPLETIONS_URL = f"{RAW_BASE_URL}/chat/completions" if not RAW_BASE_URL.endswith("/chat/completions") else RAW_BASE_URL
MODEL = os.environ.get("API_567_MODEL") or "gemini-3.8-flash-high"
try:
    TRANSLATION_WORKERS = min(16, max(1, int(os.environ.get("API_567_TRANSLATION_WORKERS", "6"))))
except ValueError:
    TRANSLATION_WORKERS = 6

REPO_ROOT = Path(__file__).resolve().parent
SKILLS_DEST_DIR = REPO_ROOT / "skills"
MCPS_DEST_DIR = REPO_ROOT / "mcps"

def has_chinese(text: str) -> bool:
    return any('\u4e00' <= char <= '\u9fff' for char in text)

def translate_to_chinese(text: str) -> str:
    if not text or has_chinese(text) or not API_KEY:
        return text
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一个专业的AI技能描述翻译专家。将以下技能描述翻译为地道、简明、富有行动力的中文说明，不要带有任何额外引语或标点包裹，直接输出中文文本即可。"
            },
            {"role": "user", "content": text}
        ],
        "max_tokens": 150
    }
    req = urllib.request.Request(
        COMPLETIONS_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        data=json.dumps(payload).encode("utf-8")
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            translated = data["choices"][0]["message"]["content"].strip()
            return translated if has_chinese(translated) else text
    except Exception as e:
        print(f"Translation warning for {text[:30]}: {e}")
        return text


def translate_skill_descriptions(source, repository_root: Path, skill_files: list[Path], previous_abilities: dict[str, dict]):
    """Translate missing descriptions concurrently while keeping catalog order stable."""
    if not API_KEY:
        return {}

    translations = {}
    pending_keys = []
    pending_texts = []
    for skill_file in skill_files:
        try:
            content = skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if len(content.encode("utf-8")) > 512 * 1024:
            continue
        frontmatter, body = parse_frontmatter(content)
        raw_description = frontmatter.get("description", "").strip()
        if not raw_description:
            first_line = next((line.lstrip("# ").strip() for line in body.splitlines() if line.strip()), "")
            raw_name = frontmatter.get("name") or skill_file.parent.name
            raw_description = first_line or f"{slugify(raw_name)} AI Agent Skill"
        if has_chinese(raw_description):
            continue

        key = (source["repository"], skill_file.relative_to(repository_root).as_posix())
        previous = next((
            item for item in previous_abilities.values()
            if item.get("type") == "skill"
            and item.get("source", {}).get("repository") == key[0]
            and item.get("source", {}).get("upstreamPath") == key[1]
        ), {})
        i18n = previous.get("detail", {}).get("i18n", {})
        previous_english = i18n.get("en", {}).get("description")
        previous_chinese = i18n.get("zh", {}).get("description") or previous.get("description")
        if previous_english == raw_description and previous_chinese and has_chinese(previous_chinese):
            translations[key] = previous_chinese
        else:
            pending_keys.append(key)
            pending_texts.append(raw_description)

    if pending_texts:
        print(f"Translating {len(pending_texts)} descriptions with {TRANSLATION_WORKERS} workers")
        with ThreadPoolExecutor(max_workers=TRANSLATION_WORKERS, thread_name_prefix="skill-translation") as executor:
            for key, translated in zip(pending_keys, executor.map(translate_to_chinese, pending_texts)):
                translations[key] = translated
    return translations

def checkout_source(source, temp_root: Path) -> Path:
    repository_path = source["repository"]
    checkout = temp_root / repository_path.replace("/", "--")
    url = f"https://github.com/{repository_path}.git"
    subprocess.run(
        ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", url, str(checkout)],
        check=True,
        stdout=subprocess.DEVNULL,
        timeout=300,
    )
    sparse_paths = [f"/{root}/" for root in source["roots"]]
    sparse_paths.append(f"/{source.get('license_file', 'LICENSE')}")
    subprocess.run(
        ["git", "-C", str(checkout), "sparse-checkout", "set", "--no-cone", *sparse_paths],
        check=True,
        stdout=subprocess.DEVNULL,
        timeout=300,
    )
    return checkout


def resolve_skill_license(skill_dir: Path, declared: str) -> str:
    if declared in {"MIT", "Apache-2.0"}:
        return declared
    if declared == "Complete terms in LICENSE.txt":
        text = (skill_dir / "LICENSE.txt").read_text(encoding="utf-8")
        if "MIT License" in text and "Permission is hereby granted" in text:
            return "MIT"
        if "Apache License" in text and "Version 2.0" in text:
            return "Apache-2.0"
    raise ValueError(f"Unreviewed skill license {declared!r}: {skill_dir}")


def write_skill(
    source,
    repository_root: Path,
    skill_file: Path,
    used_slugs: set[str],
    previous_abilities: dict[str, dict] | None = None,
    translations: dict[tuple[str, str], str] | None = None,
):
    try:
        content = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"Skipping unreadable skill {skill_file}: {error}")
        return None
    if len(content.encode("utf-8")) > 512 * 1024:
        print(f"Skipping oversized SKILL.md: {skill_file}")
        return None

    frontmatter, body = parse_frontmatter(content)
    raw_name = frontmatter.get("name") or skill_file.parent.name
    base_slug = slugify(raw_name)
    if not base_slug or base_slug in {"template", "skill"}:
        return None
    upstream_path = skill_file.relative_to(repository_root).as_posix()
    previous_abilities = previous_abilities or {}
    previous_slug = next((
        old_slug for old_slug, old in previous_abilities.items()
        if old.get("type") == "skill"
        and old.get("source", {}).get("repository") == source["repository"]
        and old.get("source", {}).get("upstreamPath") == upstream_path
        and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", old_slug)
    ), None)
    slug = previous_slug or unique_slug(base_slug, source["repository"], used_slugs)
    previous = previous_abilities.get(slug, {}) if previous_slug else {}

    raw_desc = frontmatter.get("description", "").strip()
    if not raw_desc:
        first_line = next((line.lstrip("# ").strip() for line in body.splitlines() if line.strip()), "")
        raw_desc = first_line or f"{slug} AI Agent Skill"
    description = raw_desc
    if not has_chinese(raw_desc):
        pretranslated = (translations or {}).get((source["repository"], upstream_path))
        if pretranslated is not None:
            description = pretranslated
        # Older catalogs did not include origin metadata. Keep their cache usable.
        elif not previous and slug not in used_slugs:
            candidate = previous_abilities.get(slug, {})
            if not candidate.get("source", {}).get("repository"):
                previous = candidate
        if pretranslated is None:
            previous_i18n = previous.get("detail", {}).get("i18n", {})
            previous_english = previous_i18n.get("en", {}).get("description")
            previous_chinese = previous_i18n.get("zh", {}).get("description") or previous.get("description")
            description = previous_chinese if previous_english == raw_desc and previous_chinese and has_chinese(previous_chinese) else translate_to_chinese(raw_desc)
    display_name = raw_name if raw_name != base_slug else raw_name.replace("-", " ").title()
    category = classify_skill(base_slug, display_name, raw_desc, upstream_path)
    license_name = resolve_skill_license(skill_file.parent, frontmatter.get("license") or source["license"])
    author = frontmatter.get("author") or frontmatter.get("metadata.author") or source["display_name"]
    version = frontmatter.get("version") or frontmatter.get("metadata.version") or "1.0.0"

    SKILLS_DEST_DIR.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix=".skill-", dir=SKILLS_DEST_DIR))
    try:
        copy_skill_resources(skill_file.parent, destination)
    except (OSError, ValueError) as error:
        shutil.rmtree(destination)
        print(f"Skipping skill with invalid or oversized resources {skill_file}: {error}")
        return None

    clean_skill_md = render_skill_document(content, {
        "name": slug, "description": description, "version": version, "license": license_name,
    })
    (destination / "SKILL.md").write_text(clean_skill_md, encoding="utf-8")

    license_path = repository_root / source.get("license_file", "LICENSE")
    if license_path.is_file():
        (destination / "UPSTREAM-LICENSE.txt").write_text(license_path.read_text(encoding="utf-8"), encoding="utf-8")
    if license_name == "Apache-2.0":
        shutil.copy2(Path(__file__).resolve().parent / "licenses" / "Apache-2.0.txt", destination / "APACHE-2.0.txt")
    (destination / "ATTRIBUTION.md").write_text(
        f"# Upstream attribution\n\n"
        f"- Repository: https://github.com/{source['repository']}\n"
        f"- Path: `{upstream_path}`\n"
        f"- Author: {author}\n"
        f"- Declared license: {license_name}\n\n"
        "This skill is mirrored from its upstream repository. See `UPSTREAM-LICENSE.txt` and any license files "
        "included with the skill for applicable terms.\n",
        encoding="utf-8",
    )

    digest = package_digest(destination)
    config_version = previous.get("configVersion", 1)
    if previous and previous.get("source", {}).get("contentSha256") != digest:
        config_version += 1
    with tempfile.TemporaryDirectory(prefix=".skill-backup-", dir=SKILLS_DEST_DIR) as backup:
        publish_staged_paths([(destination, SKILLS_DEST_DIR / slug)], Path(backup))
    used_slugs.add(slug)
    tags = [slug, category]
    return {
        "type": "skill",
        "slug": slug,
        "name": display_name,
        "description": description,
        "version": version,
        "configVersion": config_version,
        "license": license_name,
        "author": author,
        "category": category,
        "categoryI18n": {"zh": CATEGORIES[category], "en": category},
        "tags": tags,
        "detail": {
            "i18n": {
                "zh": {"name": display_name, "description": description, "tags": tags},
                "en": {"name": display_name, "description": raw_desc, "tags": tags},
            }
        },
        "source": {"path": f"skills/{slug}", "repository": source["repository"], "upstreamPath": upstream_path, "contentSha256": digest},
    }


def preserve_legacy_anbeime_abilities(previous_manifest: dict, used_slugs: set[str]) -> list[dict]:
    """Keep already mirrored entries visible without automatically recrawling an unlicensed source."""
    preserved = []
    for item in previous_manifest.get("abilities", []):
        if not isinstance(item, dict) or item.get("type") != "skill":
            continue
        if item.get("author") != "anbeime / 567 Agent":
            continue
        slug = item.get("slug")
        source_path = item.get("source", {}).get("path", "")
        if (
            not isinstance(slug, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug)
            or slug in used_slugs
            or not isinstance(source_path, str)
            or not source_path.startswith("skills/")
        ):
            continue
        if not (SKILLS_DEST_DIR / slug / "SKILL.md").is_file():
            continue
        legacy = copy.deepcopy(item)
        category = classify_skill(slug, legacy.get("name", slug), legacy.get("description", ""), source_path)
        legacy["category"] = category
        legacy["categoryI18n"] = {"zh": CATEGORIES[category], "en": category}
        legacy["source"] = {**legacy.get("source", {}), "repository": "anbeime/skill"}
        used_slugs.add(slug)
        preserved.append(legacy)
    return preserved

# 1. Standard Curated MCPs
CURATED_MCPS = [
    {
        "slug": "filesystem",
        "name": "本地受控文件系统",
        "description": "让 Agent 安全读写指定本地工作目录中的文件与代码资源。",
        "category": "System",
        "category_zh": "系统工具",
        "tags": ["文件", "本地", "MCP"],
        "server": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "./"]
        }
    },
    {
        "slug": "fetch",
        "name": "网页数据抓取 (Fetch)",
        "description": "让 Agent 抓取并解析外部网页、文章或 API 返回的数据。",
        "category": "Web",
        "category_zh": "网络浏览",
        "tags": ["网页", "爬取", "数据", "MCP"],
        "server": {
            "type": "stdio",
            "command": "uvx",
            "args": ["mcp-server-fetch"]
        }
    },
    {
        "slug": "brave-search",
        "name": "Brave 实时网络搜索",
        "description": "让 Agent 具备实时联网搜索最新科技、新闻与知识的能力。",
        "category": "Web",
        "category_zh": "网络浏览",
        "tags": ["搜索", "联网", "Brave", "MCP"],
        "server": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"]
        }
    },
    {
        "slug": "github",
        "name": "GitHub 协同工具",
        "description": "让 Agent 查看仓库文件、搜索代码、审查 PR 与追踪 Issues。",
        "category": "Development",
        "category_zh": "编程研发",
        "tags": ["GitHub", "Git", "开源", "MCP"],
        "server": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"]
        }
    },
    {
        "slug": "postgres",
        "name": "PostgreSQL 数据库",
        "description": "让 Agent 只读或受控查询 PostgreSQL 数据库架构与表数据。",
        "category": "Database",
        "category_zh": "数据分析",
        "tags": ["Postgres", "SQL", "数据库", "MCP"],
        "server": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"]
        }
    },
    {
        "slug": "sqlite",
        "name": "SQLite 数据库助手",
        "description": "让 Agent 直接连接并查询本地 SQLite 数据库文件。",
        "category": "Database",
        "category_zh": "数据分析",
        "tags": ["SQLite", "数据库", "本地", "MCP"],
        "server": {
            "type": "stdio",
            "command": "uvx",
            "args": ["mcp-server-sqlite", "--db-path", "./data.db"]
        }
    },
    {
        "slug": "memory",
        "name": "知识图谱长期记忆",
        "description": "让 Agent 跨会话建立并沉淀用户的偏好、事实与知识图谱实体。",
        "category": "System",
        "category_zh": "系统工具",
        "tags": ["记忆", "知识图谱", "长期上下文", "MCP"],
        "server": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"]
        }
    }
]

def generate_catalog(previous_manifest: dict, temp_root: Path) -> dict:
    abilities = []
    previous_abilities = {
        ability.get("slug"): ability
        for ability in previous_manifest.get("abilities", [])
        if isinstance(ability, dict) and isinstance(ability.get("slug"), str)
    }

    # 1. Process Curated MCPs
    print("=== Processing Curated MCPs ===")
    for m in CURATED_MCPS:
        slug = m["slug"]
        mcp_dir = MCPS_DEST_DIR / slug
        if mcp_dir.is_symlink() or (mcp_dir / "mcp.json").is_symlink():
            raise ValueError(f"Refusing to write through local symlink: {mcp_dir}")
        mcp_dir.mkdir(parents=True, exist_ok=True)
        mcp_json_path = mcp_dir / "mcp.json"
        with open(mcp_json_path, "w", encoding="utf-8") as f:
            json.dump({
                "schemaVersion": 1,
                "slug": slug,
                "version": "1.0.0",
                "server": m["server"],
                "parameters": []
            }, f, indent=2, ensure_ascii=False)

        digest = package_digest(mcp_dir)
        previous = previous_abilities.get(slug, {})
        config_version = previous.get("configVersion", 1)
        if previous and previous.get("source", {}).get("contentSha256") != digest:
            config_version += 1
        abilities.append({
            "type": "mcp",
            "slug": slug,
            "name": m["name"],
            "description": m["description"],
            "version": "1.0.0",
            "configVersion": config_version,
            "license": "MIT",
            "author": "Model Context Protocol",
            "category": m["category"],
            "categoryI18n": {
                "zh": m["category_zh"],
                "en": m["category"]
            },
            "tags": m["tags"],
            "detail": {
                "i18n": {
                    "zh": {
                        "name": m["name"],
                        "description": m["description"],
                        "tags": m["tags"]
                    }
                }
            },
            "source": {
                "path": f"mcps/{slug}",
                "contentSha256": digest,
            }
        })
        print(f"Processed MCP: {slug}")

    # 2. Collect portable skills from curated, license-declared upstreams.
    print("\n=== Processing Skills from curated upstream repositories ===")
    seen_slugs = {ability["slug"] for ability in abilities}
    legacy_abilities = preserve_legacy_anbeime_abilities(previous_manifest, seen_slugs)
    abilities.extend(legacy_abilities)
    if legacy_abilities:
        print(f"Preserved {len(legacy_abilities)} existing anbeime/skill entries pending license review")
    seen_slugs.update(path.name for path in SKILLS_DEST_DIR.iterdir())
    # Reserve existing identities before new skills claim colliding names.
    repositories = {source["repository"] for source in SKILL_SOURCES}
    seen_slugs.update(
        slug for slug, item in previous_abilities.items()
        if item.get("type") == "skill"
        and item.get("source", {}).get("repository") in repositories
        and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug)
    )
    for source in SKILL_SOURCES:
        print(f"Cloning {source['repository']}...")
        # An unavailable/empty upstream must fail the whole staged generation;
        # publishing a partial catalog would silently remove installed entries.
        checkout = checkout_source(source, temp_root)
        license_path = checkout / source.get("license_file", "LICENSE")
        license_text = license_path.read_text(encoding="utf-8")
        if "MIT License" not in license_text or "Permission is hereby granted" not in license_text:
            raise ValueError(f"Repository license changed: {source['repository']}")
        discovered = skill_files(checkout, source["roots"])
        if not discovered:
            raise ValueError(f"No skills discovered in {source['repository']}; check upstream roots")
        print(f"Found {len(discovered)} SKILL.md files in {source['repository']}")
        translations = translate_skill_descriptions(source, checkout, discovered, previous_abilities)
        for skill_file in discovered:
            ability = write_skill(source, checkout, skill_file, seen_slugs, previous_abilities, translations)
            if ability is not None:
                abilities.append(ability)
                print(f"Processed Skill: {ability['slug']} [{ability['category']}]")
            else:
                upstream_path = skill_file.relative_to(checkout).as_posix()
                for previous in previous_abilities.values():
                    if (previous.get("type") == "skill"
                        and previous.get("source", {}).get("repository") == source["repository"]
                        and previous.get("source", {}).get("upstreamPath") == upstream_path
                        and (SKILLS_DEST_DIR / previous["slug"] / "SKILL.md").is_file()):
                        abilities.append(copy.deepcopy(previous))
                        print(f"Retained previous mirror for skipped skill: {previous['slug']}")
                        break

    # 3. Write marketplace.json
    manifest = {
        "schemaVersion": 3,
        "name": "567-official",
        "displayName": "567 Agent 官方能力市场",
        "marketplaceVersion": next_marketplace_version(abilities, previous_manifest),
        "repository": "https://github.com/Chinachani/567-agent-marketplace",
        "minAppVersion": "1.0.0",
        "abilities": abilities
    }

    return manifest


def main():
    global SKILLS_DEST_DIR, MCPS_DEST_DIR
    previous_path = REPO_ROOT / "marketplace.json"
    # A malformed existing manifest needs repair, not replacement by an empty one.
    previous_manifest = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.is_file() else {}
    skills_destination, mcps_destination = SKILLS_DEST_DIR, MCPS_DEST_DIR
    with tempfile.TemporaryDirectory(prefix=".marketplace-sync-", dir=REPO_ROOT) as temp_dir:
        temp_root = Path(temp_dir)
        SKILLS_DEST_DIR, MCPS_DEST_DIR = temp_root / "skills", temp_root / "mcps"
        try:
            for source_dir, staged_dir in ((skills_destination, SKILLS_DEST_DIR), (mcps_destination, MCPS_DEST_DIR)):
                if source_dir.exists():
                    if source_dir.is_symlink():
                        raise ValueError(f"Refusing to replace a symlinked output directory: {source_dir}")
                    shutil.copytree(source_dir, staged_dir, symlinks=True)
                else:
                    staged_dir.mkdir()
            repositories = {source["repository"] for source in SKILL_SOURCES}
            manifest = generate_catalog(previous_manifest, temp_root)
            current_slugs = {item["slug"] for item in manifest["abilities"] if item["type"] == "skill"}
            # Only remove previously managed upstream directories. Preserve legacy
            # mirrors and unrelated local packages when pruning removed upstream skills.
            for item in previous_manifest.get("abilities", []):
                slug = item.get("slug", "")
                if (item.get("type") == "skill"
                    and item.get("source", {}).get("repository") in repositories
                    and slug not in current_slugs
                    and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug)):
                    path = SKILLS_DEST_DIR / slug
                    if path.is_symlink():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path)
            replacements = [(SKILLS_DEST_DIR, skills_destination), (MCPS_DEST_DIR, mcps_destination)]
            serialized = json.dumps(manifest, indent=2, ensure_ascii=False)
            for index, relative_path in enumerate(("marketplace.json", ".567agent/marketplace.json", ".vetta/marketplace.json")):
                staged = temp_root / f"manifest-{index}.json"
                staged.write_text(serialized, encoding="utf-8")
                replacements.append((staged, REPO_ROOT / relative_path))
            publish_staged_paths(replacements, temp_root / "backups")
        finally:
            SKILLS_DEST_DIR, MCPS_DEST_DIR = skills_destination, mcps_destination
    print(f"\nSuccessfully generated marketplace with {len(manifest['abilities'])} abilities!")


if __name__ == "__main__":
    main()
