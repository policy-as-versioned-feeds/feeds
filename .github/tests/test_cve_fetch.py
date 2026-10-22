"""Synthetic urllib responses drive the real CVE transport; no network or credentials."""
import importlib.util
import gzip
import json
import urllib.error
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('cve_fetch_transport', ROOT / 'fetch/cve.py')
assert SPEC is not None and SPEC.loader is not None
cve = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cve)


class Response:
    def __init__(self, value):
        self.value = value
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True
        return False

    def read(self):
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


class CVEFetchTransport(unittest.TestCase):
    def transport(self, replies):
        self.calls = []
        self.sleeps = []
        replies = iter(replies)
        def opening(request, timeout):
            self.calls.append((request.full_url, timeout))
            reply = next(replies)
            if isinstance(reply, BaseException):
                raise reply
            return reply
        self.enterContext(patch.dict(cve.os.environ, {}, clear=True))
        self.enterContext(patch.object(cve.urllib.request, 'urlopen', side_effect=opening))
        self.enterContext(patch.object(cve.time, 'sleep', side_effect=self.sleeps.append))

    def http_error(self, status, reason):
        error = urllib.error.HTTPError(cve.NVD_URL, status, reason, None, None)
        self.addCleanup(error.close)
        return error

    def test_response_read_timeout_retries_then_returns_complete_response(self):
        first = Response(TimeoutError('synthetic response read timeout'))
        second = Response(b'complete response')
        self.transport([first, second])
        self.assertEqual(cve.fetch(cve.NVD_URL), b'complete response')
        self.assertEqual(self.calls, [(cve.NVD_URL, 30), (cve.NVD_URL, 30)])
        self.assertEqual(self.sleeps, [1])
        self.assertTrue(first.closed and second.closed)

    def test_timeouts_exhaust_the_same_four_attempts_and_close_responses(self):
        responses = [Response(TimeoutError('synthetic timeout ' + str(index))) for index in range(4)]
        self.transport(responses)
        with self.assertRaises(TimeoutError) as caught:
            cve.fetch(cve.NVD_URL)
        self.assertIs(caught.exception, responses[-1].value)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(self.sleeps, [1, 2, 4])
        self.assertTrue(all(response.closed for response in responses))

    def test_existing_retryable_http_statuses_still_recover(self):
        for status in (429, 502, 503):
            with self.subTest(status=status):
                self.transport([self.http_error(status, 'synthetic transient'),
                                Response(b'complete response')])
                self.assertEqual(cve.fetch(cve.NVD_URL), b'complete response')
                self.assertEqual(len(self.calls), 2)
                self.assertEqual(self.sleeps, [1])

    def test_permanent_http_errors_are_not_retried(self):
        for status in (400, 401, 403, 404, 500):
            with self.subTest(status=status):
                error = self.http_error(status, 'synthetic permanent')
                self.transport([error])
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    cve.fetch(cve.NVD_URL)
                self.assertIs(caught.exception, error)
                self.assertEqual(len(self.calls), 1)
                self.assertEqual(self.sleeps, [])

    def test_transient_http_and_timeouts_share_one_budget(self):
        last = Response(TimeoutError('synthetic final timeout'))
        self.transport([self.http_error(429, 'synthetic transient'),
                        Response(TimeoutError('synthetic timeout')),
                        self.http_error(503, 'synthetic transient'), last])
        with self.assertRaises(TimeoutError) as caught:
            cve.fetch(cve.NVD_URL)
        self.assertIs(caught.exception, last.value)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(self.sleeps, [1, 2, 4])
        self.assertTrue(last.closed)

    def test_invalid_nvd_json_is_not_retried_or_accepted(self):
        epss = gzip.compress(b'#score_date:2026-10-22\ncve,epss\n')
        responses = [Response(b'{"vulnerabilities": []}'), Response(epss), Response(b'invalid JSON')]
        self.transport(responses)
        with self.assertRaises(json.JSONDecodeError):
            cve.source()
        self.assertEqual([url for url, _ in self.calls],
                         [cve.KEV_URL, cve.EPSS_URL, cve.NVD_URL + '&startIndex=0'])
        self.assertEqual(self.sleeps, [])
        self.assertTrue(all(response.closed for response in responses))


if __name__ == '__main__':
    unittest.main(verbosity=2)
