#!/usr/bin/env python3
"""Independent pilot OAuth probe. No Muse compatibility or real-payment claim."""
import argparse
import base64
from dataclasses import dataclass, field
import hashlib
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import json
from pathlib import Path
import secrets
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener


class ProbeFailure(Exception):
    """Only static, non-sensitive descriptions may be exposed to the caller."""


def check(value, message):
    if not value:
        raise ProbeFailure(message)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(repr=False)
class Response:
    status: int
    headers: object = field(repr=False)
    body: bytes = field(repr=False)

    def json(self):
        try:
            value = json.loads(self.body)
        except ValueError:
            raise ProbeFailure('Expected JSON response') from None
        check(isinstance(value, dict), 'Expected JSON object')
        return value


class Browser:
    def __init__(self, base):
        parsed = urlsplit(base)
        check(not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
              'Base URL must not contain credentials, query, or fragment')
        check(parsed.scheme == 'https' or (parsed.scheme == 'http' and parsed.hostname in
              ('127.0.0.1', 'localhost', '::1')), 'HTTPS required except loopback')
        self.base = base.rstrip('/')
        self.origin = (parsed.scheme, parsed.netloc)
        self.cookies = CookieJar()
        self.opener = build_opener(NoRedirect, HTTPCookieProcessor(self.cookies))

    def request(self, method, path, *, form=None, data=None, token=None, origin=None, extra_headers=None):
        url = urljoin(self.base + '/', path)
        parsed = urlsplit(url)
        check((parsed.scheme, parsed.netloc) == self.origin, 'Cross-origin request refused')
        check(not parsed.username and not parsed.password and not parsed.fragment,
              'Invalid request URL')
        headers = {'Accept': 'application/json, text/html, text/event-stream'}
        headers.update(extra_headers or {})
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if origin:
            headers['Origin'] = origin
        body = None
        if form is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            body = urlencode(form).encode()
        if data is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(data).encode()
        try:
            try:
                response = self.opener.open(Request(url, body, headers, method=method), timeout=15)
            except HTTPError as error:
                response = error
            with response:
                content = response.read(1024 * 1024 + 1)
                check(len(content) <= 1024 * 1024, 'Oversized response')
                return Response(response.code, response.headers, content)
        except (URLError, TimeoutError, OSError, ValueError):
            raise ProbeFailure('Transport failure; credentials and URLs withheld') from None


class ConsentForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}
        self.action = None
        self.forms = 0
        self.active = False
        self.method = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'form':
            self.forms += 1
            self.active = True
            self.action = values.get('action', '')
            self.method = (values.get('method') or 'get').lower()
        if self.active and tag == 'input' and (values.get('type') or '').lower() == 'hidden' and values.get('name'):
            self.fields[values['name']] = values.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form':
            self.active = False


