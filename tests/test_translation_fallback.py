import io
import json
import threading
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import sync_marketplace as sync
from translation_fallback import (
    INDEX_TRANSLATE_MODEL, INDEX_TRANSLATE_URL, IndexTranslateFallback,
    TranslationCircuitOpen, _NoRedirect,
)


def response(content="中文译文", finish_reason="stop"):
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}).encode())


def error(status=503, retry_after="7"):
    return urllib.error.HTTPError(INDEX_TRANSLATE_URL, status, "unavailable", {"Retry-After": retry_after}, None)


class TranslationFallbackTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("API_KEY", "primary-test-secret"), ("INDEX_TRANSLATE_ENABLED", True),
                            ("INDEX_TRANSLATE_CLIENT", None), ("TRANSLATION_CIRCUIT_FAILURES", 0),
                            ("TRANSLATION_CIRCUIT_OPEN", False), ("TRANSLATION_CIRCUIT_LOGGED", False)):
            setting = patch.object(sync, name, value)
            setting.start()
            self.addCleanup(setting.stop)
        self.now = 0.0
        self.sleeps = []
        self.log = Mock()
        self.transport = Mock(side_effect=lambda *args, **kwargs: response())
        self.client = IndexTranslateFallback(
            log=self.log, retry_delay=sync._translation_retry_delay, transport=self.transport,
            sleep=self.sleep, clock=lambda: self.now,
        )
        sync.INDEX_TRANSLATE_CLIENT = self.client

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def test_primary_success_never_calls_public_service(self):
        with patch.object(sync, "_request_primary_translation", return_value="主接口译文"):
            self.assertEqual(sync._request_translation([], 512), "主接口译文")
        self.transport.assert_not_called()

    def test_primary_errors_and_open_circuit_fall_back_without_sharing_credentials(self):
        for failure in (error(503), error(401), TimeoutError(), ValueError("bad JSON"), TranslationCircuitOpen()):
            with self.subTest(failure=type(failure).__name__), patch.object(sync, "_request_primary_translation", side_effect=failure):
                result = sync._request_translation([{"role": "system", "content": "保留 id，返回 JSON"},
                                                    {"role": "user", "content": "Example description"}], 1024)
                self.assertEqual(result, "中文译文")
        request = self.transport.call_args.args[0]
        self.assertEqual(request.full_url, INDEX_TRANSLATE_URL)
        self.assertIsNone(request.get_header("Authorization"))
        self.assertNotIn(sync.API_KEY, str(request.headers) + request.data.decode())
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], INDEX_TRANSLATE_MODEL)
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["max_tokens"], 1024)
        self.assertEqual(len(payload["messages"]), 1)
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertIn("保留 id，返回 JSON", payload["messages"][0]["content"])

    def test_primary_circuit_does_not_disable_healthy_backup_or_reset_on_backup_success(self):
        with patch.object(sync, "TRANSLATION_CIRCUIT_FAILURE_LIMIT", 1), \
             patch.object(sync.urllib.request, "urlopen", side_effect=TimeoutError()) as primary, \
             patch.object(sync.time, "sleep"):
            self.assertEqual(sync._request_translation([], 512), "中文译文")
            self.assertEqual(sync._request_translation([], 512), "中文译文")
        primary.assert_called_once()
        self.assertTrue(sync.TRANSLATION_CIRCUIT_OPEN)
        self.assertEqual(self.transport.call_count, 2)
        self.assertFalse(self.client.circuit_open)

    def test_backup_only_works_without_primary_key_and_preserves_cache(self):
        sync.TRANSLATION_CACHE.clear()
        self.addCleanup(sync.TRANSLATION_CACHE.clear)
        with patch.object(sync, "API_KEY", ""), patch.object(sync, "_request_primary_translation") as primary, \
             patch.object(sync, "_persist_translation_checkpoint"):
            self.assertEqual(sync.translate_texts(["Public feature description"], "descriptions"), ["中文译文"])
            self.assertEqual(sync.translate_texts(["Public feature description"], "descriptions"), ["中文译文"])
        primary.assert_not_called()
        self.transport.assert_called_once()

    def test_backup_disabled_preserves_existing_primary_failure_behavior(self):
        with patch.object(sync, "INDEX_TRANSLATE_ENABLED", False), \
             patch.object(sync, "_request_primary_translation", side_effect=TimeoutError()):
            with self.assertRaises(TimeoutError):
                sync._request_translation([], 512)
        self.transport.assert_not_called()

    def test_backup_retry_after_and_minimum_spacing_apply_across_requests(self):
        self.transport.side_effect = [error(429), response(), response()]
        self.assertEqual(self.client.request([], 512), "中文译文")
        self.assertEqual(self.client.request([], 512), "中文译文")
        self.assertEqual(self.sleeps, [7.0, 1.0])

    def test_exhausted_retry_keeps_cooldown_for_the_next_batch(self):
        self.transport.side_effect = [error(429), error(429), error(429), response()]
        with self.assertRaises(urllib.error.URLError):
            self.client.request([], 512)
        self.assertEqual(self.client.request([], 512), "中文译文")
        self.assertEqual(self.sleeps, [7.0, 7.0, 7.0])

    def test_backup_circuit_and_request_budget_stop_further_network_calls(self):
        self.client.failure_limit = 2
        self.transport.side_effect = lambda *args, **kwargs: (_ for _ in ()).throw(error(503))
        for _ in range(3):
            with self.assertRaises(TranslationCircuitOpen):
                self.client.request([], 512)
        self.assertEqual(self.transport.call_count, 2)
        self.client.circuit_open = False
        self.client.requests = self.client.request_limit
        with self.assertRaises(TranslationCircuitOpen):
            self.client.request([], 512)
        self.assertEqual(self.transport.call_count, 2)

    def test_all_providers_open_defer_without_success_cache(self):
        sync.TRANSLATION_CACHE.clear()
        self.addCleanup(sync.TRANSLATION_CACHE.clear)
        self.client.circuit_open = True
        with patch.object(sync, "_request_primary_translation", side_effect=TranslationCircuitOpen()), \
             patch.object(sync, "_persist_translation_checkpoint"), patch.object(sync, "safe_log") as log:
            self.assertEqual(sync.translate_texts(["Pending description"], "descriptions"), ["Pending description"])
        self.assertFalse(sync.TRANSLATION_CACHE)
        self.assertTrue(any("1 deferred by circuit/fallback budget" in call.args[0] for call in log.call_args_list))
        self.transport.assert_not_called()

    def test_invalid_http_payload_is_retried_and_thinking_is_removed(self):
        for invalid in (response(None), response("中文但被截断", "length"), response("<think>未完成"), io.BytesIO(b"not-json")):
            with self.subTest():
                self.transport.side_effect = [invalid, response("<think>reasoning</think>有效中文")]
                self.assertEqual(self.client.request([], 512), "有效中文")
        self.assertEqual(self.client.failures, 0)

    def test_batch_id_validation_and_name_preservation_work_through_backup(self):
        self.transport.side_effect = lambda *args, **kwargs: response(json.dumps({
            "1": {"translation": "建模工具", "keepOriginal": False}, "0": {"translation": "Blender", "keepOriginal": True},
        }))
        with patch.object(sync, "API_KEY", ""):
            result = sync._translate_batch(["Blender", "Modeling tool"], names=True)
        self.assertEqual(result, ["Blender", "建模工具"])
        self.assertEqual(result.preserved_names, {0})
        self.transport.side_effect = lambda *args, **kwargs: response('{"0":"中文","0":"重复"}')
        with patch.object(sync, "API_KEY", ""), patch.object(sync, "_reserve_single_fallback", return_value=False):
            result = sync._translate_batch(["first", "second"])
        self.assertEqual(result, ["first", "second"])
        self.assertEqual(result.deferred_count, 2)

    def test_small_batches_keep_global_ids_even_when_provider_reorders_keys(self):
        self.transport.side_effect = [response(json.dumps({str(i): f"中文{i}" for i in reversed(range(start, min(start + 4, 9)))}))
                                      for start in range(0, 9, 4)]
        result = json.loads(self.client.request_batch([f"Text {i}" for i in range(9)], 6000))
        self.assertEqual(result, [{"id": i, "translation": f"中文{i}"} for i in range(9)])
        self.assertEqual(self.transport.call_count, 3)

    def test_invalid_batch_ids_and_false_name_preservations_are_rejected(self):
        for content, names in ((json.dumps({"0": "中文"}), False),
                               (json.dumps({"0": "中文", "2": "错误 id"}), False),
                               ('{"0":"中文","0":"重复","1":"中文"}', False),
                               (json.dumps({"0": {"translation": "改名", "keepOriginal": True},
                                            "1": {"translation": "中文", "keepOriginal": False}}), True)):
            with self.subTest(content=content):
                self.transport.side_effect = lambda *args, **kwargs: response(content)
                with self.assertRaises(ValueError):
                    self.client.request_batch(["First", "Second"], 1024, names=names)

    def test_parallel_workers_use_only_one_fallback_connection(self):
        started, release = threading.Event(), threading.Event()
        calls = []

        def transport(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                started.set()
                self.assertTrue(release.wait(3))
            return response()

        self.client.transport = transport
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(self.client.request, [], 512) for _ in range(8)]
            try:
                self.assertTrue(started.wait(3))
                self.assertEqual(len(calls), 1)
            finally:
                release.set()
            self.assertEqual([future.result() for future in futures], ["中文译文"] * 8)
        self.assertEqual(self.sleeps, [1.0] * 7)

    def test_permanent_errors_disable_fallback_without_logging_body_or_redirecting(self):
        self.transport.side_effect = error(403)
        with self.assertRaises(TranslationCircuitOpen):
            self.client.request([], 512)
        self.transport.assert_called_once()
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test"))
        logs = " ".join(call.args[0] for call in self.log.call_args_list)
        self.assertNotIn(INDEX_TRANSLATE_URL, logs)
        self.assertNotIn(sync.API_KEY, logs)


if __name__ == "__main__":
    unittest.main()
