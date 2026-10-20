#!/usr/bin/env python3
"""Independent local-only human-pilot HTTP flow with explicit fake-provider inputs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
from urllib.parse import urlsplit
from uuid import uuid4

from mcp_demo import Client, Failure, Rejected
from pilot_probe import Browser, OAuthProbe, ProbeFailure, check


def utc():
    return datetime.now(timezone.utc).isoformat()


def run(fixture, credentials_path, control_path, cancellation_only=False):
    check(urlsplit(fixture['base_url']).hostname in ('localhost', '127.0.0.1'),
          'Fake-provider flow is restricted to an isolated loopback test server')
    check(stat.S_IMODE(credentials_path.stat().st_mode) == 0o600, 'Credential file must be mode 600')
    credentials = json.loads(credentials_path.read_text())
    operator = Browser(fixture['base_url'])
    origin = fixture['base_url'].rstrip('/')
    session = operator.request('POST', '/pilot/operator/session',
                               data={'credential': credentials['operator_credential']}, origin=origin)
    check(session.status == 200, 'Operator fixture login failed')
    csrf = session.json()['csrf_token']

    def op(path, values, *, expected=200, csrf_value=csrf):
        response = operator.request('POST', '/pilot/operator/api/' + path, data=values, origin=origin,
                                    extra_headers={'X-CSRF-Token': csrf_value, 'Idempotency-Key': uuid4().hex})
        check(response.status == expected, 'Unexpected operator-action result')
        return response.json()

    def available():
        op('availability', {'available': True, 'origin': {
            'address': 'Fixture operator origin', 'latitude': 0, 'longitude': 0}, 'observed_at': utc()})

    def action(job_id, name, **values):
        return op('jobs/' + job_id + '/actions', {'action': name, **values})

    guest = OAuthProbe(fixture)
    guest.discover()

    def client(probe, scope='delivery:read delivery:write'):
        grant = probe.token(probe.exchange(probe.authorize(scope=scope)))
        result = Client(fixture['resource'], grant['access_token'])
        result.initialize()
        return result

    customer = client(guest)
    check(len(customer.rpc('tools/list')['tools']) == 6, 'Pilot must expose six customer tools')

    def call(name, values, *, key=None):
        args = dict(values)
        if name != 'get_delivery_status':
            args['idempotency_key'] = key or uuid4().hex
        result = customer.call(name, args)
        check(result.get('test_mode') is True and result.get('execution_mode') == 'human_test',
              'Pilot result missing test/human mode labels')
        return result

    def denied(client_instance, name, values, expected):
        try:
            client_instance.call(name, values)
        except Rejected as error:
            check(error.code in expected, 'Negative case rejected for an unexpected reason')
            return
        raise ProbeFailure('Forbidden pilot action was accepted')

    def status(job_id):
        return call('get_delivery_status', {'delivery_id': job_id})

    def wait(job_id, predicate, label, seconds=150):
        deadline = time.monotonic() + seconds
        while True:
            state = status(job_id)
            if predicate(state):
                print('PASS ' + label, flush=True)
                return state
            check(time.monotonic() < deadline, 'Timeout waiting for ' + label)
            time.sleep(1)

    def controls(job_id, **values):
        check(stat.S_IMODE(control_path.stat().st_mode) == 0o600, 'Fake controls must be mode 600')
        content = json.loads(control_path.read_text())
        content[job_id] = values
        descriptor, temporary = tempfile.mkstemp(prefix='.pilot-control-', dir=control_path.parent)
        try:
            with os.fdopen(descriptor, 'w') as output:
                json.dump(content, output)
            os.replace(temporary, control_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def book():
        available()
        quote = call('get_delivery_quote', {
            'pickup_address': '1 Fixture Pickup Street', 'dropoff_address': '2 Fixture Dropoff Street',
            'package_description': 'Fictional sealed package', 'requested_ready_time': utc(),
            'handoff_type': 'meet_at_door'})
        reservation = call('reserve_delivery', {'quote_id': quote['quote_id']})
        values = {'reservation_id': reservation['reservation_id'], 'user_confirmed': True,
                  'customer_contact': 'fictional@example.invalid'}
        key = uuid4().hex
        job = call('confirm_delivery', values, key=key)
        check(job['state'] == 'pending_payment', 'Unpaid booking prematurely confirmed')
        check(call('confirm_delivery', values, key=key)['delivery_id'] == job['delivery_id'],
              'Confirmation replay duplicated a job')
        return job['delivery_id']

    job_id = None
    if not cancellation_only:
        job_id = book()
        other = OAuthProbe(fixture)
        other.discover()
        outsider = client(other)
        denied(outsider, 'get_delivery_status', {'delivery_id': job_id}, {'not_found'})
        readonly = client(guest, 'delivery:read')
        check(readonly.call('get_delivery_status', {'delivery_id': job_id})['delivery_id'] == job_id,
              'Same-browser reconnect lost guest ownership')
        denied(readonly, 'cancel_delivery', {'delivery_id': job_id, 'reason': 'scope test',
                                          'idempotency_key': uuid4().hex}, {'http_403', 'insufficient_scope'})
        print('PASS guest continuity, cross-guest isolation, read-only scope and confirmation retry', flush=True)
        op('jobs/' + job_id + '/actions', {'action': 'accept'}, expected=409)
        denied(customer, 'submit_pickup_details', {
            'delivery_id': job_id, 'restaurant_confirmation': True, 'restaurant_order_reference': 'FIXTURE',
            'pickup_name': 'Fixture guest', 'ready_at': utc(), 'idempotency_key': uuid4().hex}, {'invalid_state'})
        wait(job_id, lambda s: bool((s.get('next_action') or {}).get('url')), 'payment handoff URL available')
        controls(job_id, status='authorized', authorization_expires_at=time.time() + 3600)
        wait(job_id, lambda s: s['state'] == 'pending_operator', 'fake authorization awaits operator')
        op('jobs/' + job_id + '/actions', {'action': 'accept'}, expected=403, csrf_value='wrong')
        action(job_id, 'accept')
        check(status(job_id)['state'] == 'confirmed', 'Operator acceptance did not confirm capacity')
        call('submit_pickup_details', {'delivery_id': job_id, 'restaurant_confirmation': True,
             'restaurant_order_reference': 'FICTIONAL-ORDER', 'pickup_name': 'Fixture guest', 'ready_at': utc()})
        for name in ('heading_to_pickup', 'arrived_pickup', 'collected'):
            action(job_id, name)
        controls(job_id, status='authorized', capture_failure=True, authorization_expires_at=time.time() + 3600)
        action(job_id, 'handoff', handoff_evidence='Fictional recipient acknowledged test handoff')
        check(status(job_id)['state'] == 'delivered', 'Handoff did not record physical delivery')
        wait(job_id, lambda s: s['state'] == 'delivered' and s['payment_state'] == 'reconciliation_required',
             'delivery remains delivered after fake capture failure')
        controls(job_id, status='authorized', authorization_expires_at=time.time() + 3600)
        wait(job_id, lambda s: s['state'] == 'delivered' and s['payment_state'] == 'captured',
             'fake capture reconciliation completes without redispatch')

    cancelled = book()
    wait(cancelled, lambda s: bool((s.get('next_action') or {}).get('url')), 'second fake checkout available')
    call('cancel_delivery', {'delivery_id': cancelled, 'reason': 'Fixture cancellation before authorization'})
    controls(cancelled, status='authorized', authorization_expires_at=time.time() + 3600)
    wait(cancelled, lambda s: s['state'] == 'cancelled' and s['payment_state'] == 'voided',
         'late fake authorization after cancellation is voided, not confirmed')
    print(json.dumps({'tier': 'local_https_oauth_mcp_with_injected_fake_provider',
                      'delivered_job_id': job_id, 'cancelled_job_id': cancelled,
                      'actual_muse': 'not tested', 'actual_stripe': 'not tested',
                      'real_dispatch': 'disabled'}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--provider-controls', type=Path, required=True)
    parser.add_argument('--cancellation-only', action='store_true')
    args = parser.parse_args()
    try:
        run(json.loads(args.fixture.read_text()), args.credentials, args.provider_controls, args.cancellation_only)
    except (ProbeFailure, Failure, ValueError, KeyError, TypeError, OSError) as error:
        print('FAIL ' + (str(error) if isinstance(error, (ProbeFailure, Failure)) else
                        'Invalid test fixture or response; sensitive details withheld'), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
