#!/usr/bin/env python3
import os
import re
import json
import shutil
import urllib.request
import urllib.error
from pathlib import Path

API_KEY = os.environ.get("API_567_KEY", "")
BASE_URL = "https://api.567.wiki/v1/chat/completions"
MODEL = "gemini-3.5-flash-lite"

REPO_ROOT = Path(__file__).resolve().parent
SKILLS_SRC_DIR = Path("/tmp/anbeime-skill/skills")
SKILLS_DEST_DIR = REPO_ROOT / "skills"
MCPS_DEST_DIR = REPO_ROOT / "mcps"

SKILLS_DEST_DIR.mkdir(parents=True, exist_ok=True)
MCPS_DEST_DIR.mkdir(parents=True, exist_ok=True)

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
        BASE_URL,
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
            return translated if translated else text
    except Exception as e:
        print(f"Translation warning for {text[:30]}: {e}")
        return text

def parse_frontmatter(content: str):
    m = re.match(r"^---\r?\n([\s\S]*?)\r?\n---", content)
    if not m:
        return {}, content
    yaml_text = m.group(1)
    body = content[m.end():]
    fields = {}
    for line in yaml_text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip().strip("\"'")
    return fields, body

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
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-fetch"]
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
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-sqlite", "./data.db"]
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

def main():
    abilities = []

    # 1. Process Curated MCPs
    print("=== Processing Curated MCPs ===")
    for m in CURATED_MCPS:
        slug = m["slug"]
        mcp_dir = MCPS_DEST_DIR / slug
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

        abilities.append({
            "type": "mcp",
            "slug": slug,
            "name": m["name"],
            "description": m["description"],
            "version": "1.0.0",
            "configVersion": 1,
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
                "path": f"mcps/{slug}"
            }
        })
        print(f"Processed MCP: {slug}")

    # 2. Process Skills from anbeime-skill
    print("\n=== Processing Skills from anbeime/skill ===")
    if not SKILLS_SRC_DIR.exists():
        print(f"Cloning anbeime/skill into /tmp/anbeime-skill...")
        os.system("git clone --depth 1 https://github.com/anbeime/skill.git /tmp/anbeime-skill")
    if not SKILLS_SRC_DIR.exists():
        print(f"Directory still not found: {SKILLS_SRC_DIR}")
        return

    # Find all SKILL.md
    skill_files = list(SKILLS_SRC_DIR.glob("**/SKILL.md"))
    print(f"Found {len(skill_files)} SKILL.md files")

    seen_slugs = set()
    for skill_file in skill_files:
        try:
            content = skill_file.read_text(encoding="utf-8")
        except Exception:
            continue

        frontmatter, body = parse_frontmatter(content)
        raw_name = frontmatter.get("name")
        if not raw_name:
            raw_name = skill_file.parent.name
            if raw_name == "SKILL":
                raw_name = skill_file.parent.parent.name

        slug = re.sub(r"[^a-z0-9-]", "-", raw_name.lower().strip()).strip("-")
        if not slug or slug in seen_slugs or slug.startswith("_") or slug == "template":
            continue
        seen_slugs.add(slug)

        raw_desc = frontmatter.get("description", "")
        if not raw_desc:
            first_line = body.strip().splitlines()[0] if body.strip() else ""
            raw_desc = first_line.lstrip("#").strip() or f"{slug} AI Agent Skill"

        # Translate or keep
        if not has_chinese(raw_desc):
            desc = translate_to_chinese(raw_desc)
        else:
            desc = raw_desc

        display_name = frontmatter.get("name", slug)
        if display_name == slug:
            display_name = slug.replace("-", " ").title()

        # Copy skill files to repo skills/<slug>/
        dest_skill_dir = SKILLS_DEST_DIR / slug
        dest_skill_dir.mkdir(parents=True, exist_ok=True)

        # Write clean standardized SKILL.md
        clean_skill_md = f"---\nname: {slug}\ndescription: {desc}\nversion: 1.0.0\n---\n{body.lstrip()}\n"
        with open(dest_skill_dir / "SKILL.md", "w", encoding="utf-8") as f:
            f.write(clean_skill_md)

        # Copy other sibling files (like scripts, references) if any
        src_parent = skill_file.parent
        for item in src_parent.iterdir():
            if item.name != "SKILL.md" and item.is_file() and not item.name.startswith("."):
                shutil.copy2(item, dest_skill_dir / item.name)

        abilities.append({
            "type": "skill",
            "slug": slug,
            "name": display_name,
            "description": desc,
            "version": "1.0.0",
            "configVersion": 1,
            "license": "MIT",
            "author": "anbeime / 567 Agent",
            "category": "Skills",
            "categoryI18n": {
                "zh": "实用技能",
                "en": "Skills"
            },
            "tags": [slug, "Skill"],
            "detail": {
                "i18n": {
                    "zh": {
                        "name": display_name,
                        "description": desc,
                        "tags": [slug, "实用技能"]
                    }
                }
            },
            "source": {
                "path": f"skills/{slug}"
            }
        })
        print(f"Processed Skill: {slug} -> {desc[:40]}...")

    # 3. Write marketplace.json
    manifest = {
        "schemaVersion": 3,
        "name": "567-official",
        "displayName": "567 Agent 官方能力市场",
        "marketplaceVersion": "2026.09.24.1",
        "repository": "https://github.com/Chinachani/567-agent-marketplace",
        "minAppVersion": "1.0.0",
        "abilities": abilities
    }

    marketplace_json = REPO_ROOT / "marketplace.json"
    with open(marketplace_json, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    dot_dir = REPO_ROOT / ".567agent"
    dot_dir.mkdir(parents=True, exist_ok=True)
    with open(dot_dir / "marketplace.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    dot_vetta_dir = REPO_ROOT / ".vetta"
    dot_vetta_dir.mkdir(parents=True, exist_ok=True)
    with open(dot_vetta_dir / "marketplace.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\nSuccessfully generated marketplace with {len(abilities)} abilities!")

if __name__ == "__main__":
    main()
