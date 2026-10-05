#!/usr/bin/env python3
import os
import builtins
import json
import copy
import gzip
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import re
import shutil
import subprocess
import tempfile
import tomllib
import urllib.request
import urllib.error
import urllib.parse
import hashlib
import time
import random
import threading
import zlib
from email.utils import parsedate_to_datetime
from pathlib import Path

from marketplace_contract import validate_ability, validate_manifest
from skill_content_policy import KEY_PATTERN, redistribution_allowed, scan_skill_tree

from marketplace_sync import (
    CATEGORIES,
    MCP_UPSTREAM,
    MCP_UPSTREAM_SERVERS,
    MCP_MAIN_CATEGORIES,
    MCP_FUNCTION_TAGS,
    MCP_COLLECTION_SOURCES,
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
    TRANSLATION_WORKERS = min(16, max(1, int(os.environ.get("API_567_TRANSLATION_WORKERS", "8"))))
except ValueError:
    TRANSLATION_WORKERS = 8
try:
    MAX_TRANSLATIONS_PER_SYNC = min(200_000, max(1, int(os.environ.get("API_567_MAX_TRANSLATIONS_PER_SYNC", "200000"))))
except ValueError:
    MAX_TRANSLATIONS_PER_SYNC = 200_000
try:
    TRANSLATION_BATCH_ITEMS = min(32, max(1, int(os.environ.get("API_567_TRANSLATION_BATCH_ITEMS", "24"))))
except ValueError:
    TRANSLATION_BATCH_ITEMS = 24
try:
    TRANSLATION_CHECKPOINT_BATCHES = max(1, int(os.environ.get("API_567_TRANSLATION_CHECKPOINT_BATCHES", "250")))
except ValueError:
    TRANSLATION_CHECKPOINT_BATCHES = 250
try:
    TRANSLATION_SINGLE_FALLBACK_BUDGET = max(0, int(os.environ.get("API_567_TRANSLATION_SINGLE_FALLBACK_ITEMS", "500")))
except ValueError:
    TRANSLATION_SINGLE_FALLBACK_BUDGET = 500
try:
    TRANSLATION_CIRCUIT_FAILURE_LIMIT = max(1, int(os.environ.get("API_567_TRANSLATION_CIRCUIT_FAILURE_LIMIT", "8")))
except ValueError:
    TRANSLATION_CIRCUIT_FAILURE_LIMIT = 8

TRANSLATION_NO_CHINESE_RETRIES = 0
TRANSLATION_DIAGNOSTIC_LOGGED = False
TRANSLATION_DIAGNOSTIC_LOCK = threading.Lock()
TRANSLATION_CACHE: dict[str, str] = {}
TRANSLATION_SINGLE_FALLBACK_USED = 0
TRANSLATION_FALLBACK_BUDGET_LOGGED = False
TRANSLATION_FALLBACK_LOCK = threading.Lock()
TRANSLATION_CIRCUIT_FAILURES = 0
TRANSLATION_CIRCUIT_OPEN = False
TRANSLATION_CIRCUIT_LOCK = threading.Lock()
TRANSLATION_CIRCUIT_LOGGED = False

# The installed catalog stays small enough for the desktop client's legacy
# GitHub Contents path. Discovery candidates are published as bounded shards.
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
DISCOVERY_SHARD_ITEMS = 500
DISCOVERY_SHARD_BYTES = 1024 * 1024
DISCOVERY_MAX_RECORDS = 100_000
DISCOVERY_MAX_SHARDS = 250
DISCOVERY_MAX_BYTES = 100 * 1024 * 1024

REPO_ROOT = Path(__file__).resolve().parent
SKILLS_DEST_DIR = REPO_ROOT / "skills"
MCPS_DEST_DIR = REPO_ROOT / "mcps"
MCP_CLASSIFICATION_SUGGESTIONS = []

def safe_log(message, *, flush=False):
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", str(message))
    text = KEY_PATTERN.sub("[REDACTED]", text)
    if API_KEY:
        text = text.replace(API_KEY, "[REDACTED]")
    builtins.print("[sync] " + text[:4000], flush=flush)


def _translation_retry_delay(error, attempt: int) -> float:
    """Use server guidance when available and jitter retries to avoid retry bursts."""
    if isinstance(error, urllib.error.HTTPError):
        retry_after = error.headers.get("Retry-After") if error.headers else None
        if retry_after:
            try:
                return min(60.0, max(0.0, float(retry_after)))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    return min(60.0, max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds()))
                except (TypeError, ValueError, OverflowError):
                    pass
    if isinstance(error, (urllib.error.URLError, TimeoutError, OSError)):
        return min(60.0, (5 * (2 ** attempt)) + random.uniform(0.0, 3.0))
    return min(30.0, (2 ** attempt) + random.uniform(0.0, 1.0))


def has_chinese(text: str) -> bool:
    return any('\u4e00' <= char <= '\u9fff' for char in text)


def _reserve_single_fallback(items: int) -> bool:
    """Bound extra single-item calls after batch responses need repair."""
    global TRANSLATION_SINGLE_FALLBACK_USED, TRANSLATION_FALLBACK_BUDGET_LOGGED
    with TRANSLATION_FALLBACK_LOCK:
        if TRANSLATION_SINGLE_FALLBACK_USED + items <= TRANSLATION_SINGLE_FALLBACK_BUDGET:
            TRANSLATION_SINGLE_FALLBACK_USED += items
            return True
        if not TRANSLATION_FALLBACK_BUDGET_LOGGED:
            safe_log("Single-item translation fallback budget exhausted; remaining items deferred")
            TRANSLATION_FALLBACK_BUDGET_LOGGED = True
        return False


class TranslationCircuitOpen(RuntimeError):
    """Raised when upstream translation failures opened the per-run circuit."""


def _record_translation_failure() -> None:
    global TRANSLATION_CIRCUIT_FAILURES, TRANSLATION_CIRCUIT_OPEN, TRANSLATION_CIRCUIT_LOGGED
    with TRANSLATION_CIRCUIT_LOCK:
        TRANSLATION_CIRCUIT_FAILURES += 1
        if TRANSLATION_CIRCUIT_FAILURES >= TRANSLATION_CIRCUIT_FAILURE_LIMIT:
            TRANSLATION_CIRCUIT_OPEN = True
            if not TRANSLATION_CIRCUIT_LOGGED:
                safe_log(
                    f"Translation circuit opened after {TRANSLATION_CIRCUIT_FAILURES} upstream failures; deferring remaining batches",
                    flush=True,
                )
                TRANSLATION_CIRCUIT_LOGGED = True


def _record_translation_success() -> None:
    global TRANSLATION_CIRCUIT_FAILURES
    with TRANSLATION_CIRCUIT_LOCK:
        if not TRANSLATION_CIRCUIT_OPEN:
            TRANSLATION_CIRCUIT_FAILURES = 0

def _request_translation(messages: list[dict], max_tokens: int) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        COMPLETIONS_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        data=json.dumps(payload).encode("utf-8")
    )
    for attempt in range(3):
        if TRANSLATION_CIRCUIT_OPEN:
            raise TranslationCircuitOpen("upstream circuit is open")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            _record_translation_success()
            return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as error:
            _record_translation_failure()
            if error.code not in {408, 425, 429, 500, 502, 503, 504} or attempt == 2:
                raise
            wait = _translation_retry_delay(error, attempt)
            safe_log(f"Translation API returned HTTP {error.code}; retrying in {wait}s", flush=True)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            _record_translation_failure()
            if attempt == 2:
                raise
            wait = _translation_retry_delay(error, attempt)
            safe_log(f"Translation request failed; retrying in {wait}s: {error}", flush=True)
            time.sleep(wait)
    raise RuntimeError("Translation retries exhausted")


