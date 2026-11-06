"""Low-concurrency, unauthenticated Index-Translate fallback.

Protocol reference: bilibili/Index-Translate inference/llm/call_api.py.
Only public marketplace names/descriptions are sent; primary credentials are
never accepted by this client. Network calls are injected for offline tests.
"""
import json
import re
import threading
import time
import urllib.error
import urllib.request

INDEX_TRANSLATE_URL = "https://index-translate.bilibili.com/v1/chat/completions"
INDEX_TRANSLATE_MODEL = "Index-Translate-35B-A3B"
RESPONSE_BYTES = 2 * 1024 * 1024
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
INDEX_BATCH_ITEMS = 4


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Index-Translate returned a duplicate JSON key")
        result[key] = value
    return result


class TranslationCircuitOpen(RuntimeError):
    """The requested translation provider exhausted its per-run safeguards."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_translation_request(request, timeout):
    # Keep the public text at the explicitly configured service origin.
    return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)


class IndexTranslateFallback:
    def __init__(self, *, log, retry_delay, failure_limit=8, request_limit=5000,
                 transport=None, sleep=None, clock=None):
        self.log = log
        self.retry_delay = retry_delay
        self.failure_limit = failure_limit
        self.request_limit = request_limit
        self.transport = transport or open_translation_request
        self.sleep = sleep or time.sleep
        self.clock = clock or time.monotonic
        self._lock = threading.Lock()
        self.failures = 0
        self.requests = 0
        self.circuit_open = False
        self._next_request_at = 0.0
        self._announced = False

    def request_batch(self, texts, max_tokens, *, names=False):
        # The public gateway times out on large generic chat batches. Its native
        # translation prompt reliably preserves object keys in small groups.
        result = []
        for start in range(0, len(texts), INDEX_BATCH_ITEMS):
            source = {str(index): text for index, text in enumerate(texts[start:start + INDEX_BATCH_ITEMS], start)}
            if names:
                constraints = (
                    "请将 AI 能力名称翻译成简体中文。保留 JSON 的数字 key，每个 value 改为一个对象，"
                    "包含 translation 和 keepOriginal。品牌/专名/缩写组成的名称保留原文且 keepOriginal 为 true；"
                    "有普通功能词则翻译这些词并令 keepOriginal 为 false。"
                    '例如输入 {"0":"FreeCAD","1":"Database Tool"} 应输出 '
                    '{"0":{"translation":"FreeCAD","keepOriginal":true},'
                    '"1":{"translation":"数据库工具","keepOriginal":false}}。只输出 JSON。'
                )
            else:
                constraints = (
                    "严格保留 JSON 对象的所有 key，仅将字符串 value 翻译成自然简体中文，保留常见产品名。"
                    "请以相同的 JSON 格式输出翻译结果，key 保持不变，value 为对应译文。只输出 JSON。"
                )
            content = self.request([
                {"role": "system", "content": constraints},
                {"role": "user", "content": json.dumps(source, ensure_ascii=False)},
            ], min(max_tokens, max(1024, sum(len(text) for text in source.values()) * 2)))
            candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
            parsed = json.loads(candidate, object_pairs_hook=_unique_object)
            if not isinstance(parsed, dict) or set(parsed) != set(source):
                raise ValueError("Index-Translate changed or omitted batch ids")
            for item_id, original in source.items():
                value = parsed[item_id]
                if names:
                    if (not isinstance(value, dict) or not isinstance(value.get("translation"), str)
                            or type(value.get("keepOriginal")) is not bool):
                        raise ValueError("Invalid Index-Translate name response")
                    if value["keepOriginal"] and value["translation"] != original:
                        raise ValueError("Index-Translate changed a preserved name")
                    result.append({"id": int(item_id), "translation": value["translation"], "keepOriginal": value["keepOriginal"]})
                else:
                    if not isinstance(value, str):
                        raise ValueError("Invalid Index-Translate description response")
                    result.append({"id": int(item_id), "translation": value})
        return json.dumps(result, ensure_ascii=False)

    def request(self, messages, max_tokens):
        source = "\n\n".join(item["content"] for item in messages if item["role"] == "user")
        constraints = "\n".join(item["content"] for item in messages if item["role"] == "system")
        prompt = ("请将以下文本翻译成简体中文，并严格遵循约束要求。\n\n【源文】\n"
                  + source + "\n\n【约束要求】\n" + constraints
                  + "\n\n只输出符合要求的翻译结果，不要解释。")
        payload = {"model": INDEX_TRANSLATE_MODEL, "messages": [{"role": "user", "content": prompt}],
                   "temperature": 0.0, "max_tokens": max_tokens, "stream": False,
                   "chat_template_kwargs": {"enable_thinking": False}}
        request = urllib.request.Request(
            INDEX_TRANSLATE_URL, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "567-Agent-Marketplace/1.0"},
        )
        # One in-flight request, including retries, across all translation workers.
        with self._lock:
            for attempt in range(3):
                if self.circuit_open:
                    raise TranslationCircuitOpen("Index-Translate circuit is open")
                if self.requests >= self.request_limit:
                    self.circuit_open = True
                    self.log("Index-Translate request budget exhausted; remaining translations deferred", flush=True)
                    raise TranslationCircuitOpen("Index-Translate request budget exhausted")
                if not self._announced:
                    self.log("Using Index-Translate public fallback (one worker, no API key)", flush=True)
                    self._announced = True
                wait = self._next_request_at - self.clock()
                if wait > 0:
                    self.sleep(wait)
                self._next_request_at = self.clock() + 1.0
                self.requests += 1
                try:
                    with self.transport(request, timeout=45) as response:
                        raw = response.read(RESPONSE_BYTES + 1)
                    if len(raw) > RESPONSE_BYTES:
                        raise ValueError("response exceeds byte limit")
                    choice = json.loads(raw)["choices"][0]
                    content = choice["message"]["content"]
                    if not isinstance(content, str) or choice.get("finish_reason") == "length":
                        raise ValueError("invalid or truncated translation")
                    if "</think>" in content:
                        content = content.split("</think>", 1)[1]
                    if not content.strip() or "<think>" in content:
                        raise ValueError("empty translation or unfinished reasoning")
                    self.failures = 0
                    return content.strip()
                except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError) as error:
                    self.failures += 1
                    status = error.code if isinstance(error, urllib.error.HTTPError) else None
                    permanent = status is not None and status not in RETRYABLE_STATUS
                    reason = f"HTTP {status}" if status is not None else type(error).__name__
                    self.log(f"Index-Translate request failed ({reason})", flush=True)
                    wait = self.retry_delay(error, attempt)
                    self._next_request_at = max(self._next_request_at, self.clock() + wait)
                    if isinstance(error, urllib.error.HTTPError):
                        error.close()
                    if permanent or self.failures >= self.failure_limit:
                        self.circuit_open = True
                        self.log("Index-Translate circuit opened; remaining translations deferred", flush=True)
                        raise TranslationCircuitOpen("Index-Translate circuit opened") from None
                    if attempt == 2:
                        raise urllib.error.URLError(f"Index-Translate failed after retries ({reason})") from None
                    self.log(f"Index-Translate retrying in {wait:.1f}s", flush=True)
