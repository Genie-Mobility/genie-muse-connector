#!/usr/bin/env python3
"""Read-only-auth compatibility probe; no Muse support or delivery capability claim."""
import argparse
import json
from pathlib import Path
import secrets
import sys

from mcp_demo import Client, Failure
from pilot_probe import OAuthProbe, ProbeFailure, check, expect_oauth_error


def run(fixture):
    probe = OAuthProbe(fixture)
    probe.discover()
    endpoint = probe.metadata.get('registration_endpoint')
    check(isinstance(endpoint, str), 'Dynamic registration is not advertised')
    request = {'client_name': 'Independent OAuth compatibility probe',
               'redirect_uris': [fixture['redirect_uri']],
               'token_endpoint_auth_method': 'none',
               'grant_types': ['authorization_code', 'refresh_token'],
               'response_types': ['code'], 'scope': 'delivery:read'}

    def register(values):
        return probe.browser.request('POST', endpoint, data=values)

    untrusted = register({**request, 'redirect_uris': ['https://untrusted.invalid/callback']})
    check(untrusted.status == 400 and untrusted.json().get('error') == 'invalid_redirect_uri',
          'Unknown redirect was not rejected before registration')
    for changes in ({'token_endpoint_auth_method': 'client_secret_basic'},
                    {'grant_types': ['client_credentials']}, {'response_types': ['token']},
                    {'scope': 'delivery:read operator:write'},
                    {'redirect_uris': [fixture['redirect_uri'] + '#fragment']}):
        reply = register({**request, **changes})
        check(reply.status == 400 and reply.json().get('error') in
              ('invalid_client_metadata', 'invalid_redirect_uri', 'invalid_scope'),
              'Unsupported registration metadata was not rejected')
    omitted_auth = dict(request)
    omitted_auth.pop('token_endpoint_auth_method')
    reply = register(omitted_auth)
    check(reply.status == 400 and reply.json().get('error') == 'invalid_client_metadata',
          'Omitted token authentication method silently changed OAuth defaults')
    print('PASS unapproved callback and unsupported DCR metadata rejected', flush=True)

    response = register(request)
    check(response.status == 201, 'Approved test callback registration failed')
    registration = response.json()
    check(isinstance(registration.get('client_id'), str) and registration['client_id'], 'No generated client ID')
    check(registration.get('redirect_uris') == [fixture['redirect_uri']], 'Registered callback changed')
    check(registration.get('token_endpoint_auth_method') == 'none', 'Unexpected client authentication mode')
    check(not any(key in registration for key in ('client_secret', 'access_token', 'refresh_token')),
          'Public registration returned an unexpected credential')
    probe.fixture = {**fixture, 'client_id': registration['client_id']}
    probe.authorize(scope='delivery:write', expected_get_error={'invalid_scope'})
    probe.authorize(scope='delivery:read', consent_overrides={'decision': 'deny'})
    probe.authorize(scope='delivery:read', overrides={'code_challenge_method': 'plain'},
                    expected_get_error={'invalid_request'})
    probe.authorize(scope='delivery:read', overrides={'redirect_uri': 'https://untrusted.invalid/callback'},
                    expected_get_error={'invalid_request'})
    grant = probe.authorize(scope='delivery:read')
    expect_oauth_error(probe.exchange(grant, overrides={'code_verifier': secrets.token_urlsafe(48)}),
                       {'invalid_grant'})
    grant = probe.authorize(scope='delivery:read')
    expect_oauth_error(probe.exchange(grant, overrides={'resource': 'https://untrusted.invalid/mcp'}),
                       {'invalid_target', 'invalid_grant'})
    grant = probe.authorize(scope='delivery:read')
    token = probe.token(probe.exchange(grant))
    expect_oauth_error(probe.exchange(grant), {'invalid_grant'})
    check(set(token.get('scope', '').split()) == {'delivery:read'}, 'Registered read scope widened')
    print('PASS generated client ID, consent, S256/code/resource/exact redirect bindings', flush=True)

    def connect(access_token):
        client = Client(fixture['resource'], access_token)
        client.initialize()
        return client

    client = connect(token['access_token'])
    listed = client.rpc('tools/list')['tools']
    check([tool['name'] for tool in listed] == [fixture['probe_tool']], 'Auth-only server exposed unexpected tools')
    check(listed[0].get('annotations', {}).get('readOnlyHint') is True, 'Probe is not annotated read-only')
    status = client.call(fixture['probe_tool'], {})
    check(status.get('authenticated') is True and status.get('mode') == 'oauth_compatibility_probe'
          and status.get('resource') == fixture['resource'], 'Unexpected auth-probe result')
    check(set(status) == {'authenticated', 'mode', 'resource'}, 'Auth probe returned extra private fields')
    for path in fixture.get('absent_paths', ['/pilot/operator/session', '/pilot/v1/quotes', '/pilot/operator',
                                           '/pilot/payments/webhook', '/pilot/payment-return']):
        reply = probe.browser.request('GET', path, token=token['access_token'])
        check(reply.status == 404, 'Auth-only server exposed a business/operator route')
    print('PASS only the read-only auth tool is exposed; business/operator routes absent', flush=True)

    refresh = {'grant_type': 'refresh_token', 'refresh_token': token['refresh_token'],
               'client_id': registration['client_id'], 'resource': fixture['resource']}
    rotated = probe.token(probe.browser.request('POST', probe.metadata['token_endpoint'], form=refresh))
    check(rotated['refresh_token'] != token['refresh_token'], 'Dynamic client refresh was not rotated')
    connect(rotated['access_token'])
    expect_oauth_error(probe.browser.request('POST', probe.metadata['token_endpoint'], form=refresh),
                       {'invalid_grant'})
    denied = probe.browser.request('POST', '/pilot/mcp', token=rotated['access_token'], data={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}})
    check(denied.status == 401, 'Refresh replay did not revoke the dynamic grant family')
    fresh = probe.token(probe.exchange(probe.authorize(scope='delivery:read')))
    response = probe.browser.request('POST', probe.metadata['revocation_endpoint'], form={
        'client_id': registration['client_id'], 'token': fresh['refresh_token'],
        'token_type_hint': 'refresh_token'})
    check(response.status == 200, 'Dynamic client revocation failed')
    denied = probe.browser.request('POST', '/pilot/mcp', token=fresh['access_token'], data={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}})
    check(denied.status == 401, 'Revoked dynamic grant still has access')
    print('PASS dynamic-client refresh rotation/replay family revocation and explicit revoke', flush=True)
    print('PASS generic DCR/OAuth protocol only; actual Muse handshake not performed', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', required=True, type=Path)
    args = parser.parse_args()
    try:
        run(json.loads(args.fixture.read_text()))
    except (ProbeFailure, Failure, ValueError, KeyError, TypeError, OSError) as error:
        print('FAIL ' + (str(error) if isinstance(error, (ProbeFailure, Failure)) else
                        'Invalid fixture or response; sensitive details withheld'), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