def translate_to_chinese(text: str) -> str:
    if not text or has_chinese(text) or not API_KEY:
        return text
    for attempt in range(2):
        try:
            if attempt == 0:
                messages = [
                    {"role": "system", "content": "将用户提供的 AI 能力名称或说明翻译成自然、简洁的简体中文。保留常见产品名、专有名词和缩写；只输出译文。"},
                    {"role": "user", "content": text},
                ]
            else:
                messages = [
                    {"role": "system", "content": "Translate the input into Simplified Chinese (简体中文). You must translate ordinary English words into Chinese. Preserve only proper names and acronyms. Return only the Chinese translation, with no explanation."},
                    {"role": "user", "content": text},
                ]
            translated = _request_translation(
                messages,
                min(2048, max(512, len(text) * 2)),
            )
            if has_chinese(translated):
                return translated
            if attempt == 0:
                global TRANSLATION_NO_CHINESE_RETRIES, TRANSLATION_DIAGNOSTIC_LOGGED
                with TRANSLATION_DIAGNOSTIC_LOCK:
                    TRANSLATION_NO_CHINESE_RETRIES += 1
                    if not TRANSLATION_DIAGNOSTIC_LOGGED:
                        sample = re.sub(r"\s+", " ", translated)[:240]
                        safe_log(
                            f"Translation response contained no Chinese; retrying once. First response sample: {sample!r}",
                            flush=True,
                        )
                        TRANSLATION_DIAGNOSTIC_LOGGED = True
        except TranslationCircuitOpen:
            return text
        except Exception as error:
            safe_log(f"Translation fallback after retries: {error}")
            return text
    return text


def _translation_groups(texts: list[str]) -> list[list[str]]:
    groups = []
    current = []
    current_chars = 0
    for text in texts:
        if current and (len(current) >= TRANSLATION_BATCH_ITEMS or current_chars + len(text) > 8000):
            groups.append(current)
            current = []
            current_chars = 0
        current.append(text)
        current_chars += len(text)
    if current:
        groups.append(current)
    return groups


def _translate_batch(texts: list[str]) -> list[str]:
    if len(texts) == 1:
        return [translate_to_chinese(texts[0])]
    prompt = json.dumps([{"id": index, "text": text} for index, text in enumerate(texts)], ensure_ascii=False)
    try:
        content = _request_translation(
            [
                {"role": "system", "content": "把输入数组中每个 AI 能力名称或说明翻译成自然、简洁的简体中文。保留常见产品名、专有名词和缩写。必须返回 JSON 对象数组，每项包含原样的 id 和 translation 字段；每个输入 id 必须且只能出现一次，不要输出 Markdown 或解释。"},
                {"role": "user", "content": prompt},
            ],
            min(6000, max(512, len(texts) * 240)),
        )
        candidate = content.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            parsed = parsed.get("translations")
        if not isinstance(parsed, list) or len(parsed) != len(texts):
            raise ValueError("translation batch returned an invalid item count")
        translations_by_id = {}
        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError("translation batch item is not an object")
            item_id = item.get("id")
            translated = item.get("translation")
            if isinstance(item_id, bool) or not isinstance(item_id, int) or not isinstance(translated, str):
                raise ValueError("translation batch item has an invalid id or translation")
            if item_id in translations_by_id:
                raise ValueError("translation batch returned a duplicate id")
            translations_by_id[item_id] = translated.strip()
        expected_ids = set(range(len(texts)))
        if set(translations_by_id) != expected_ids:
            raise ValueError("translation batch omitted or changed an id")
        needs_fallback = [index for index, value in translations_by_id.items() if not has_chinese(value)]
        fallback_allowed = _reserve_single_fallback(len(needs_fallback)) if needs_fallback else True
        results = []
        for index, original in enumerate(texts):
            translated = translations_by_id[index]
            if not has_chinese(translated):
                results.append(translate_to_chinese(original) if fallback_allowed else original)
            else:
                results.append(translated)
        return results
    except TranslationCircuitOpen:
        return texts
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
        safe_log(f"Translation batch deferred after request failure: {error}")
        return texts
    except Exception as error:
        safe_log(f"Translation batch fallback for {len(texts)} items: {error}")
        if not _reserve_single_fallback(len(texts)):
            return texts
        return [translate_to_chinese(text) for text in texts]


def translate_texts(texts: list[str], label: str) -> list[str]:
    """Translate all distinct pending strings in bounded parallel batches."""
    if not API_KEY:
        safe_log(f"API_567_KEY is unavailable; {len(texts)} {label} stay in their source language")
        return texts
    unique = list(dict.fromkeys(text for text in texts if text and not has_chinese(text)))
    if not unique:
        return texts
    cached_by_text = {
        text: TRANSLATION_CACHE[hashlib.sha256(text.encode("utf-8")).hexdigest()]
        for text in unique
        if has_chinese(TRANSLATION_CACHE.get(hashlib.sha256(text.encode("utf-8")).hexdigest(), ""))
    }
    unique = [text for text in unique if text not in cached_by_text]
    if not unique:
        return [cached_by_text.get(text, text) for text in texts]
    with TRANSLATION_DIAGNOSTIC_LOCK:
        no_chinese_retries_before = TRANSLATION_NO_CHINESE_RETRIES
    current = unique[:MAX_TRANSLATIONS_PER_SYNC]
    groups = _translation_groups(current)
    safe_log(
        f"Translating {len(current)} of {len(unique)} {label} in {len(groups)} batches with {TRANSLATION_WORKERS} workers",
        flush=True,
    )
    translated_by_text = {}
    with ThreadPoolExecutor(max_workers=TRANSLATION_WORKERS, thread_name_prefix="translation") as executor:
        futures = {executor.submit(_translate_batch, group): group for group in groups}
        for index, future in enumerate(as_completed(futures), start=1):
            group = futures[future]
            results = future.result()
            translated_by_text.update(zip(group, results))
            for source, translated in zip(group, results):
                if has_chinese(translated):
                    key = hashlib.sha256(source.encode("utf-8")).hexdigest()
                    TRANSLATION_CACHE[key] = translated
            if index % TRANSLATION_CHECKPOINT_BATCHES == 0:
                _persist_translation_checkpoint()
    unresolved = sum(1 for text in current if not has_chinese(translated_by_text.get(text, text)))
    with TRANSLATION_DIAGNOSTIC_LOCK:
        no_chinese_retries = TRANSLATION_NO_CHINESE_RETRIES - no_chinese_retries_before
    if no_chinese_retries:
        safe_log(f"{no_chinese_retries} translation requests needed a non-Chinese response retry")
    skipped = len(unique) - len(current)
    if unresolved or skipped:
        safe_log(f"Translation incomplete: {unresolved} failed after retries, {skipped} deferred")
    else:
        safe_log(f"Translation complete: {len(current)} of {len(unique)} {label}")
    current_set = set(current)
    return [
        cached_by_text.get(text, translated_by_text.get(text, text)) if text in cached_by_text or text in current_set else text
        for text in texts
    ]


def load_translation_checkpoint(path: Path | None = None) -> None:
    """Load resumable translations keyed by a hash of the exact source text."""
    checkpoint_path = path or (REPO_ROOT / ".translation-cache.json.gz")
    if not checkpoint_path.is_file():
        return
    try:
        with gzip.open(checkpoint_path, "rt", encoding="utf-8") as handle:
            cached = json.load(handle)
        if isinstance(cached, dict):
            TRANSLATION_CACHE.update({key: value for key, value in cached.items()
                                      if isinstance(key, str) and isinstance(value, str) and has_chinese(value)})
            safe_log(f"Restored {len(TRANSLATION_CACHE)} resumable translation checkpoints")
    except (OSError, EOFError, zlib.error, UnicodeError, json.JSONDecodeError) as error:
        safe_log(f"Ignoring invalid translation checkpoint: {error}")


def write_translation_checkpoint(path: Path) -> None:
    """Write the translation cache atomically enough for final catalog publication."""
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as handle:
        json.dump(TRANSLATION_CACHE, handle, ensure_ascii=False, separators=(",", ":"))


