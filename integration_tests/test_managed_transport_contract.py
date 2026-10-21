"""Independent HTTP boundary checks with synthetic RSA tokens; no provider writes.

Run with the managed backend on PYTHONPATH and its installed test dependencies.
The fake service records dispatch: denied mutations must never reach it.
"""
import json
import time

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import httpx
import jwt
import pytest

from delivery.app import create_app
from delivery.managed_auth import DescopeTokenVerifier
from delivery.service import ServiceError

BASE = 'https://delivery.geniemobility.ai'
RESOURCE = BASE + '/mcp'
ISSUER = 'https://identity.example/project'
DISCOVERY = ISSUER + '/.well-known/openid-configuration'
JWKS = 'https://identity.example/keys'
OBJECT = '12345678-1234-4234-8234-123456789abc'
NOW = '2030-01-01T12:00:00Z'
LEGACY = 'independent-synthetic-legacy-key-000000'
QUOTE = dict(pickup_address='Test pickup', dropoff_address='Test dropoff',
             package_description='Test parcel', requested_ready_time=NOW,
             handoff_type='meet_at_door')
WRITES = [
    ('get_delivery_quote', '/v1/quotes', QUOTE),
    ('reserve_delivery', '/v1/reservations', {'quote_id': OBJECT}),
    ('confirm_delivery', '/v1/deliveries', {'reservation_id': OBJECT, 'user_confirmed': True}),
    ('submit_pickup_details', f'/v1/deliveries/{OBJECT}/pickup-details', {
        'delivery_id': OBJECT, 'restaurant_confirmation': True,
        'restaurant_order_reference': 'TEST', 'pickup_name': 'Test', 'ready_at': NOW}),
    ('cancel_delivery', f'/v1/deliveries/{OBJECT}/cancel', {'delivery_id': OBJECT, 'reason': 'Test'}),
]


class RecordingService:
    def __init__(self):
        self.calls = []
        self.owner = None

    def initialize(self):
        pass

    def check_health(self):
        pass

    def execute(self, operation, tenant, key, payload):
        self.calls.append((operation, tenant))
        if operation == 'get_delivery_quote':
            self.owner = tenant
            return dict(quote_id=OBJECT, status='quoted', simulation=True,
                        price_cents=500, currency='USD', eligible=True,
                        eligibility='simulated', eligibility_note='Test',
                        estimated_delivery_at=NOW,
                        estimated_window={'earliest': NOW, 'latest': NOW, 'simulation': True},
                        eta_note='Test', expires_at=NOW, cancellation_terms='Test',
                        terms=dict(simulation=True, price='Test', confirmation='Test',
                                   pickup='Test', cancellation='Test', eligibility='Test'))
        if tenant != self.owner:
            raise ServiceError(404, 'not_found', 'Not found')
        return dict(delivery_id=OBJECT, reservation_id=OBJECT, status='awaiting_pickup_details',
                    simulation=True, payment_status='simulated_authorized', price_cents=500,
                    currency='USD', pickup_details_received=False, ready_at=None,
                    created_at=NOW, updated_at=NOW, cancellation_reason=None, events=[])


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('EXTERNAL_BASE_URL', BASE)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid='fixture', alg='RS256', use='sig')

    def remote(request):
        if str(request.url) == DISCOVERY:
            # Project metadata need not enumerate resource-specific scopes or DCR.
            return httpx.Response(200, json={'issuer': ISSUER, 'jwks_uri': JWKS,
                                           'scopes_supported': ['openid', 'email']})
        assert str(request.url) == JWKS
        return httpx.Response(200, json={'keys': [jwk]})

    def token(subject='customer-a', scope='delivery:read delivery:write', **claims):
        payload = dict(iss=ISSUER, aud=RESOURCE, sub=subject, scope=scope,
                       exp=int(time.time()) + 300, client_id='same-native-connector')
        payload.update(claims)
        return jwt.encode(payload, key, algorithm='RS256', headers={'kid': 'fixture'})

    def app(mode='managed'):
        verifier = DescopeTokenVerifier(DISCOVERY, RESOURCE, issuer=ISSUER,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(remote)))
        service = RecordingService()
        return create_app(service=service, api_keys={LEGACY: 'existing-sandbox'},
                          auth_mode=mode, managed_verifier=verifier), service
    return token, app