class OAuthProbe:
    def __init__(self, fixture):
        self.fixture = fixture
        self.browser = Browser(fixture['base_url'])
        check(fixture.get('resource') == self.browser.base + '/pilot/mcp',
              'Pilot resource must match the configured origin and path')
        check(fixture.get('issuer') == self.browser.base, 'Pilot issuer must match configured origin')
        self.metadata = None

    def discover(self):
        f = self.fixture
        protected = self.browser.request('GET', f['resource_metadata_path'])
        check(protected.status == 200, 'Protected-resource metadata unavailable')
        resource = protected.json()
        check(resource.get('resource') == f['resource'], 'Resource metadata audience mismatch')
        check(f['issuer'] in resource.get('authorization_servers', []), 'Unexpected authorization issuer')
        response = self.browser.request('GET', f['authorization_metadata_path'])
        check(response.status == 200, 'Authorization metadata unavailable')
        self.metadata = response.json()
        check(self.metadata.get('issuer') == f['issuer'], 'Issuer metadata mismatch')
        check('S256' in self.metadata.get('code_challenge_methods_supported', []), 'S256 not advertised')
        for name in ('authorization_endpoint', 'token_endpoint'):
            check(isinstance(self.metadata.get(name), str), 'Invalid authorization endpoint metadata')
            endpoint = urlsplit(self.metadata[name])
            check((endpoint.scheme, endpoint.netloc) == self.browser.origin, 'Unexpected authorization origin')
        return resource

    def authorize(self, *, scope='delivery:read delivery:write', overrides=None,
                  consent_overrides=None, expected_status=303, expected_get_error=None,
                  consent_origin=None):
        check(self.metadata is not None, 'Discovery must run first')
        verifier = secrets.token_urlsafe(48)
        state = secrets.token_urlsafe(24)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        query = {'response_type': 'code', 'client_id': self.fixture['client_id'],
                 'redirect_uri': self.fixture['redirect_uri'], 'scope': scope, 'state': state,
                 'code_challenge': challenge, 'code_challenge_method': 'S256',
                 'resource': self.fixture['resource']}
        query.update(overrides or {})
        endpoint = self.metadata['authorization_endpoint']
        page = self.browser.request('GET', endpoint + '?' + urlencode(query))
        if expected_get_error:
            expect_oauth_error(page, expected_get_error)
            check(not page.headers.get('Location'), 'Invalid authorization request redirected')
            return None
        check(page.status == 200, 'Authorization form unavailable')
        cookies = [cookie for cookie in self.browser.cookies if cookie.name == '__Host-pilot_guest']
        check(len(cookies) == 1 and cookies[0].secure and cookies[0].path == '/'
              and not cookies[0].domain_specified and cookies[0].has_nonstandard_attr('HttpOnly')
              and str(cookies[0].get_nonstandard_attr('SameSite')).lower() == 'lax',
              'Guest cookie lacks required host/Secure/HttpOnly/SameSite attributes')
        form = ConsentForm()
        form.feed(page.body.decode())
        check(form.forms == 1 and form.method == 'post', 'Expected exactly one POST consent form')
        check(bool(form.fields.get('request_id')) and bool(form.fields.get('csrf_token')),
              'Missing bound consent request or CSRF token')
        action = urljoin(endpoint, form.action or endpoint)
        values = {**form.fields, **self.fixture.get('consent_fields', {'decision': 'allow'}),
                  **(consent_overrides or {})}
        reply = self.browser.request('POST', action, form=values,
                                     origin=consent_origin or self.fixture['base_url'].rstrip('/'))
        check(reply.status == expected_status, 'Unexpected consent response status')
        if expected_status == 403:
            check(not reply.headers.get('Location'), 'Rejected consent produced a callback')
            return None
        location = reply.headers.get('Location', '')
        target = urlsplit(location)
        registered = urlsplit(self.fixture['redirect_uri'])
        check(not target.fragment and not target.username and not target.password,
              'Unexpected callback fragment or user information')
        check((target.scheme, target.netloc, target.path) ==
              (registered.scheme, registered.netloc, registered.path), 'Unregistered callback location')
        params = parse_qs(target.query)
        check(set(params) <= {'code', 'state', 'iss', 'error'}, 'Unexpected callback parameters')
        if 'iss' in params:
            check(params['iss'] == [self.fixture['issuer']], 'Callback issuer mismatch')
        check(params.get('state') == [state], 'Callback state mismatch')
        if values.get('decision') == 'deny':
            check(params.get('error') == ['access_denied'] and 'code' not in params,
                  'Denied consent issued an authorization code')
            return None
        check(len(params.get('code', [])) == 1 and 'access_token' not in params,
              'Expected code-only callback')
        check('error' not in params, 'Code callback also contained an error')
        return {'code': params['code'][0], 'verifier': verifier, 'scope': scope}

    def exchange(self, grant, *, overrides=None):
        values = {'grant_type': 'authorization_code', 'code': grant['code'],
                  'client_id': self.fixture['client_id'], 'redirect_uri': self.fixture['redirect_uri'],
                  'code_verifier': grant['verifier'], 'resource': self.fixture['resource']}
        values.update(overrides or {})
        return self.browser.request('POST', self.metadata['token_endpoint'], form=values)

    def token(self, response):
        check(response.status == 200, 'Token exchange rejected')
        result = response.json()
        check(isinstance(result.get('access_token'), str) and result['access_token'], 'Missing access token')
        check(str(result.get('token_type', '')).lower() == 'bearer', 'Unexpected token type')
        check(isinstance(result.get('expires_in'), int) and 0 < result['expires_in'] <= 3600,
              'Expected short-lived access token')
        check('no-store' in response.headers.get('Cache-Control', '').lower(), 'Token response may be cached')
        return result


def expect_oauth_error(response, codes):
    check(response.status in (400, 401), 'Expected OAuth client-error status')
    check(response.json().get('error') in codes, 'Unexpected OAuth failure reason')


