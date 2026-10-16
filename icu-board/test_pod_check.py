"""Reproducible Pod checker tests: mocked API, no sockets or real model calls.

Run with python3 -m unittest test_pod_check -v, or unittest discover.
"""
import contextlib
import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

import pod_check


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        return json.dumps(self.value).encode()


def basic(content="POD_OK"):
    return {"choices": [{"message": {"content": content}}]}


def native(patient="POD-SYNTH-001", extra=None):
    arguments = {"patient_id": patient}
    if extra:
        arguments.update(extra)
    return {"choices": [{"message": {"tool_calls": [{"id": "call-1", "type": "function",
             "function": {"name": "get_patient", "arguments": json.dumps(arguments)}}]}}]}


class PodCheckTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"LLM_BASE_URL": "https://pod.example/v1", "LLM_MODEL": "qwen-test",
                                         "LLM_API_KEY": "SECRET_TEST_ONLY"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_default_never_calls_model_even_when_configured(self):
        stream = io.StringIO()
        with patch.object(pod_check, "offline_checks", return_value=[pod_check.check("fixture", "pass", "ok")]), \
             patch.object(pod_check, "model_checks") as calls, contextlib.redirect_stdout(stream):
            code = pod_check.main([])
        self.assertEqual(code, 0)
        calls.assert_not_called()
        result = json.loads(stream.getvalue())
        self.assertFalse(result["real_model_call_verified"])
        self.assertFalse(result["native_tool_call_verified"])

    def test_pending_returns_nonzero(self):
        with patch.object(pod_check, "offline_checks", return_value=[pod_check.check("fixture", "pending", "pending")]), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pod_check.main([]), 1)

    def test_missing_configuration_makes_no_requests(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(pod_check.urllib.request, "urlopen") as calls:
            result = pod_check.model_checks(1)
        calls.assert_not_called()
        self.assertEqual(result[0]["status"], "fail")
        self.assertTrue(all(item["status"] == "unverified" for item in result[1:]))

    def test_legacy_configuration_fallback_and_llm_priority(self):
        with patch.dict(os.environ, {"KHDP_BASE_URL": "https://legacy.example/v1", "KHDP_MODEL": "glm-legacy",
                                    "KHDP_API_KEY": "OLDKEY"}):
            self.assertEqual(pod_check.model_configuration(), ("https://pod.example/v1", "qwen-test", "SECRET_TEST_ONLY"))
        with patch.dict(os.environ, {"KHDP_BASE_URL": "https://legacy.example/v1", "KHDP_MODELS": "glm-first,qwen-second",
                                    "KHDP_API_KEY": "OLDKEY"}, clear=True):
            self.assertEqual(pod_check.model_configuration(), ("https://legacy.example/v1", "glm-first", "OLDKEY"))

    def test_native_success_uses_one_endpoint_and_only_synthetic_payload(self):
        captured = []

        def send(request, **kwargs):
            captured.append(request)
            body = json.loads(request.data)
            return Response(native() if "tools" in body else basic())

        with patch.object(pod_check.urllib.request, "urlopen", side_effect=send):
            result = pod_check.model_checks(1)
        self.assertTrue(all(item["status"] == "pass" for item in result))
        self.assertEqual(len(captured), 2)
        self.assertEqual({request.full_url for request in captured}, {"https://pod.example/v1/chat/completions"})
        self.assertIn("POD-SYNTH-001", captured[1].data.decode())
        self.assertNotIn("SECRET_TEST_ONLY", json.dumps(result))

    def test_tool_api_failure_stays_failed_and_hides_error_body(self):
        error = urllib.error.HTTPError("https://pod.example/SECRET_TEST_ONLY", 400,
                                       "SECRET_TEST_ONLY private response body", {}, None)
        with patch.object(pod_check.urllib.request, "urlopen", side_effect=[Response(basic()), error]):
            result = pod_check.model_checks(1)
        self.assertEqual(result[1]["status"], "pass")
        self.assertEqual(result[2]["status"], "fail")
        self.assertEqual(result[2]["http_status"], 400)
        self.assertNotIn("SECRET_TEST_ONLY", json.dumps(result))
        self.assertNotIn("private response body", json.dumps(result))

    def test_textual_tool_intent_is_not_native_success(self):
        with patch.object(pod_check.urllib.request, "urlopen", side_effect=[Response(basic()), Response(basic("get_patient POD-SYNTH-001"))]):
            result = pod_check.model_checks(1)
        self.assertEqual(result[2]["status"], "fail")

    def test_wrong_patient_native_tool_is_rejected(self):
        with patch.object(pod_check.urllib.request, "urlopen", side_effect=[Response(basic()), Response(native("OTHER-ID"))]):
            result = pod_check.model_checks(1)
        self.assertEqual(result[2]["status"], "fail")

    def test_empty_basic_response_is_failed(self):
        with patch.object(pod_check.urllib.request, "urlopen", side_effect=[Response(basic("")), Response(native())]):
            result = pod_check.model_checks(1)
        self.assertEqual(result[1]["status"], "fail")

    def test_url_embedded_auth_is_rejected_without_request(self):
        with patch.dict(os.environ, {"LLM_BASE_URL": "https://name:SECRET_TEST_ONLY@pod.example/v1"}), \
             patch.object(pod_check.urllib.request, "urlopen") as calls:
            result = pod_check.model_checks(1)
        calls.assert_not_called()
        self.assertEqual(result[0]["status"], "fail")
        self.assertNotIn("SECRET_TEST_ONLY", json.dumps(result))

    def test_unexpected_native_arguments_are_rejected(self):
        with patch.object(pod_check.urllib.request, "urlopen", side_effect=[Response(basic()), Response(native(extra={"extra": "unexpected"}))]):
            result = pod_check.model_checks(1)
        self.assertEqual(result[2]["status"], "fail")

    def test_native_tool_check_alone_is_not_complete_model_success(self):
        stream = io.StringIO()
        error = ValueError("SECRET_TEST_ONLY discard this exception message")
        with patch.object(pod_check, "offline_checks", return_value=[pod_check.check("fixture", "pass", "ok")]), \
             patch.object(pod_check.urllib.request, "urlopen", side_effect=[error, Response(native())]), \
             contextlib.redirect_stdout(stream):
            code = pod_check.main(["--model"])
        result = json.loads(stream.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["real_model_call_verified"])
        self.assertTrue(result["native_tool_call_verified"])
        self.assertNotIn("SECRET_TEST_ONLY", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