def headers(token):
    return {'Authorization': 'Bearer ' + token, 'Idempotency-Key': 'independent-test',
            'Accept': 'application/json, text/event-stream'}


def rpc(client, token, method, params=None):
    return client.post('/mcp', headers=headers(token), json={
        'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})


def test_discovery_advertises_resource_scopes_without_invented_registration(setup):
    token, factory = setup
    app, service = factory()
    with TestClient(app) as client:
        response = client.get('/.well-known/oauth-protected-resource/mcp')
        assert response.status_code == 200
        doc = response.json()
        assert doc['resource'] == RESOURCE
        assert doc['authorization_servers'] == [ISSUER]
        assert set(doc['scopes_supported']) == {'delivery:read', 'delivery:write'}
        challenge = client.post('/mcp')
        assert challenge.status_code == 401
        assert BASE + '/.well-known/oauth-protected-resource/mcp' in challenge.headers['www-authenticate']
        assert rpc(client, token(scope='delivery:read'), 'tools/list').status_code == 200
        assert service.calls == []


@pytest.mark.parametrize('name,path,body', WRITES)
def test_read_only_denies_every_write_before_service_dispatch(setup, name, path, body):
    token, factory = setup
    app, service = factory()
    with TestClient(app) as client:
        bearer = token(scope='delivery:read')
        rest_body = {k: v for k, v in body.items() if k != 'delivery_id'}
        assert client.post(path, headers=headers(bearer), json=rest_body).status_code == 403
        reply = rpc(client, bearer, 'tools/call', {'name': name, 'arguments': {
            **body, 'idempotency_key': 'independent-test'}})
        assert reply.status_code == 200
        assert reply.json()['result']['isError'] is True
        assert 'insufficient_scope' in reply.text
        assert service.calls == []


def test_customer_isolation_survives_same_client_id_and_changed_email(setup):
    token, factory = setup
    app, service = factory()
    with TestClient(app) as client:
        first = token(email='same@example.test', tenant='existing-sandbox')
        assert client.post('/v1/quotes', headers=headers(first), json=QUOTE).status_code == 200
        owner = service.owner
        assert owner.startswith('managed:') and owner != 'existing-sandbox'
        changed = token(email='changed@example.test', client_id='other-connector')
        assert client.get(f'/v1/deliveries/{OBJECT}', headers=headers(changed)).status_code == 200
        outsider = token(subject='customer-b', email='same@example.test', tenant=owner)
        assert client.get(f'/v1/deliveries/{OBJECT}', headers=headers(outsider)).status_code == 404
        denied = rpc(client, outsider, 'tools/call', {'name': 'get_delivery_status',
                                                    'arguments': {'delivery_id': OBJECT}})
        assert denied.json()['result']['isError'] is True
        assert service.calls[0][1] == service.calls[1][1]
        assert service.calls[2][1] == service.calls[3][1] != owner


@pytest.mark.parametrize('claims', [{'aud': 'project-only-audience'}, {'iss': ISSUER + '/other'},
                                   {'exp': 1}, {'scope': 'delivery:write'}])
def test_invalid_claims_rejected_on_both_transports(setup, claims):
    token, factory = setup
    app, service = factory()
    with TestClient(app) as client:
        bearer = token(**claims)
        assert client.get(f'/v1/deliveries/{OBJECT}', headers=headers(bearer)).status_code == 401
        assert rpc(client, bearer, 'tools/list').status_code == 401
        assert service.calls == []


def test_transition_preserves_legacy_identity_but_managed_mode_rejects_key(setup):
    token, factory = setup
    app, service = factory('transition')
    with TestClient(app) as client:
        assert client.post('/v1/quotes', headers=headers(LEGACY), json=QUOTE).status_code == 200
        assert service.owner == 'existing-sandbox'
        assert client.get(f'/v1/deliveries/{OBJECT}', headers=headers(token())).status_code == 404
    app, service = factory('managed')
    with TestClient(app) as client:
        assert rpc(client, LEGACY, 'tools/list').status_code == 401
        assert service.calls == []
