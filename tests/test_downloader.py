import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import requests

from tronclass_client import BASE_URL, Cancelled, DownloadError, TronClassClient, describe_error, parse_target, safe_name


class Response:
    def __init__(self, data=None, content=b"%PDF-1.7 test document", status=200, headers=None, text="", url=BASE_URL, chunks=None):
        self.data, self.content, self.status_code = data, content, status
        self.headers = headers or {"Content-Type": "application/pdf", "Content-Length": str(len(content))}
        self.text, self.url, self.chunks = text, url, chunks

    def json(self):
        return self.data

    def iter_content(self, size):
        if self.chunks:
            yield from self.chunks()
        else:
            yield self.content

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.session = Mock(headers={})
        self.client = TronClassClient(session=self.session)
        self.target = BASE_URL + "/course/42/learning-activity#/1"

    def route(self, method, url, **kwargs):
        page = (kwargs.get("params") or {}).get("page", 1)
        if url.endswith("/modules"):
            return Response({"modules": [{"id": 7, "name": "第一章"}], "total": 1})
        if url.endswith("/activities"):
            # Server caps page_size at 1 despite client requesting 100.
            return Response({"activities": [{"id": page, "module_id": 7}], "total": 2})
        if url.endswith("/activities/1"):
            return Response({"id": 1, "title": "入門", "module_id": 7, "uploads": [
                {"name": "same.pdf", "reference_id": 101},
                {"name": "same.pdf", "reference_id": 102},
                {"name": "video.mp4", "reference_id": 103}]})
        if url.endswith("/activities/2"):
            return Response({"id": 2, "title": "進階", "module_id": 7,
                             "uploads": [{"name": "CON.pdf", "reference_id": 104}]})
        if "/document/" in url:
            return Response({"url": "https://files.example.test/" + url.split("/")[-2]})
        if url.startswith("https://files.example.test/"):
            return Response()
        raise AssertionError(f"Unexpected request: {method} {url}")

    def test_paged_course_multiple_uploads_and_idempotent_retry(self):
        self.session.request.side_effect = self.route
        first = self.client.run(self.target, self.root)
        self.assertEqual((first.downloaded, first.skipped, first.excluded, first.failures), (3, 0, 1, []))
        files = list(self.root.rglob("*.pdf"))
        self.assertEqual(len(files), 3)
        self.assertEqual(len({p.name for p in files}), 3)
        self.assertTrue(all("第一章__7" in str(p) for p in files))
        self.assertTrue(any(p.name.startswith("_CON") for p in files))
        self.session.request.reset_mock()
        second = self.client.run(self.target, self.root)
        self.assertEqual((second.downloaded, second.skipped, second.failures), (0, 3, []))
        self.assertFalse(any("files.example" in call.args[1] for call in self.session.request.call_args_list))

    def test_failure_does_not_stop_other_files_and_retry_recovers(self):
        def failure(method, url, **kwargs):
            return Response(status=500) if url == "https://files.example.test/102" else self.route(method, url, **kwargs)
        self.session.request.side_effect = failure
        first = self.client.run(self.target, self.root)
        self.assertEqual((first.downloaded, len(first.failures)), (2, 1))
        self.assertFalse(list(self.root.rglob("*.part")))
        report = json.loads(next(self.root.rglob(".download-report.json")).read_text(encoding="utf-8"))
        self.assertEqual(report["failures"][0]["reference_id"], 102)
        self.session.request.side_effect = self.route
        second = self.client.run(self.target, self.root)
        self.assertEqual((second.downloaded, second.skipped, second.failures), (1, 2, []))

    def test_single_activity_still_downloads_all_attachments(self):
        self.session.request.side_effect = self.route
        result = self.client.run(self.target, self.root, whole_course=False)
        self.assertEqual((result.downloaded, result.excluded, result.failures), (2, 1, []))
        self.assertFalse(any(call.args[1].endswith("/modules") for call in self.session.request.call_args_list))

    def test_cancel_midstream_cleans_partial_files(self):
        def chunks():
            yield b"start"
            self.client.cancel.set()
            yield b"end"
        def route(method, url, **kwargs):
            return Response(chunks=chunks) if "files.example.test" in url else self.route(method, url, **kwargs)
        self.session.request.side_effect = route
        result = self.client.run(self.target, self.root, whole_course=False)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.downloaded, 0)
        self.assertFalse(list(self.root.rglob("*.part")))
        self.assertFalse(list(self.root.rglob("*.pdf")))

    def test_corrupted_file_is_preserved_and_redownloaded(self):
        self.session.request.side_effect = self.route
        self.client.run(self.target, self.root, whole_course=False)
        original = next(self.root.rglob("*101.pdf"))
        original.write_bytes(b"local edit")
        result = self.client.run(self.target, self.root, whole_course=False)
        self.assertEqual((result.downloaded, result.skipped), (1, 1))
        self.assertEqual(original.read_bytes(), b"local edit")
        self.assertEqual(len(list(self.root.rglob("*.pdf"))), 3)

    def test_truncated_and_html_downloads_are_not_success(self):
        for response in [Response(headers={"Content-Length": "999"}), Response(headers={"Content-Type": "text/html"})]:
            with self.subTest(headers=response.headers):
                def route(method, url, **kwargs):
                    return response if "files.example.test" in url else self.route(method, url, **kwargs)
                self.session.request.side_effect = route
                result = self.client.run(self.target, self.root, whole_course=False)
                self.assertEqual((result.downloaded, len(result.failures)), (0, 2))
                self.assertFalse(list(self.root.rglob("*.part")))
                self.assertFalse(list(self.root.rglob("*.pdf")))

    def test_failed_activity_scan_is_reported(self):
        def route(method, url, **kwargs):
            return Response(status=403) if url.endswith("/activities/2") else self.route(method, url, **kwargs)
        self.session.request.side_effect = route
        result = self.client.run(self.target, self.root)
        self.assertEqual((result.downloaded, len(result.failures)), (2, 1))
        self.assertEqual(result.failures[0]["stage"], "清單")

    def test_pagination_repetition_with_metadata_fails(self):
        self.session.request.return_value = Response({"activities": [{"id": 1}], "total": 2})
        with self.assertRaises(DownloadError):
            self.client.list_all("/api/courses/42/activities", "activities")

    def test_unpaged_and_short_pages_without_metadata(self):
        self.session.request.return_value = Response({"activities": [{"id": 1}]})
        self.assertEqual(len(self.client.list_all("/test", "activities")), 1)
        self.session.request.side_effect = [Response({"activities": [{"id": 1}]}),
                                           Response({"activities": [{"id": 2}]}), Response({"activities": []})]
        self.assertEqual(len(self.client.list_all("/test", "activities")), 2)

    def test_missing_records_fail_instead_of_reporting_complete(self):
        self.session.request.side_effect = [Response({"activities": [{"id": 1}], "total": 3}),
                                           Response({"activities": [], "total": 3})]
        with self.assertRaises(DownloadError):
            self.client.list_all("/test", "activities")

    def test_login_hidden_fields_relative_action_and_tls(self):
        form = '<form action="/authenticate"><input type="hidden" name="token" value="example"><input type="password" name="password"></form>'
        self.session.request.side_effect = [Response(text=form, url="https://sso.nsysu.edu.tw/login"), Response(text="Welcome")]
        self.client.login("test-user", "test-password")
        call = self.session.request.call_args_list[1]
        self.assertEqual(call.args[1], "https://sso.nsysu.edu.tw/authenticate")
        self.assertEqual(call.kwargs["data"]["token"], "example")
        self.assertNotIn("verify", call.kwargs)

    def test_login_rejects_password_form_and_untrusted_action(self):
        for action in ["https://evil.example/login", "https://sso.nsysu.edu.tw/login"]:
            form = f'<form action="{action}"><input type="password"></form>'
            self.session.request.side_effect = [Response(text=form), Response(text=form)]
            with self.assertRaises(DownloadError):
                self.client.login("test-user", "test-password")

    def test_bad_url_and_sensitive_error_redaction(self):
        for url in ["https://evil.example/course/42", BASE_URL + "/course/nope", "http://elearn.nsysu.edu.tw/course/42"]:
            with self.assertRaises(DownloadError):
                parse_target(url)
        self.assertNotIn("secret", describe_error(requests.ConnectionError("https://file/?token=secret")))
        self.assertEqual(safe_name("../CON"), "_CON")


if __name__ == "__main__":
    unittest.main()
