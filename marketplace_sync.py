"""Pure helpers for collecting and presenting Agent Skills sources."""

import re
import json
import hashlib
import shutil
import textwrap
from datetime import date
from pathlib import Path

CATEGORIES = {
    "System": "系统工具",
    "Web": "网络浏览",
    "Development": "编程研发",
    "Design": "设计创意",
    "Documents": "办公文档",
    "Media": "音视频与图像",
    "Research": "研究分析",
    "Data": "数据分析",
    "Writing": "内容创作",
    "Business": "商业运营",
    "Productivity": "效率协作",
    "Security": "安全合规",
    "Database": "数据与数据库",
    "Skills": "实用技能",
}

# Sources are limited to repositories that publish portable SKILL.md content
# and declare a license compatible with redistribution.
SKILL_SOURCES = (
    {
        "repository": "microsoft/skills",
        "display_name": "Microsoft",
        "license": "MIT",
        "license_file": "LICENSE",
        "roots": (".github/plugins", ".github/skills"),
    },
    {
        "repository": "github/awesome-copilot",
        "display_name": "GitHub Community",
        "license": "MIT",
        "license_file": "LICENSE",
        "roots": ("skills", ".github/skills"),
    },
    {
        "repository": "addyosmani/agent-skills",
        "display_name": "Addy Osmani",
        "license": "MIT",
        "license_file": "LICENSE",
        "roots": ("skills",),
    },
)

_CATEGORY_KEYWORDS = (
    ("Security", ("security", "secure", "threat-model", "supply-chain", "vulnerability", "owasp", "compliance", "privacy", "安全", "合规")),
    ("Database", ("database", "postgres", "postgresql", "mysql", "sqlite", "redis", "qdrant", "snowflake", "vector-store", "datastore", "orm", "数据库")),
    ("Documents", ("docx", "document", "documents", "documentation", "readme", "markdown", "pdf", "pptx", "xlsx", "spreadsheet", "resume", "specification", "bug-report", "issue-report", "简历", "文档", "表格")),
    ("Design", ("design", "designer", "ui", "ux", "visual", "brand", "wireframe", "prototype", "canvas", "diagram", "设计", "界面")),
    ("Media", ("video", "audio", "image", "images", "photo", "music", "voice", "illustration", "animation", "视频", "音频", "图像", "绘图")),
    ("Research", ("research", "evaluator", "evaluation", "evaluations", "evals", "assessment", "benchmark", "verification", "verify", "fact-check", "evidence-backed", "paper", "literature", "scientific", "science", "academic", "分析研究", "论文", "科研")),
    ("Data", ("data", "analytics", "visualization", "observability", "telemetry", "monitoring", "power-bi", "dax", "logs", "数据", "统计")),
    ("Web", ("website", "web-site", "browser", "static-site", "vitepress", "web", "搜索", "联网", "网页", "网站")),
    ("Development", ("code", "coding", "comments", "developer", "development", "deploy", "implementation", "bug", "ai-ready", "agentsmd", "mcp", "playwright", "connector", "automation", "codespaces", "microsoft-store", "apple-appstore", "structured-autonomy", "typespec", "spring-boot", "springboot", "csharp", "kotlin", "mvvm", "next-intl", "internationalization", "i18n", "pytest", "coverage", "react", "compatibility", "ruff", "editorconfig", "containerize", "debugging", "github-release", "frontend", "backend", "api", "debug", "test", "git", "linux", "architecture", "sdk", "typescript", "javascript", "python", "java", "rust", "dotnet", "azure", "aws", "terraform", "kubernetes", "container", "docker", "devops", "refactor", "framework", "migration", "configuration", "编程", "开发", "代码")),
    ("Writing", ("write", "writer", "writing", "content", "copywriting", "wechat-hotspot", "blog", "article", "story", "narrative", "synthesis", "prompt", "写作", "文章", "文案", "内容创作")),
    ("Business", ("business", "product", "marketing", "sales", "commerce", "ecommerce", "finance", "legal", "contract", "go-to-market", "gtm", "launch", "商业", "营销", "电商", "合同")),
    ("Productivity", ("productivity", "planning", "workflow", "meeting", "project-management", "task", "organize", "memory", "workshop", "collaboration", "partnership", "personalize", "suggest-awesome", "efficiency", "context-engineering", "bench-read", "what-context-needed", "效率", "计划", "协作", "会议")),
)


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    match = re.match(r"^\ufeff?---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)", content)
    if not match:
        return {}, content
    fields: dict[str, str] = {}
    lines = match.group(1).splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if ":" not in line or line[:1].isspace():
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "metadata" and not value:
            chunks = []
            index += 1
            while index < len(lines) and (not lines[index].strip() or lines[index][:1].isspace()):
                chunks.append(lines[index])
                index += 1
            nested, _ = parse_frontmatter("---\n" + textwrap.dedent("\n".join(chunks)) + "\n---")
            fields.update({f"metadata.{nested_key}": nested_value for nested_key, nested_value in nested.items()})
            continue
        if value in {">", ">-", "|", "|-"}:
            chunks = []
            index += 1
            while index < len(lines) and (not lines[index].strip() or lines[index][:1].isspace()):
                chunks.append(lines[index].strip())
                index += 1
            fields[key] = " ".join(chunk for chunk in chunks if chunk)
            continue
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = value.strip('"')
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("''", "'")
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        if isinstance(value, str):
            fields[key] = value
        index += 1
    return fields, content[match.end():]