def run(fixture):
    probe = OAuthProbe(fixture)
    unauthenticated = probe.browser.request('POST', '/pilot/mcp', data={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}})
    check(unauthenticated.status == 401 and 'resource_metadata=' in
          unauthenticated.headers.get('WWW-Authenticate', ''), 'Missing OAuth discovery challenge')
    probe.discover()
    print('PASS protected-resource and authorization metadata', flush=True)
    probe.authorize(consent_overrides={'decision': 'deny'})
    probe.authorize(consent_overrides={'csrf_token': 'invalid-csrf'}, expected_status=403)
    probe.authorize(consent_origin='https://untrusted.invalid', expected_status=403)
    probe.authorize(overrides={'redirect_uri': 'https://untrusted.invalid/callback'},
                    expected_get_error={'invalid_request'})
    probe.authorize(overrides={'code_challenge_method': 'plain'}, expected_get_error={'invalid_request'})
    print('PASS denied consent, CSRF/Origin, redirect allowlist and PKCE downgrade rejection', flush=True)
    grant = probe.authorize()
    expect_oauth_error(probe.exchange(grant, overrides={'code_verifier': secrets.token_urlsafe(48)}),
                       {'invalid_grant'})
    # A rejected verifier may consume the code; always start a fresh independent grant.
    grant = probe.authorize()
    result = probe.token(probe.exchange(grant))
    expect_oauth_error(probe.exchange(grant), {'invalid_grant'})
    print('PASS browser consent, PKCE exchange, wrong verifier and code replay rejection', flush=True)
    grant = probe.authorize()
    expect_oauth_error(probe.exchange(grant, overrides={'redirect_uri': 'https://untrusted.invalid/callback'}),
                       {'invalid_grant', 'invalid_request'})
    grant = probe.authorize()
    expect_oauth_error(probe.exchange(grant, overrides={'resource': 'https://untrusted.invalid/mcp'}),
                       {'invalid_target', 'invalid_grant'})
    print('PASS token redirect and resource binding', flush=True)
    readonly = probe.token(probe.exchange(probe.authorize(scope='delivery:read')))
    check(set(readonly.get('scope', '').split()) == {'delivery:read'}, 'Read-only scope was widened')
    print('PASS read-only authorization is not widened', flush=True)
    operator = probe.browser.request('GET', '/pilot/operator/session', token=readonly['access_token'])
    check(operator.status == 401, 'Customer token granted operator session access')

    def access(token, expected):
        reply = probe.browser.request('POST', '/pilot/mcp', token=token, data={
            'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': '2025-11-25', 'capabilities': {},
                'clientInfo': {'name': 'independent-pilot-probe', 'version': '0.1.0'}}})
        check(reply.status == expected, 'Unexpected pilot MCP authorization result')

    fresh = probe.token(probe.exchange(probe.authorize()))
    access(fresh['access_token'], 200)
    refresh_values = {'grant_type': 'refresh_token', 'client_id': fixture['client_id'],
                      'refresh_token': fresh['refresh_token'], 'resource': fixture['resource']}
    rotated = probe.token(probe.browser.request('POST', probe.metadata['token_endpoint'], form=refresh_values))
    check(rotated['refresh_token'] != fresh['refresh_token'], 'Refresh token was not rotated')
    access(rotated['access_token'], 200)
    expect_oauth_error(probe.browser.request('POST', probe.metadata['token_endpoint'], form=refresh_values),
                       {'invalid_grant'})
    access(rotated['access_token'], 401)
    print('PASS operator separation, refresh rotation/reuse rejection and grant-family revocation', flush=True)
    revocable = probe.token(probe.exchange(probe.authorize()))
    revoke = probe.browser.request('POST', probe.metadata['revocation_endpoint'], form={
        'client_id': fixture['client_id'], 'token': revocable['refresh_token'],
        'token_type_hint': 'refresh_token'})
    check(revoke.status == 200, 'Revocation rejected')
    access(revocable['access_token'], 401)
    print('PASS explicit revocation invalidates access', flush=True)
    print('PASS protocol-only probe; actual Muse and Stripe UI flows not exercised', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', required=True, type=Path)
    args = parser.parse_args()
    try:
        fixture = json.loads(args.fixture.read_text())
        run(fixture)
    except (ProbeFailure, ValueError, KeyError, TypeError, OSError) as error:
        print('FAIL ' + (str(error) if isinstance(error, ProbeFailure) else 'Invalid fixture or response'),
              file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
