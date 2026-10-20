#!/usr/bin/env python3
"""Independent, dependency-free acceptance client; not a Muse client emulator."""
import argparse
from datetime import datetime, timezone
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import uuid4

TOOLS = {
    'get_delivery_quote', 'reserve_delivery', 'confirm_delivery',
    'submit_pickup_details', 'get_delivery_status', 'cancel_delivery',
}


class Failure(Exception):
    pass


class Rejected(Failure):
    """An explicit protocol/tool rejection, never a network failure."""

    def __init__(self, code):
        super().__init__('Request rejected')
        self.code = code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward bearer credentials to another location.


def require(condition, description):
    if not condition:
        raise Failure(description)


def decode_response(response, request_id, deadline):
    media = response.headers.get_content_type()
    if media == 'application/json':
        raw = response.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, 'Response too large')
        return json.loads(raw)
    if media != 'text/event-stream':
        raise Failure('Unsupported response content type')
    data = []
    count = 0
    while True:
        require(time.monotonic() < deadline, 'Response deadline exceeded; outcome may be uncertain')
        raw = response.readline(65537)
        if not raw:
            break
        count += len(raw)
        require(len(raw) <= 65536 and count <= 1024 * 1024, 'SSE response too large')
        line = raw.decode('utf-8').rstrip('\r\n')
        if line.startswith('data:'):
            data.append(line[5:].lstrip(' '))
        elif not line:
            if data and ''.join(data):
                item = json.loads('\n'.join(data))
                require(isinstance(item, dict), 'Invalid SSE message object')
                if item.get('id') == request_id:
                    return item
            data = []
    raise Failure('SSE ended without matching response; outcome may be uncertain')