def skill_files(repository_root: Path, roots: tuple[str, ...]) -> list[Path]:
    files: set[Path] = set()
    for root in roots:
        root_path = repository_root / root
        if not root_path.is_dir():
            continue
        files.update(
            path for path in root_path.rglob("SKILL.md")
            if not any(part.is_symlink() for part in (path, *path.parents) if part != repository_root)
            and not _has_ignored_path(path.relative_to(repository_root))
        )
    return sorted(files, key=lambda path: path.as_posix().lower())


def render_skill_document(content: str, overrides: dict[str, str]) -> str:
    """Rewrite catalog fields while preserving upstream runtime metadata verbatim."""
    match = re.match(r"^\ufeff?---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)", content)
    extra_lines = []
    body = content
    if match:
        body = content[match.end():]
        current_key = None
        for line in match.group(1).splitlines():
            key_match = re.match(r"^([A-Za-z0-9_-]+):", line)
            if key_match:
                current_key = key_match.group(1)
            if current_key not in overrides:
                extra_lines.append(line)
    fields = [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in overrides.items()]
    return "---\n" + "\n".join(fields + extra_lines) + "\n---\n" + body.lstrip() + "\n"


def _has_ignored_path(path: Path) -> bool:
    for index, part in enumerate(path.parts):
        if part == ".github" and index == 0:
            continue
        if part.startswith(".") or part == "__MACOSX":
            return True
    return path.name.startswith("._")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", value.lower().strip()).strip("-")[:64].rstrip("-")


def unique_slug(base: str, repository: str, used: set[str]) -> str:
    if base not in used:
        return base
    suffix = slugify(repository.split("/", 1)[0]) or "upstream"
    prefix = base[: 63 - len(suffix)].rstrip("-")
    candidate = f"{prefix}-{suffix}"
    counter = 2
    while candidate in used:
        ending = f"-{suffix}-{counter}"
        candidate = f"{base[: 64 - len(ending)].rstrip('-')}{ending}"
        counter += 1
    return candidate


def classify_skill(slug: str, name: str, description: str, source_path: str) -> str:
    # Classify the skill's purpose first; repository names and generic mentions
    # in long descriptions should not outweigh the title.
    for text in (f"{slug} {name}", description):
        haystack = text.lower().replace("_", "-")
        for category, keywords in _CATEGORY_KEYWORDS:
            if any(
                keyword in haystack if re.search(r"[\u4e00-\u9fff]", keyword)
                else re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", haystack)
                for keyword in keywords
            ):
                return category
    return "Skills"


def package_digest(directory: Path) -> str:
    """Hash file paths and content, ignoring filesystem timestamps."""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file() and not path.is_symlink():
            digest.update(path.relative_to(directory).as_posix().encode("utf-8") + b"\0")
            content = path.read_bytes()
            digest.update(str(len(content)).encode("ascii") + b"\0" + content)
    return digest.hexdigest()


def publish_staged_paths(replacements: list[tuple[Path, Path]], backup_root: Path) -> None:
    """Replace staged outputs and restore all old paths if a replacement fails."""
    backup_root.mkdir(parents=True, exist_ok=True)
    completed = []
    try:
        for index, (staged, destination) in enumerate(replacements):
            destination.parent.mkdir(parents=True, exist_ok=True)
            backup = backup_root / str(index)
            existed = destination.exists() or destination.is_symlink()
            if existed:
                destination.rename(backup)
            completed.append((destination, backup, existed))
            staged.rename(destination)
    except BaseException:
        for destination, backup, existed in reversed(completed):
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            elif destination.exists() or destination.is_symlink():
                destination.unlink()
            if existed:
                backup.rename(destination)
        raise


def copy_skill_resources(source_dir: Path, destination_dir: Path) -> None:
    """Copy nested supporting files without following symlinks or hidden content."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    copied_bytes = 0

    def copy_tree(source: Path, destination: Path) -> None:
        nonlocal copied_bytes
        for item in sorted(source.iterdir(), key=lambda path: path.name.lower()):
            if item.name.startswith(".") or item.name == "__MACOSX" or item.is_symlink():
                continue
            target = destination / item.name
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                copy_tree(item, target)
            elif item.is_file():
                size = item.stat().st_size
                if size > 2 * 1024 * 1024 or copied_bytes + size > 10 * 1024 * 1024:
                    raise ValueError(f"skill resources exceed size limits: {item}")
                copied_bytes += size
                shutil.copy2(item, target)

    copy_tree(source_dir, destination_dir)


def next_marketplace_version(abilities: list[dict], previous_manifest: dict | None, today: date | None = None) -> str:
    """Only bump the catalog version when the generated ability catalog changes."""
    previous_manifest = previous_manifest or {}
    previous_abilities = previous_manifest.get("abilities")
    previous_version = previous_manifest.get("marketplaceVersion")
    if previous_abilities == abilities and isinstance(previous_version, str) and previous_version:
        return previous_version

    day = (today or date.today()).strftime("%Y.%m.%d")
    match = re.fullmatch(r"(\d{4}\.\d{2}\.\d{2})\.(\d+)", str(previous_version or ""))
    sequence = int(match.group(2)) + 1 if match and match.group(1) == day else 1
    return f"{day}.{sequence}"