def _persist_translation_checkpoint() -> None:
    """Publish a bounded-resume cache to the catalog branch during long runs."""
    if not TRANSLATION_CACHE:
        return
    worktree_root = None
    worktree = None
    try:
        worktree_root = Path(tempfile.mkdtemp(prefix=".translation-checkpoint-", dir=REPO_ROOT))
        worktree = worktree_root / "catalog"
        subprocess.run(
            ["git", "fetch", "origin", "refs/heads/catalog:refs/remotes/origin/catalog"],
            cwd=REPO_ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), "refs/remotes/origin/catalog"],
            cwd=REPO_ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        checkpoint = worktree / "translation-cache.json.gz"
        with gzip.open(checkpoint, "wt", encoding="utf-8", compresslevel=6) as handle:
            json.dump(TRANSLATION_CACHE, handle, ensure_ascii=False, separators=(",", ":"))
        subprocess.run(["git", "-C", str(worktree), "add", "translation-cache.json.gz"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        changed = subprocess.run(["git", "-C", str(worktree), "diff", "--cached", "--quiet"], check=False).returncode != 0
        if changed:
            subprocess.run(["git", "-C", str(worktree), "config", "user.name", "github-actions[bot]"], check=True)
            subprocess.run(["git", "-C", str(worktree), "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
            subprocess.run(["git", "-C", str(worktree), "commit", "-m", "chore: checkpoint marketplace translations [skip ci]"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            subprocess.run(["git", "-C", str(worktree), "push", "origin", "HEAD:refs/heads/catalog"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            safe_log(f"Persisted {len(TRANSLATION_CACHE)} translation checkpoints")
    except (OSError, subprocess.CalledProcessError) as error:
        safe_log(f"Translation checkpoint publish failed; continuing current run: {error}")
    finally:
        if worktree is not None:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=REPO_ROOT,
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if worktree_root is not None:
            shutil.rmtree(worktree_root, ignore_errors=True)


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
        for key, translated in zip(pending_keys, translate_texts(pending_texts, "skill descriptions")):
            translations[key] = translated
    return translations

def checkout_source(source, temp_root: Path) -> Path:
    repository_path = source["repository"]
    checkout = temp_root / repository_path.replace("/", "--")
    url = f"https://github.com/{repository_path}.git"
    # Resolve once and fetch exactly that commit. A branch changing mid-run cannot
    # change the reviewed license/resources while files are being copied.
    revision = source.get("commit")
    if revision is None:
        output = subprocess.check_output(["git", "ls-remote", url, "HEAD"], timeout=60, text=True)
        revision = output.split()[0] if output.split() else ""
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Invalid upstream revision")
    checkout.mkdir(parents=True)
    for args in (("init",), ("remote", "add", "origin", url), ("config", "core.sparseCheckout", "true"),
                 ("fetch", "--depth", "1", "--filter=blob:none", "origin", revision),
                 ("checkout", "--detach", "FETCH_HEAD")):
        subprocess.run(["git", "-C", str(checkout), *args], check=True, stdout=subprocess.DEVNULL, timeout=300)
    source["resolved_commit"] = revision
    sparse_paths = [f"/{root}/" for root in source["roots"]]
    sparse_paths.append(f"/{source.get('license_file', 'LICENSE')}")
    subprocess.run(
        ["git", "-C", str(checkout), "sparse-checkout", "set", "--no-cone", *sparse_paths],
        check=True,
        stdout=subprocess.DEVNULL,
        timeout=300,
    )
    return checkout


def read_mcp_upstream_server(repository_root: Path, definition: dict) -> dict:
    """Read a supported upstream package manifest and map it to a pinned runtime."""
    server_dir = repository_root / definition["path"]
    package_json = server_dir / "package.json"
    pyproject_toml = server_dir / "pyproject.toml"
    if package_json.is_file():
        package = json.loads(package_json.read_text(encoding="utf-8"))
        package_name = package.get("name")
        version = package.get("version")
        description = package.get("description")
        declared_license = package.get("license")
        runtime = "npm"
        command = "npx"
        args = ["-y", f"{package_name}@{version}"]
    elif pyproject_toml.is_file():
        package = tomllib.loads(pyproject_toml.read_text(encoding="utf-8")).get("project", {})
        package_name = package.get("name")
        version = package.get("version")
        description = package.get("description")
        license_value = package.get("license")
        declared_license = license_value.get("text") if isinstance(license_value, dict) else license_value
        runtime = "pypi"
        command = "uvx"
        args = [f"{package_name}=={version}"]
    else:
        raise ValueError(f"No supported package manifest for upstream MCP {definition['slug']}")

    if not all(isinstance(value, str) and value.strip() for value in (package_name, version, description)):
        raise ValueError(f"Incomplete package metadata for upstream MCP {definition['slug']}")
    if declared_license not in {"MIT", "SEE LICENSE IN LICENSE", "MIT License"}:
        raise ValueError(f"Unreviewed license for upstream MCP {definition['slug']}: {declared_license!r}")

    args.extend(definition.get("args", []))
    return {
        **definition,
        "description_en": description.strip(),
        "license": "MIT",
        "package": package_name,
        "package_version": version,
        "runtime": runtime,
        "server": {"type": "stdio", "command": command, "args": args},
    }


def load_mcp_upstream(temp_root: Path) -> dict[str, dict]:
    checkout = checkout_source(MCP_UPSTREAM, temp_root)
    license_path = checkout / MCP_UPSTREAM["license_file"]
    license_text = license_path.read_text(encoding="utf-8")
    if "MIT License" not in license_text or "Permission is hereby granted" not in license_text:
        raise ValueError(f"Repository license changed: {MCP_UPSTREAM['repository']}")
    return {
        item["slug"]: read_mcp_upstream_server(checkout, item)
        for item in MCP_UPSTREAM_SERVERS
    }


def fetch_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "567-agent-marketplace-sync/1.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code not in {408, 425, 429, 500, 502, 503, 504}:
                raise
            if attempt == 4:
                raise
            wait = min(30, 2 ** attempt)
            safe_log(f"Transient upstream error; retrying in {wait}s: {error}", flush=True)
            time.sleep(wait)


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "567-agent-marketplace-sync/1.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code not in {408, 425, 429, 500, 502, 503, 504}:
                raise
            if attempt == 4:
                raise
            wait = min(30, 2 ** attempt)
            safe_log(f"Transient upstream error; retrying in {wait}s: {error}", flush=True)
            time.sleep(wait)


def registry_servers(previous_abilities: dict[str, dict]) -> list[dict]:
    """Bootstrap the full Registry once, then fetch only records updated since its watermark."""
    updated_values = [
        item.get("source", {}).get("registryUpdatedAt")
        for item in previous_abilities.values()
        if item.get("type") == "mcp" and item.get("source", {}).get("registryUpdatedAt")
    ]
    latest_updated = max(updated_values, default="")
    params = {"limit": "100", "version": "latest"}
    if latest_updated:
        try:
            watermark = datetime.fromisoformat(latest_updated.replace("Z", "+00:00")) - timedelta(minutes=5)
            params["updated_since"] = watermark.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            safe_log(f"Fetching MCP Registry updates since {params['updated_since']}", flush=True)
        except ValueError:
            safe_log("Invalid MCP Registry watermark; falling back to a full sync", flush=True)
    else:
        safe_log("Bootstrapping full latest-version MCP Registry catalog", flush=True)
    url = MCP_COLLECTION_SOURCES["registry"] + "?" + urllib.parse.urlencode(params)
    records = {}
    seen_cursors = set()
    page_number = 0
    while url:
        payload = fetch_json(url)
        page_number += 1
        for item in payload.get("servers", []):
            server = item.get("server", {})
            meta = item.get("_meta", {}).get("io.modelcontextprotocol.registry/official", {})
            name = server.get("name")
            if not name:
                continue
            records[name] = {**server, "_registryMeta": meta}
        if page_number % 25 == 0:
            safe_log(f"Registry pages: {page_number} ({len(records)} distinct names)", flush=True)
        cursor = payload.get("metadata", {}).get("nextCursor")
        if not cursor:
            break
        if cursor in seen_cursors:
            raise ValueError("MCP Registry pagination cursor repeated")
        seen_cursors.add(cursor)
        url = MCP_COLLECTION_SOURCES["registry"] + "?limit=100&version=latest&cursor=" + urllib.parse.quote(cursor, safe="")
    return list(records.values())


def github_repository(url: str) -> str:
    match = re.search(r"github\.com/([^/]+/[^/#?]+)", url or "", re.I)
    if not match:
        return ""
    return match.group(1).removesuffix(".git").lower()


def safe_https_url(value: str) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return value.strip()


def infer_runtime(record: dict) -> str:
    for remote in record.get("remotes", []):
        kind = remote.get("type", "")
        if kind in {"streamable-http", "sse"}:
            return kind
    packages = record.get("packages", [])
    if packages:
        return "stdio"
    transport = record.get("transport", [])
    if "streamable-http" in transport:
        return "streamable-http"
    if "sse" in transport:
        return "sse"
    if "stdio" in transport:
        return "stdio"
    return "unknown"


def collect_mcp_candidates(previous_abilities: dict[str, dict] | None = None) -> list[dict]:
    """Merge four discovery feeds by upstream GitHub repo or stable Registry name."""
    merged = {}
    previous_abilities = previous_abilities or {}

    # Rehydrate unchanged Registry entries from the previous manifest; the Registry
    # delta below replaces changed records and drops deleted records.
    deleted_registry_names = set()

    def add(key: str, name: str, description: str, url: str, source: str, raw: dict, version="1.0.0"):
        name = str(name or "").strip()
        if not name:
            return
        repository_identity = github_repository(url)
        alias_identity = f"{repository_identity}::{slugify(name).lower()}" if repository_identity else ""
        if key.startswith("registry:"):
            canonical = key.lower()
        else:
            canonical = alias_identity or key.lower()
            registry_match = next(
                (identity for identity, candidate in merged.items() if candidate.get("aliasIdentity") == alias_identity and alias_identity),
                None,
            )
            if registry_match:
                canonical = registry_match
        entry = merged.setdefault(canonical, {
            "identity": canonical,
            "aliasIdentity": alias_identity,
            "name_en": name,
            "description_en": str(description or "").strip(),
            "version": str(version or "1.0.0"),
            "repository": url or "",
            "sources": [],
            "runtimeMode": "unknown",
            "authentication": "unknown",
            "license": "",
            "author": "",
            "registryName": key.removeprefix("registry:") if key.startswith("registry:") else "",
            "registryUpdatedAt": "",
            "registryStatus": "unknown",
        })
        if source not in entry["sources"]:
            entry["sources"].append(source)
        if source == "official-mcp-registry":
            entry["name_en"] = name
            if description:
                entry["description_en"] = str(description).strip()
        elif not entry["description_en"] and description:
            entry["description_en"] = str(description).strip()
        if url and (not entry["repository"] or github_repository(url)):
            entry["repository"] = url
        if alias_identity and (source == "official-mcp-registry" or not entry.get("aliasIdentity")):
            entry["aliasIdentity"] = alias_identity
        inferred_runtime = infer_runtime(raw)
        entry["runtimeMode"] = inferred_runtime if inferred_runtime != "unknown" else entry["runtimeMode"]
        auth = raw.get("auth", {})
        if isinstance(auth, dict) and auth.get("type") in {"none", "api-key", "oauth", "credentials"}:
            entry["authentication"] = auth["type"]
        entry["license"] = entry["license"] or str(raw.get("license") or "")
        entry["author"] = entry["author"] or str(raw.get("provider") or raw.get("publisher") or "")
        if raw.get("version") and (source == "official-mcp-registry" or not entry["version"]):
            entry["version"] = str(raw["version"])
        if source == "official-mcp-registry":
            entry["registry"] = {
                key: raw[key]
                for key in ("websiteUrl", "documentationUrl", "remotes", "packages")
                if raw.get(key)
            }
        elif raw.get("server"):
            entry["registry"] = raw["server"]
        meta = raw.get("_registryMeta", {})
        if meta.get("updatedAt"):
            entry["registryUpdatedAt"] = max(entry["registryUpdatedAt"], meta["updatedAt"])
        if meta.get("status"):
            entry["registryStatus"] = meta["status"]

    for previous in previous_abilities.values():
        source = previous.get("source", {})
        registry_name = source.get("registryName")
        if previous.get("type") != "mcp" or not registry_name:
            continue
        english = previous.get("detail", {}).get("i18n", {}).get("en", {})
        add(
            "registry:" + registry_name,
            english.get("name") or previous.get("name", registry_name),
            english.get("description") or previous.get("description", ""),
            source.get("repository", ""),
            "official-mcp-registry",
            {
                "transport": [previous.get("mcpMetadata", {}).get("runtimeMode", "unknown")],
                "_registryMeta": {"status": source.get("registryStatus", "unknown")},
            },
            previous.get("version", "1.0.0"),
        )
        identity = next((candidate for candidate in merged.values() if candidate.get("registryName") == registry_name), None)
        if identity:
            identity["registryName"] = registry_name
            identity["registryUpdatedAt"] = source.get("registryUpdatedAt", "")
            identity["license"] = previous.get("license", "")
            identity["author"] = previous.get("author", "")
            identity["authentication"] = previous.get("mcpMetadata", {}).get("authentication", "unknown")

    registry_records = registry_servers(previous_abilities)
    for server in registry_records:
        server_name = server.get("name", "")
        registry_meta = server.get("_registryMeta", {})
        if registry_meta.get("status") == "deleted":
            deleted_registry_names.add(server_name)
            continue
        repository = server.get("repository", {})
        source_url = repository.get("url", "") if isinstance(repository, dict) else ""
        add("registry:" + server_name, server.get("title") or server_name, server.get("description", ""), source_url, "official-mcp-registry", {**server, "_registryMeta": registry_meta}, server.get("version"))

    if deleted_registry_names:
        for identity in list(merged):
            candidate = merged[identity]
            if candidate.get("registryName") not in deleted_registry_names:
                continue
            candidate["sources"] = [source for source in candidate["sources"] if source != "official-mcp-registry"]
            candidate["registryName"] = ""
            if not candidate["sources"]:
                del merged[identity]

    safe_log("Fetching mcpHQ and TensorBlock indexes…")
    for row in fetch_json(MCP_COLLECTION_SOURCES["mcphq"]):
        add("mcphq:" + row.get("name", ""), row.get("name"), row.get("description"), row.get("url", ""), "mcpHQ", row)
    for row in fetch_json(MCP_COLLECTION_SOURCES["tensorblock"]):
        links = row.get("links", {})
        url = links.get("repo") or links.get("primary") or links.get("homepage") or ""
        add("tensorblock:" + row.get("id", row.get("name", "")), row.get("name"), row.get("description"), url, "TensorBlock", row)

    safe_log("Fetching punkpeye directory…")
    readme = fetch_text(MCP_COLLECTION_SOURCES["punkpeye"])
    for line in readme.splitlines():
        if not re.match(r"\s*[-*+]\s+", line):
            continue
        urls = re.findall(r"https?://github\.com/[^\s)\]>]+", line)
        if not urls:
            continue
        name_match = re.match(r"\s*[-*+]\s+\[([^]]+)\]", line)
        name = name_match.group(1) if name_match else github_repository(urls[0]).split("/")[-1]
        description = re.sub(r"\[[^]]+\]\([^)]*\)", "", line).lstrip("-*+ ").strip()
        add("punkpeye:" + github_repository(urls[0]), name, description, urls[0], "punkpeye", {})

    return sorted(merged.values(), key=lambda item: item["identity"])


def suggest_mcp_classification(name: str, description: str) -> dict:
    """Automatic browsing hints only: no permission or installability inference."""
    rules = (
        ("cad-3d", ("cad", "blender", "freecad", "solidworks", "3d", "mesh", "modeling"), "3d-modeling"),
        ("data-databases", ("database", "postgres", "postgresql", "mysql", "sqlite", "sql", "warehouse"), "database"),
        ("developer-tools", ("github", "gitlab", "git", "code", "repository", "issue", "pull request", "debug", "compiler"), "developer-tools"),
        ("web-search", ("search", "browser", "web", "fetch", "crawl", "internet"), "search"),
        ("knowledge-memory", ("memory", "knowledge", "notion", "wiki", "document"), "documents"),
        ("communication", ("slack", "discord", "email", "telegram", "teams", "messaging"), "communication"),
        ("creative-media", ("image", "video", "audio", "music", "design", "media"), None),
        ("automation", ("automation", "workflow", "orchestration"), "automation"),
        ("productivity", ("calendar", "tasks", "todo", "schedule"), None),
        ("system-tools", ("filesystem", "shell", "terminal", "process", "system"), "filesystem"),
        ("ai-agents", ("llm", "model", "agent", "prompt", "inference"), "ai"),
    )
    def contains(text, word):
        return re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", text.lower()) is not None
    # The project name is stronger evidence than a passing mention in its description.
    for text in (name, description):
        for category, keywords, primary_tag in rules:
            if any(contains(text, word) for word in keywords):
                tags = [primary_tag] if primary_tag else []
                for word, tag in (("blender", "blender"), ("freecad", "freecad"), ("solidworks", "solidworks"), ("cad", "cad"), ("git", "git"), ("github", "git"), ("issue", "issue-tracking"), ("browser", "browser"), ("memory", "memory"), ("email", "email")):
                    if contains(name + " " + description, word):
                        tags.append(tag)
                return {"category": category, "tags": [tag for tag in dict.fromkeys(tags) if tag in MCP_FUNCTION_TAGS][:3]}
    return {"category": "uncategorized", "tags": []}


def translate_mcp_fields(servers: dict[str, dict], previous_abilities: dict[str, dict]) -> dict[str, dict[str, str]]:
    """Translate MCP names/descriptions and reuse only verified Chinese cache entries."""
    if not API_KEY:
        safe_log("API_567_KEY is unavailable; MCP names and descriptions remain in their source language")
        return {}
    translations: dict[str, dict[str, str]] = {}
    pending_keys = []
    pending_texts = []
    for slug, server in servers.items():
        previous = previous_abilities.get(slug, {})
        i18n = previous.get("detail", {}).get("i18n", {})
        fields = {
            "description": server.get("description_en", ""),
            "name": server.get("name_en") or server.get("name") or "",
        }
        for field, source_text in fields.items():
            if not source_text:
                continue
            translations.setdefault(slug, {})
            if has_chinese(source_text):
                translations[slug][field] = source_text
                continue
            if field == "name" and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source_text.strip()):
                # Registry names that are just owner/repository identifiers are labels, not prose.
                translations[slug][field] = source_text
                continue
            old_english = i18n.get("en", {}).get(field)
            old_chinese = i18n.get("zh", {}).get(field)
            if old_english == source_text and old_chinese and has_chinese(old_chinese):
                translations[slug][field] = old_chinese
            else:
                pending_keys.append((slug, field))
                pending_texts.append(source_text)
    if pending_texts:
        translated = translate_texts(pending_texts, "MCP names/descriptions")
        for (slug, field), text in zip(pending_keys, translated):
            translations.setdefault(slug, {})[field] = text
    return translations


def translate_mcp_descriptions(servers: dict[str, dict], previous_abilities: dict[str, dict]) -> dict[str, str]:
    """Compatibility helper retained for callers that only need description fields."""
    fields = translate_mcp_fields(servers, previous_abilities)
    return {slug: value["description"] for slug, value in fields.items() if "description" in value}


def write_mcp_record(mcp: dict, previous_abilities: dict[str, dict], translated_fields: dict[str, dict[str, str]], reviewed_metadata: dict | None = None) -> dict:
    slug = mcp["slug"]
    upstream = mcp.get("upstream")
    discovery = mcp.get("discovery")
    previous = previous_abilities.get(slug, {})
    localized_fields = translated_fields.get(slug, {})
    if isinstance(localized_fields, str):
        localized_fields = {"description": localized_fields}
    description = localized_fields.get("description", (upstream or discovery or {}).get("description_en") or mcp["description"])
    source_name = discovery["name_en"] if discovery else mcp["name"]
    localized_name = localized_fields.get("name", mcp["name"])
    version = upstream["package_version"] if upstream else mcp.get("version", "1.0.0")
    reviewed = reviewed_metadata if reviewed_metadata is not None else json.loads((REPO_ROOT / "mcp-curation.json").read_text(encoding="utf-8"))
    metadata = reviewed.get(slug)
    installable = metadata is not None and bool(metadata.get("installable"))
    if discovery:
        installable = False
        version = discovery.get("version", version)
    validate_ability({"type": "mcp", "slug": slug, "name": mcp["name"], "description": description, "version": version, "source": {"path": "mcps/discovery"}})
    if installable:
        mcp_dir = MCPS_DEST_DIR / slug
        if mcp_dir.is_symlink() or (mcp_dir / "mcp.json").is_symlink():
            raise ValueError(f"Refusing to write through local symlink: {mcp_dir}")
        pending_mcp = json.dumps({
            "schemaVersion": 1, "slug": slug, "version": version,
            "server": upstream["server"] if upstream else mcp["server"], "parameters": [],
        }, indent=2, ensure_ascii=False)
        digest = package_digest(mcp_dir, {"mcp.json": pending_mcp.encode("utf-8")})
        source_path = f"mcps/{slug}"
    else:
        digest = hashlib.sha256(json.dumps({key: value for key, value in (discovery or {}).items() if key != "registryUpdatedAt"}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        source_path = "mcps/discovery"
    config_version = previous.get("configVersion", 1)
    if previous and previous.get("source", {}).get("contentSha256") != digest:
        config_version += 1
    automatic = suggest_mcp_classification(discovery["name_en"] if discovery else mcp["name"], (upstream or discovery or {}).get("description_en", mcp["description"]))
    category = metadata.get("category", automatic["category"]) if metadata else automatic["category"]
    if category not in MCP_MAIN_CATEGORIES:
        raise ValueError(f"Uncontrolled MCP category for {slug}: {category}")
    tags = metadata.get("tags", automatic["tags"]) if metadata else automatic["tags"]
    if len(tags) > 3 or any(tag not in MCP_FUNCTION_TAGS for tag in tags):
        raise ValueError(f"Invalid MCP feature tags for {slug}: {tags}")
    metadata = metadata or {}
    mcp_metadata = {
        "runtimeMode": metadata.get("runtimeMode", discovery.get("runtimeMode", "unknown") if discovery else "unknown"),
        "platforms": metadata.get("platforms", ["unknown"]),
        "permissionScopes": metadata.get("permissionScopes", ["unknown"]),
        "authentication": metadata.get("authentication", discovery.get("authentication", "unknown") if discovery else "unknown"),
        "publisherType": metadata.get("publisherType", "unknown"),
        "installable": installable,
    }
    category_labels = {
        "ai-agents": "AI 与 Agent", "automation": "自动化", "cad-3d": "CAD 与 3D",
        "communication": "沟通协作", "creative-media": "创意与媒体", "data-databases": "数据与数据库",
        "developer-tools": "开发工具", "knowledge-memory": "知识与记忆", "productivity": "效率工具",
        "system-tools": "系统工具", "web-search": "网页与搜索", "uncategorized": "未分类",
    }
    category_labels_en = {
        "ai-agents": "AI and agents", "automation": "Automation", "cad-3d": "CAD and 3D",
        "communication": "Communication", "creative-media": "Creative and media", "data-databases": "Data and databases",
        "developer-tools": "Developer tools", "knowledge-memory": "Knowledge and memory", "productivity": "Productivity",
        "system-tools": "System tools", "web-search": "Web and search", "uncategorized": "Uncategorized",
    }
    localized = category_labels[category]
    details = {
        "zh": {"name": localized_name, "description": description, "tags": tags},
    }
    if upstream or discovery:
        details["en"] = {"name": source_name, "description": (upstream or discovery)["description_en"], "tags": tags}
    source = {"path": source_path, "contentSha256": digest}
    if upstream:
        source.update({"repository": MCP_UPSTREAM["repository"], "upstreamPath": upstream["path"]})
    if discovery:
        source.update({"repository": safe_https_url(discovery.get("repository", "")), "upstreamSources": discovery.get("sources", []), "registryName": discovery.get("registryName", "")})
        source["catalogIdentity"] = discovery.get("identity", "")
        source["catalogAliasIdentity"] = discovery.get("aliasIdentity", "")
        if discovery.get("registryUpdatedAt"):
            source["registryUpdatedAt"] = discovery["registryUpdatedAt"]
        if discovery.get("registryStatus") and discovery["registryStatus"] != "unknown":
            source["registryStatus"] = discovery["registryStatus"]
    links = []
    repository_url = safe_https_url(discovery.get("repository", "")) if discovery else ""
    if repository_url:
        links.append({"key": "repository", "value": repository_url})
    if discovery and discovery.get("registryName"):
        links.append({"label": "MCP Registry", "value": "https://registry.modelcontextprotocol.io/v0.1/servers/" + urllib.parse.quote(discovery["registryName"], safe="") + "/versions/latest"})
    if discovery:
        registry = discovery.get("registry", {})
        if isinstance(registry, dict):
            docs_url = registry.get("websiteUrl") or registry.get("documentationUrl")
            safe_docs_url = safe_https_url(docs_url)
            if safe_docs_url:
                links.append({"key": "docs", "value": safe_docs_url})
            for remote in registry.get("remotes", []):
                endpoint = safe_https_url(remote.get("url", ""))
                if endpoint:
                    links.append({"label": f"MCP endpoint ({remote.get('type', 'remote')})", "value": endpoint})
            for package in registry.get("packages", []):
                identifier = package.get("identifier", "")
                package_type = package.get("registryType", "")
                if package_type == "npm" and identifier:
                    package_url = "https://www.npmjs.com/package/" + urllib.parse.quote(identifier, safe="@")
                elif package_type == "pypi" and identifier:
                    package_url = "https://pypi.org/project/" + urllib.parse.quote(identifier, safe="")
                else:
                    package_url = identifier if isinstance(identifier, str) and identifier.startswith("https://") else ""
                if package_url:
                    links.append({"label": f"{package_type or 'MCP'} package", "value": package_url})
    if discovery and not discovery.get("registry"):
        preserved_meta = previous.get("detail", {}).get("meta", [])
        known_links = {(item.get("label"), item.get("key"), item.get("value")) for item in links}
        links.extend(
            item for item in preserved_meta
            if (item.get("label"), item.get("key"), item.get("value")) not in known_links
        )
    record = {
        "type": "mcp",
        "slug": slug,
        "name": localized_name,
        "description": description,
        "version": version,
        "configVersion": config_version,
        "license": mcp.get("license", "MIT" if upstream else ""),
        "author": mcp.get("author", "Model Context Protocol" if upstream else ""),
        "icon": "",
        "classificationSource": "maintainer" if metadata.get("category") else "automatic",
        "category": category,
        "categoryI18n": {"zh": localized, "en": category_labels_en[category]},
        "tags": tags,
        "mcpMetadata": mcp_metadata,
        "detail": {"i18n": details, "meta": links},
        "source": source,
    }

    validate_ability(record)
    if installable:
        mcp_dir.mkdir(parents=True, exist_ok=True)
        temporary = mcp_dir / ".mcp.json.tmp"
        try:
            temporary.write_text(pending_mcp, encoding="utf-8")
            temporary.replace(mcp_dir / "mcp.json")
        finally:
            temporary.unlink(missing_ok=True)
    return record


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
        safe_log(f"Skipping unreadable skill {skill_file}: {error}")
        return None
    if len(content.encode("utf-8")) > 512 * 1024:
        safe_log(f"Skipping oversized SKILL.md: {skill_file}")
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
    try:
        license_name = resolve_skill_license(skill_file.parent, frontmatter.get("license") or source["license"])
    except (ValueError, OSError):
        safe_log(f"Skipped skill with unreviewed license: {slug}")
        return None
    author = frontmatter.get("author") or frontmatter.get("metadata.author") or source["display_name"]
    version = frontmatter.get("version") or frontmatter.get("metadata.version") or "1.0.0"

    try:
        validate_ability({"type": "skill", "slug": slug, "name": display_name, "description": description, "version": version, "author": author, "license": license_name, "source": {"path": f"skills/{slug}"}})
    except ValueError as error:
        safe_log(f"Skipped skill {slug}: {error}")
        return None

    if scan_skill_tree(skill_file.parent):
        safe_log(f"Quarantined skill content: {slug}")
        return None
    SKILLS_DEST_DIR.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix=".skill-", dir=SKILLS_DEST_DIR))
    try:
        copy_skill_resources(skill_file.parent, destination)
    except (OSError, ValueError) as error:
        shutil.rmtree(destination)
        safe_log(f"Skipping skill with invalid or oversized resources {skill_file}: {error}")
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
    tags = [slug, category]
    record = {
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
        "source": {"path": f"skills/{slug}", "repository": source["repository"], "upstreamPath": upstream_path, "upstreamCommit": source.get("resolved_commit", ""), "contentSha256": digest},
    }

    try:
        validate_ability(record)
    except ValueError:
        shutil.rmtree(destination)
        return None
    with tempfile.TemporaryDirectory(prefix=".skill-backup-", dir=SKILLS_DEST_DIR) as backup:
        publish_staged_paths([(destination, SKILLS_DEST_DIR / slug)], Path(backup))
    used_slugs.add(slug)
    return record


def preserve_legacy_anbeime_abilities(previous_manifest: dict, used_slugs: set[str]) -> list[dict]:
    """Unlicensed legacy mirrors stay quarantined until redistribution is reviewed."""
    return []

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
    },
    {
        "slug": "git",
        "name": "Git 仓库工具",
        "description": "读取、搜索和修改 Git 仓库中的文件与版本历史。",
        "category": "Development",
        "category_zh": "编程研发",
        "tags": ["Git", "代码仓库", "MCP"],
        "server": {"type": "stdio", "command": "uvx", "args": ["mcp-server-git"]}
    },
    {
        "slug": "sequential-thinking",
        "name": "顺序思考",
        "description": "将复杂问题拆解为可逐步展开和修订的思考过程。",
        "category": "Development",
        "category_zh": "编程研发",
        "tags": ["推理", "规划", "MCP"],
        "server": {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]}
    },
    {
        "slug": "time",
        "name": "时间与时区",
        "description": "查询当前时间并在不同时区之间转换。",
        "category": "System",
        "category_zh": "系统工具",
        "tags": ["时间", "时区", "MCP"],
        "server": {"type": "stdio", "command": "uvx", "args": ["mcp-server-time"]}
    }
]

def generate_catalog(
    previous_manifest: dict,
    temp_root: Path,
    previous_discovery: dict | None = None,
    previous_package_manifest: dict | None = None,
) -> dict:
    global MCP_CLASSIFICATION_SUGGESTIONS
    abilities = []
    previous_abilities = {
        ability.get("slug"): ability
        for ability in previous_manifest.get("abilities", [])
        if isinstance(ability, dict) and isinstance(ability.get("slug"), str)
    }

    # 1. Sync supported first-party MCPs from the maintained upstream repository.
    curated_metadata = json.loads((REPO_ROOT / "mcp-curation.json").read_text(encoding="utf-8"))
    safe_log("=== Processing Curated and Official Upstream MCPs ===")
    upstream_mcps = load_mcp_upstream(temp_root)
    translated_mcp_descriptions = translate_mcp_fields(upstream_mcps, previous_abilities)
    curated_by_slug = {item["slug"]: item for item in CURATED_MCPS}
    mcp_records = []
    for slug, upstream in upstream_mcps.items():
        curated = curated_by_slug.get(slug)
        if curated is None:
            raise ValueError(f"Upstream MCP has no reviewed marketplace metadata: {slug}")
        mcp_records.append({**curated, "upstream": upstream})
    mcp_records.extend(item for item in CURATED_MCPS if item["slug"] not in upstream_mcps)
    for mcp in mcp_records:
        try:
            record = write_mcp_record(mcp, previous_abilities, translated_mcp_descriptions, curated_metadata)
        except ValueError:
            record = previous_abilities.get(mcp["slug"])
            if not record:
                safe_log(f"Skipped invalid MCP: {mcp['slug']}")
                continue
            validate_ability(record)
        abilities.append(record)
        safe_log(f"Processed MCP: {record['slug']} ({record['version']})")

    safe_log("\n=== Discovering community and Registry MCP candidates ===")
    candidates = collect_mcp_candidates(previous_abilities)
    curated_slugs = set(curated_by_slug)
    used_slugs = {item.get("slug", "") for item in abilities} | set(previous_abilities)
    previous_candidate_slugs = {
        identity: slug
        for slug, item in previous_abilities.items()
        if item.get("type") == "mcp"
        for identity in (item.get("source", {}).get("catalogIdentity"), item.get("source", {}).get("catalogAliasIdentity"))
        if identity
    }
    discovery_by_slug = {}
    for candidate in candidates:
        base = slugify(candidate["name_en"]) or slugify(candidate["identity"].split("/")[-1]) or "mcp"
        if base in curated_slugs:
            continue
        previous_slug = previous_candidate_slugs.get(candidate["identity"]) or previous_candidate_slugs.get(candidate.get("aliasIdentity", ""))
        if previous_slug:
            used_slugs.discard(previous_slug)
            slug = previous_slug
        else:
            slug = base if base not in used_slugs else f"{base[:52].rstrip('-')}-{hashlib.sha1(candidate['identity'].encode()).hexdigest()[:10]}"
            slug = slug[:64].rstrip("-")
            if slug in used_slugs:
                slug = unique_slug(base[:50].rstrip("-"), candidate["identity"], used_slugs)
        used_slugs.add(slug)
        discovery = {
            **candidate,
            "slug": slug,
            "description_en": candidate["description_en"] or f"MCP server listed by {', '.join(candidate['sources'])}.",
        }
        discovery_by_slug[slug] = discovery
    safe_log(f"Merged discovery feeds into {len(discovery_by_slug)} candidate MCP entries")
    translated_discoveries = translate_mcp_fields(discovery_by_slug, previous_abilities)
    for slug, discovery in discovery_by_slug.items():
        try:
            record = write_mcp_record({
            "slug": slug,
            "name": discovery["name_en"],
            "description": discovery["description_en"],
            "license": discovery.get("license", ""),
            "author": discovery.get("author", ""),
            "discovery": discovery,
            }, previous_abilities, translated_discoveries, curated_metadata)
        except ValueError:
            record = previous_abilities.get(slug)
            if not record:
                safe_log(f"Skipped invalid discovery record: {slug}")
                continue
            try:
                validate_ability(record)
            except ValueError:
                continue
        abilities.append(record)

    suggestions = []
    for item in abilities:
        classification = curated_metadata.get(item.get("slug", ""), {})
        category_confirmed = classification.get("category") in MCP_MAIN_CATEGORIES
        tags_confirmed = "tags" in classification
        if item.get("type") != "mcp" or (category_confirmed and tags_confirmed):
            continue
        source = item.get("source", {})
        english = item.get("detail", {}).get("i18n", {}).get("en", {})
        proposed = suggest_mcp_classification(english.get("name", item.get("name", "")), english.get("description", item.get("description", "")))
        if not category_confirmed and not tags_confirmed and proposed["category"] == "uncategorized" and not proposed["tags"]:
            continue
        suggestions.append({
            "slug": item["slug"],
            "identity": source.get("registryName") or source.get("repository") or item["slug"],
            "name": item.get("name", ""),
            "sources": source.get("upstreamSources", []),
            "currentCategory": item.get("category", "uncategorized"),
            "currentTags": item.get("tags", []),
            "suggestedCategory": proposed["category"] if not category_confirmed else None,
            "suggestedTags": proposed["tags"] if not tags_confirmed else None,
            "categoryRequiresMaintainerApproval": not category_confirmed,
            "tagsRequireMaintainerApproval": not tags_confirmed,
        })
    MCP_CLASSIFICATION_SUGGESTIONS = suggestions
    safe_log(f"Wrote {len(suggestions)} classification suggestions for maintainer review")

    # 2. Collect portable skills from curated, license-declared upstreams.
    safe_log("\n=== Processing Skills from curated upstream repositories ===")
    seen_slugs = {ability["slug"] for ability in abilities}
    legacy_abilities = preserve_legacy_anbeime_abilities(previous_manifest, seen_slugs)
    abilities.extend(legacy_abilities)
    if legacy_abilities:
        safe_log(f"Preserved {len(legacy_abilities)} existing anbeime/skill entries pending license review")
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
        safe_log(f"Cloning {source['repository']}...")
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
        safe_log(f"Found {len(discovered)} SKILL.md files in {source['repository']}")
        translations = translate_skill_descriptions(source, checkout, discovered, previous_abilities)
        for skill_file in discovered:
            ability = write_skill(source, checkout, skill_file, seen_slugs, previous_abilities, translations)
            if ability is not None:
                abilities.append(ability)
                safe_log(f"Processed Skill: {ability['slug']} [{ability['category']}]")
            else:
                upstream_path = skill_file.relative_to(checkout).as_posix()
                for previous in previous_abilities.values():
                    if (previous.get("type") == "skill"
                        and previous.get("source", {}).get("repository") == source["repository"]
                        and previous.get("source", {}).get("upstreamPath") == upstream_path
                        and (SKILLS_DEST_DIR / previous["slug"] / "SKILL.md").is_file()
                        and redistribution_allowed(previous, SKILLS_DEST_DIR / previous["slug"])):
                        abilities.append(copy.deepcopy(previous))
                        safe_log(f"Retained previous mirror for skipped skill: {previous['slug']}")
                        break

    valid_abilities = []
    for item in abilities:
        try:
            validate_ability(item)
            if item["type"] == "skill" and not redistribution_allowed(item, SKILLS_DEST_DIR / item["slug"]):
                continue
            valid_abilities.append(item)
        except ValueError:
            safe_log("Skipped invalid generated ability")
    abilities = valid_abilities
    # 3. Write marketplace.json
    installable_abilities = [
        item for item in abilities
        if item.get("type") != "mcp" or item.get("mcpMetadata", {}).get("installable") is True
    ]
    discovery_abilities = sorted(
        (
            item for item in abilities
            if item.get("type") == "mcp" and item.get("mcpMetadata", {}).get("installable") is not True
        ),
        key=lambda item: item["slug"],
    )
    manifest = {
        "schemaVersion": 3,
        "name": "567-official",
        "displayName": "567 Agent 官方能力市场",
        "marketplaceVersion": next_marketplace_version(installable_abilities, previous_package_manifest or previous_manifest),
        "discoveryVersion": next_marketplace_version(discovery_abilities, previous_discovery),
        "repository": "https://github.com/Chinachani/567-agent-marketplace",
        "minAppVersion": "1.0.0",
        "abilities": installable_abilities,
        "discoveryAbilities": discovery_abilities,
    }

    return manifest


def serialize_manifest(manifest: dict) -> str:
    """Keep metadata readable while writing each ability as one compact JSON line."""
    header = {key: value for key, value in manifest.items() if key != "abilities"}
    serialized_header = json.dumps(header, indent=2, ensure_ascii=False)
    if header:
        serialized = serialized_header[:-2] + ',\n  "abilities": [\n'
    else:
        serialized = '{\n  "abilities": [\n'
    serialized += ",\n".join(
        "    " + json.dumps(ability, ensure_ascii=False, separators=(",", ":"))
        for ability in manifest.get("abilities", [])
    )
    serialized += "\n  ]\n}\n"
    size_bytes = len(serialized.encode("utf-8"))
    if size_bytes > MAX_MANIFEST_BYTES:
        raise ValueError(
            f"Marketplace manifest is {size_bytes / (1024 * 1024):.2f} MiB; "
            f"the safe limit is {MAX_MANIFEST_BYTES / (1024 * 1024):.0f} MiB. "
            "Shard the discovery catalog before publishing more entries."
        )
    return serialized


def build_discovery_distribution(manifest: dict, output_dir: Path) -> dict:
    """Write a small index and independently verifiable MCP discovery shards."""
    abilities = copy.deepcopy(sorted(manifest.get("discoveryAbilities", []), key=lambda item: item["slug"]))
    if len(abilities) > DISCOVERY_MAX_RECORDS:
        raise ValueError("Discovery record capacity exceeded; keep the previous published catalog")
    for ability in abilities:
        ability.get("source", {}).pop("registryUpdatedAt", None)
    search_dir = output_dir / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    search_shards = []
    shards_dir = output_dir / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)
    shards = []
    grouped = {}
    for ability in abilities:
        category = ability.get("category") or "uncategorized"
        grouped.setdefault(category, []).append(ability)
    for category, category_abilities in sorted(grouped.items()):
        chunks = []
        current = []
        # Serialize each record once, instead of repeatedly serializing a growing 500-item array.
        envelope = {"schemaVersion": 1, "catalogVersion": manifest["discoveryVersion"], "category": category, "abilities": []}
        envelope_bytes = len(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        current_bytes = envelope_bytes
        for ability in category_abilities:
            encoded_size = len(json.dumps(ability, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            if envelope_bytes + encoded_size > DISCOVERY_SHARD_BYTES:
                raise ValueError(f"MCP discovery record is too large to publish: {ability['slug']}")
            addition = encoded_size + (1 if current else 0)
            if current and (len(current) >= DISCOVERY_SHARD_ITEMS or current_bytes + addition > DISCOVERY_SHARD_BYTES):
                chunks.append(current)
                current = []
                current_bytes = envelope_bytes
                addition = encoded_size
            current.append(ability)
            current_bytes += addition
        if current:
            chunks.append(current)
        for shard_index, chunk in enumerate(chunks):
            shard_name = f"mcp-{category}-{shard_index:04d}.json"
            payload = json.dumps({
                "schemaVersion": 1,
                "catalogVersion": manifest["discoveryVersion"],
                "category": category,
                "abilities": chunk,
            }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            (shards_dir / shard_name).write_bytes(payload)
            shards.append({
                "path": f"shards/{shard_name}",
                "category": category,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "sizeBytes": len(payload),
                "count": len(chunk),
            })
            # Search rows contain only searchable presentation and a checked detail locator.
            summaries = []
            for item in chunk:
                summary = {key: item.get(key, "") for key in (
                    "type", "slug", "name", "version", "configVersion", "category", "tags", "classificationSource"
                )}
                if summary.get("classificationSource") not in {"automatic", "maintainer"}:
                    summary.pop("classificationSource", None)
                summary.update({"description": item.get("description", "")[:320], "license": "", "author": "", "icon": "", "detail": {},
                    "mcpMetadata": {"installable": False}, "detailShard": f"shards/{shard_name}"})
                localized = item.get("detail", {}).get("i18n", {})
                summary["detail"] = {"i18n": {locale: {key: value for key, value in {
                    "name": data.get("name", item["name"]), "description": data.get("description", "")[:320]
                }.items() if value != summary.get(key)} for locale, data in localized.items() if locale in {"en", "zh"}}}
                summaries.append(summary)
            search_payload = json.dumps({"schemaVersion": 1, "catalogVersion": manifest["discoveryVersion"],
                "category": category, "abilities": summaries}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(search_payload) > DISCOVERY_SHARD_BYTES:
                raise ValueError("Search shard exceeds byte capacity")
            (search_dir / shard_name).write_bytes(search_payload)
            search_shards.append({"path": f"search/{shard_name}", "category": category,
                "sha256": hashlib.sha256(search_payload).hexdigest(), "sizeBytes": len(search_payload), "count": len(chunk)})
    category_counts = {}
    for ability in abilities:
        category = ability.get("category") or "uncategorized"
        category_counts[category] = category_counts.get(category, 0) + 1
    total_bytes = sum(shard["sizeBytes"] for shard in shards)
    if len(shards) > DISCOVERY_MAX_SHARDS or total_bytes > DISCOVERY_MAX_BYTES:
        raise ValueError("Discovery shard/byte capacity exceeded; keep the previous published catalog")
    if max(len(abilities) / DISCOVERY_MAX_RECORDS, len(shards) / DISCOVERY_MAX_SHARDS, total_bytes / DISCOVERY_MAX_BYTES) >= 0.8:
        safe_log("Discovery capacity warning: extend the versioned client/publisher contract before the next limit")
    index = {
        "schemaVersion": 1,
        "catalogVersion": manifest["discoveryVersion"],
        "marketplaceVersion": manifest["marketplaceVersion"],
        "recordCount": len(abilities),
        "categories": category_counts,
        "shards": shards,
        "searchShards": search_shards,
    }
    (output_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "classification-suggestions.json").write_text(
        json.dumps({"items": MCP_CLASSIFICATION_SUGGESTIONS}, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return index


def main():
    global SKILLS_DEST_DIR, MCPS_DEST_DIR
    load_translation_checkpoint()
    previous_path = REPO_ROOT / "marketplace.json"
    # A malformed existing manifest needs repair, not replacement by an empty one.
    previous_manifest = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.is_file() else {}
    previous_discovery_path = REPO_ROOT / ".marketplace-state.json.gz"
    if previous_discovery_path.is_file():
        with gzip.open(previous_discovery_path, "rt", encoding="utf-8") as handle:
            previous_discovery = json.load(handle)
    else:
        # First migration run: the current checked-in manifest still contains
        # the full discovery catalog and can seed stable IDs/translations.
        previous_discovery = previous_manifest
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
            combined_previous = dict(previous_manifest)
            combined_previous["abilities"] = [
                *previous_manifest.get("abilities", []),
                *previous_discovery.get("abilities", []),
            ]
            manifest = generate_catalog(combined_previous, temp_root, previous_discovery, previous_manifest)
            current_slugs = {item["slug"] for item in manifest["abilities"] if item["type"] == "skill"}
            # Only remove previously managed upstream directories. Preserve legacy
            # mirrors and unrelated local packages when pruning removed upstream skills.
            for item in previous_manifest.get("abilities", []):
                slug = item.get("slug", "")
                if (item.get("type") == "skill"
                    and (item.get("source", {}).get("repository") in repositories or item.get("author") == "anbeime / 567 Agent" or item.get("source", {}).get("repository") == "anbeime/skill")
                    and slug not in current_slugs
                    and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug)):
                    path = SKILLS_DEST_DIR / slug
                    if path.is_symlink():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path)
            replacements = [(SKILLS_DEST_DIR, skills_destination), (MCPS_DEST_DIR, mcps_destination)]
            discovery_abilities = manifest.pop("discoveryAbilities")
            package_manifest = dict(manifest)
            package_manifest["abilities"] = manifest["abilities"]
            validate_manifest(package_manifest)
            serialized = serialize_manifest(package_manifest)
            for index, relative_path in enumerate(("marketplace.json", ".567agent/marketplace.json", ".vetta/marketplace.json")):
                staged = temp_root / f"manifest-{index}.json"
                staged.write_text(serialized, encoding="utf-8")
                replacements.append((staged, REPO_ROOT / relative_path))
            discovery_root = temp_root / "catalog-dist"
            discovery_root.mkdir()
            distribution_manifest = {**manifest, "discoveryAbilities": discovery_abilities}
            build_discovery_distribution(distribution_manifest, discovery_root)
            state_path = discovery_root / "catalog-state.json.gz"
            with gzip.open(state_path, "wt", encoding="utf-8", compresslevel=9) as handle:
                json.dump({"abilities": discovery_abilities, "marketplaceVersion": manifest["discoveryVersion"]}, handle, ensure_ascii=False, separators=(",", ":"))
            if TRANSLATION_CACHE:
                write_translation_checkpoint(discovery_root / "translation-cache.json.gz")
            replacements.append((discovery_root, REPO_ROOT / "catalog-dist"))
            publish_staged_paths(replacements, temp_root / "backups")
            legacy_suggestions = REPO_ROOT / ".567agent" / "mcp-classification-suggestions.json"
            if legacy_suggestions.exists():
                legacy_suggestions.unlink()
        finally:
            SKILLS_DEST_DIR, MCPS_DEST_DIR = skills_destination, mcps_destination
    safe_log(f"\nSuccessfully generated installable marketplace with {len(manifest['abilities'])} abilities and {len(discovery_abilities)} MCP discovery records!")


if __name__ == "__main__":
    main()