class Client:
    def __init__(self, endpoint, token, timeout=15):
        parsed = urlsplit(endpoint)
        require(not parsed.username and not parsed.password and not parsed.query
                and not parsed.fragment, 'Endpoint must not contain credentials/query/fragment')
        require(parsed.scheme == 'https' or
                (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')),
                'Use HTTPS except for loopback tests')
        require(not any(c in token for c in '\r\n'), 'Invalid credential format')
        self.endpoint, self.token, self.timeout = endpoint, token, timeout
        self.session = None
        self.version = None
        self.sequence = 0
        self.opener = build_opener(NoRedirect)

    def rpc(self, method, params=None, notification=False):
        self.sequence += 1
        payload = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        if not notification:
            payload['id'] = self.sequence
        headers = {'Content-Type': 'application/json',
                   'Accept': 'application/json, text/event-stream'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        if self.version:
            headers['MCP-Protocol-Version'] = self.version
        request = Request(self.endpoint, json.dumps(payload).encode(), headers, method='POST')
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if notification:
                    require(response.status == 202, 'Notification did not return 202')
                    return None
                if method == 'initialize':
                    self.session = response.headers.get('Mcp-Session-Id')
                result = decode_response(response, self.sequence, time.monotonic() + self.timeout)
        except HTTPError as error:
            if error.code in (401, 403):
                raise Rejected('http_' + str(error.code)) from None
            raise Failure('Unexpected HTTP status: ' + str(error.code)) from None
        except (URLError, TimeoutError, OSError):
            raise Failure('Transport failed; write outcome may be uncertain. Do not retry with a new key.') from None
        require(isinstance(result, dict) and result.get('jsonrpc') == '2.0', 'Invalid JSON-RPC envelope')
        require(result.get('id') == self.sequence, 'Mismatched JSON-RPC response ID')
        if 'error' in result:
            raise Failure('Unexpected JSON-RPC error')
        require('result' in result, 'Missing JSON-RPC result')
        require(isinstance(result['result'], dict), 'Expected object result')
        return result['result']

    def initialize(self):
        result = self.rpc('initialize', {
            'protocolVersion': '2025-11-25', 'capabilities': {},
            'clientInfo': {'name': 'genie-independent-acceptance', 'version': '0.1.0'},
        })
        self.version = result.get('protocolVersion')
        require(self.version in ('2025-03-26', '2025-06-18', '2025-11-25'),
                'Unsupported negotiated MCP version')
        self.rpc('notifications/initialized', notification=True)

    def call(self, name, arguments):
        result = self.rpc('tools/call', {'name': name, 'arguments': arguments})
        require(isinstance(result.get('isError', False), bool), 'Invalid isError type')
        if result.get('isError'):
            for item in result.get('content', []):
                if item.get('type') != 'text':
                    continue
                value = item.get('text', '')
                # FastMCP prefixes ToolError text; decode only the JSON object suffix.
                start = value.find('{')
                if start >= 0:
                    try:
                        error = json.loads(value[start:])
                    except ValueError:
                        continue
                    if isinstance(error, dict) and isinstance(error.get('code'), str):
                        raise Rejected(error['code'])
                if 'user_confirmed' in value and ('validation error' in value.lower() or 'boolean true' in value):
                    raise Rejected('confirmation_validation')
            raise Failure('Unrecognized tool failure; cannot count as expected rejection')
        data = result.get('structuredContent')
        if data is None:
            texts = [c['text'] for c in result.get('content', []) if c.get('type') == 'text']
            require(len(texts) == 1, 'Expected one JSON tool result')
            data = json.loads(texts[0])
        require(isinstance(data, dict), 'Tool result must be an object')
        return data


def rejected(action, description, expected):
    try:
        action()
    except Rejected as error:
        require(error.code in expected, 'Rejected for an unexpected reason')
        return
    raise Failure(description)


def run(args):
    token = os.environ.get('GENIE_SANDBOX_TOKEN', '')
    require(bool(token), 'Set GENIE_SANDBOX_TOKEN through the environment')
    client = Client(args.endpoint, token)
    evidence = []

    def passed(label):
        evidence.append(label)
        print('PASS ' + label, flush=True)

    for bad in ('', 'invalid-sandbox-token-' + uuid4().hex):
        try:
            Client(args.endpoint, bad).initialize()
        except Rejected as error:
            require(error.code in ('http_401', 'http_403'),
                    'Authentication failed for an unrelated reason')
        else:
            raise Failure('Missing/invalid credentials accepted')
    passed('missing and invalid credentials rejected')
    client.initialize()
    listed = client.rpc('tools/list')['tools']
    require(TOOLS <= {tool['name'] for tool in listed}, 'Expected six tools not exposed')
    passed('MCP initialization and six-tool discovery')

    def write(name, values):
        payload = {**values, 'idempotency_key': str(uuid4())}
        result = client.call(name, payload)
        require(result.get('simulation') is True, 'Missing explicit simulation label')
        return result, payload

    def booking():
        quote, qp = write('get_delivery_quote', {
            'pickup_address': '1 Fictional Restaurant Lane, Sandbox',
            'dropoff_address': '2 Fictional Customer Lane, Sandbox',
            'package_description': 'Already ordered fictional sealed meal; no food purchase',
            'requested_ready_time': datetime.now(timezone.utc).isoformat(),
            'handoff_type': 'meet_at_door', 'instructions': 'Sandbox only; do not dispatch',
        })
        require(quote.get('price_cents') == 500 and quote.get('currency') == 'USD',
                'Unexpected sandbox total/currency')
        require(bool(quote.get('expires_at')), 'Quote missing expiry')
        require(client.call('get_delivery_quote', qp)['quote_id'] == quote['quote_id'],
                'Quote replay created a new quote')
        rejected(lambda: client.call('get_delivery_quote', {**qp, 'package_description': 'changed'}),
                 'Changed payload accepted with original idempotency key', {'idempotency_conflict'})
        reservation, rp = write('reserve_delivery', {'quote_id': quote['quote_id']})
        require(client.call('reserve_delivery', rp)['reservation_id'] == reservation['reservation_id'],
                'Reservation replay created a duplicate')
        rejected(lambda: client.call('confirm_delivery', {
            'reservation_id': reservation['reservation_id'], 'user_confirmed': False,
            'idempotency_key': str(uuid4()),
        }), 'Confirmation accepted without affirmative caller assertion', {'confirmation_validation', 'validation_error'})
        delivery, cp = write('confirm_delivery', {
            'reservation_id': reservation['reservation_id'], 'user_confirmed': True,
        })
        require(delivery.get('status') == 'awaiting_pickup_details', 'Premature execution')
        require(delivery.get('payment_status') == 'simulated_authorized', 'Unexpected payment state')
        require(client.call('confirm_delivery', cp)['delivery_id'] == delivery['delivery_id'],
                'Confirmation replay created a duplicate')
        return delivery['delivery_id']

    delivery_id = booking()
    passed('quote, reserve, confirm, retries, payload conflict and confirmation gate')
    second = os.environ.get('GENIE_SECOND_TENANT_TOKEN')
    if second:
        other = Client(args.endpoint, second)
        other.initialize()
        rejected(lambda: other.call('get_delivery_status', {'delivery_id': delivery_id}),
                 'Another tenant read the delivery', {'not_found'})
        rejected(lambda: other.call('cancel_delivery', {
            'delivery_id': delivery_id, 'reason': 'Tenant isolation test',
            'idempotency_key': str(uuid4()),
        }), 'Another tenant cancelled the delivery', {'not_found'})
        passed('second tenant cannot read or cancel first tenant delivery')
    else:
        print('SKIP tenant isolation: GENIE_SECOND_TENANT_TOKEN absent', flush=True)
    write('submit_pickup_details', {
        'delivery_id': delivery_id, 'restaurant_confirmation': True,
        'restaurant_order_reference': 'FICTIONAL-ORDER-001', 'pickup_name': 'Sandbox Tester',
        'pickup_code': 'SIM-001', 'ready_at': datetime.now(timezone.utc).isoformat(),
        'instructions': 'Fictional package; simulation only',
    })
    deadline = time.monotonic() + args.completion_timeout
    while True:
        state = client.call('get_delivery_status', {'delivery_id': delivery_id})
        require(state.get('simulation') is True, 'Status missing simulation label')
        if state.get('status') == 'completed':
            break
        require(state.get('status') not in ('cancelled', 'failed'), 'Unexpected terminal delivery state')
        require(time.monotonic() < deadline, 'Timed out waiting for simulated completion')
        time.sleep(1)
    passed('pickup details and simulated completion')
    cancelled_id = booking()
    cancelled, payload = write('cancel_delivery', {
        'delivery_id': cancelled_id, 'reason': 'Sandbox cancellation scenario',
    })
    require(cancelled.get('status') == 'cancelled', 'Cancellation not persisted')
    require(client.call('cancel_delivery', payload).get('status') == 'cancelled',
            'Cancellation replay is not stable')
    require(client.call('get_delivery_status', {'delivery_id': cancelled_id}).get('status') == 'cancelled',
            'Cancelled status not readable')
    passed('separate cancellation and idempotent replay')
    print(json.dumps({'tier': 'generic_mcp_not_muse', 'passed': evidence,
                      'completed_delivery_id': delivery_id, 'cancelled_delivery_id': cancelled_id,
                      'muse_validation': 'not performed', 'restart_validation': 'not performed'}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', default='http://127.0.0.1:8800/mcp')
    parser.add_argument('--completion-timeout', type=float, default=60)
    args = parser.parse_args()
    try:
        run(args)
    except (Failure, ValueError, KeyError, TypeError) as error:
        # Never print server bodies, credential-bearing URLs, or request arguments.
        print('FAIL ' + (str(error) if isinstance(error, Failure) else 'Malformed protocol/contract response'),
              file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
