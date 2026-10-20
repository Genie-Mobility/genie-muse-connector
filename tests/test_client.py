"""Regression tests preventing false-positive acceptance and credential forwarding."""
from email.message import Message
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('mcp_demo', Path(__file__).parents[1] / 'scripts/mcp_demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class Response(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())
        self.headers = Message()
        self.headers['Content-Type'] = 'application/json'
        self.status = 200


class ClientTests(unittest.TestCase):
    def client(self):
        return demo.Client('http://127.0.0.1:8800/mcp', 'test-only-key')

    def test_internal_server_failure_cannot_pass_negative_test(self):
        client = self.client()
        client.opener.open = Mock(side_effect=HTTPError(client.endpoint, 500, 'error', {}, None))
        with self.assertRaises(demo.Failure) as error:
            demo.rejected(lambda: client.rpc('tools/call'), 'must reject', {'not_found'})
        self.assertNotIsInstance(error.exception, demo.Rejected)

    def test_unrelated_rejection_cannot_pass_negative_test(self):
        def action():
            raise demo.Rejected('validation_error')
        with self.assertRaises(demo.Failure):
            demo.rejected(action, 'must reject', {'not_found'})

    def test_invalid_protocol_and_nonobject_envelopes_fail_safely(self):
        for value in (None, [], {'jsonrpc': '1.0', 'id': 1, 'result': {}}):
            with self.subTest(value=value):
                client = self.client()
                client.opener.open = Mock(return_value=Response(value))
                with self.assertRaises(demo.Failure):
                    client.rpc('tools/list')

    def test_string_error_flag_is_not_a_rejection(self):
        client = self.client()
        client.rpc = Mock(return_value={'isError': 'false'})
        with self.assertRaises(demo.Failure) as error:
            client.call('get_delivery_status', {})
        self.assertNotIsInstance(error.exception, demo.Rejected)

    def test_redirect_never_creates_forwarded_request(self):
        self.assertIsNone(demo.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.test'))

    def test_remote_plaintext_and_secret_urls_rejected(self):
        for endpoint in ('http://example.test/mcp', 'https://u:p@example.test/mcp',
                         'https://example.test/mcp?token=secret'):
            with self.subTest(endpoint=endpoint), self.assertRaises(demo.Failure):
                demo.Client(endpoint, 'test-only-key')


if __name__ == '__main__':
    unittest.main()
