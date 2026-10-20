"""Independent Stripe contract fixtures; fake HTTP, never real provider evidence.

Run with the isolated backend on PYTHONPATH and its dependency environment.
"""
import copy
import hashlib
import hmac
import json
import time
import unittest
import httpx
from delivery.pilot.payments import StripeTestPayments, PaymentValidationError
from delivery.service import ServiceError


class PaymentContractTests(unittest.TestCase):
    def setUp(self):
        self.job = {'id': 'e77a3bbe-8cba-4dce-bc7e-51e379d03965', 'tenant': 'fixture-guest',
                    'price_minor': 500, 'currency': 'USD', 'checkout_id': 'cs_test_fixture',
                    'payment_id': None}
        metadata = {'pilot_job_id': self.job['id'], 'pilot_tenant': 'fixture-guest',
                    'execution_mode': 'human_test'}
        self.session = {'id': 'cs_test_fixture', 'object': 'checkout.session', 'livemode': False,
                        'metadata': metadata, 'mode': 'payment', 'amount_total': 500,
                        'currency': 'usd', 'status': 'complete', 'payment_status': 'unpaid',
                        'payment_intent': 'pi_fixture'}
        self.intent = {'id': 'pi_fixture', 'object': 'payment_intent', 'livemode': False,
                       'metadata': metadata, 'amount': 500, 'currency': 'usd',
                       'capture_method': 'manual', 'status': 'requires_payment_method',
                       'amount_capturable': 0, 'amount_received': 0}
        self.calls = []

    def adapter(self):
        def transport(request):
            self.calls.append((request.method, request.url.path))
            if request.method == 'GET' and request.url.path.endswith('/checkout/sessions/cs_test_fixture'):
                payload = self.session
            elif request.method == 'GET' and request.url.path.endswith('/payment_intents/pi_fixture'):
                payload = self.intent
            elif request.method == 'POST' and request.url.path.endswith('/checkout/sessions/cs_test_fixture/expire'):
                self.session['status'] = 'expired'
                self.intent['status'] = 'canceled'
                payload = self.session
            elif request.method == 'POST' and request.url.path.endswith('/payment_intents/pi_fixture/cancel'):
                if self.intent['status'] != 'requires_capture':
                    return httpx.Response(400, json={'error': {'message': 'Expire open Checkout instead'}})
                self.intent['status'] = 'canceled'
                payload = self.intent
            else:
                raise AssertionError('Unexpected fake provider request')
            return httpx.Response(200, json=copy.deepcopy(payload))
        return StripeTestPayments('sk_test_fixture_only_no_provider_access', 'whsec_fixture_only',
                                  'https://pilot.example.test/return', 'https://pilot.example.test/cancel',
                                  client=httpx.Client(transport=httpx.MockTransport(transport)))

    def test_completed_checkout_does_not_prove_authorization(self):
        state = self.adapter().reconcile(self.job)
        self.assertEqual(state['status'], 'pending')

    def test_wrong_amount_or_live_mode_cannot_authorize(self):
        for field, value in [('livemode', True), ('amount', 501), ('currency', 'eur')]:
            with self.subTest(field=field):
                original = self.intent[field]
                self.intent[field] = value
                with self.assertRaises(PaymentValidationError):
                    self.adapter().reconcile(self.job)
                self.intent[field] = original

    def test_checkout_from_other_guest_is_rejected(self):
        self.session['metadata'] = {**self.session['metadata'], 'pilot_tenant': 'other-guest'}
        with self.assertRaises(PaymentValidationError):
            self.adapter().reconcile(self.job)

    def test_cancel_unpaid_checkout_with_existing_intent_expires_session(self):
        self.session['status'] = 'open'
        result = self.adapter().void(self.job, 'void-test-operation')
        self.assertEqual(result['status'], 'voided')
        self.assertIn(('POST', '/v1/checkout/sessions/cs_test_fixture/expire'), self.calls)
        self.assertNotIn(('POST', '/v1/payment_intents/pi_fixture/cancel'), self.calls)

    def test_live_provider_key_is_refused_before_network(self):
        with self.assertRaises(ValueError):
            StripeTestPayments('sk_live_fixture_refuse', 'whsec_fixture_only',
                               'https://pilot.example.test/return', 'https://pilot.example.test/cancel')

    def test_webhook_signature_cannot_authenticate_modified_body_or_live_event(self):
        body = json.dumps({'id': 'evt_fixture', 'livemode': False,
                           'type': 'checkout.session.completed', 'data': {'object': self.session}}).encode()
        timestamp = str(int(time.time()))

        def sign(value):
            digest = hmac.new(b'whsec_fixture_only', timestamp.encode() + b'.' + value,
                              hashlib.sha256).hexdigest()
            return 't=' + timestamp + ',v1=' + digest

        adapter = self.adapter()
        self.assertEqual(adapter.verify_webhook(body, sign(body))['id'], 'evt_fixture')
        with self.assertRaises(ServiceError):
            adapter.verify_webhook(body + b' ', sign(body))
        live = json.loads(body)
        live['livemode'] = True
        live_body = json.dumps(live).encode()
        with self.assertRaises(ServiceError):
            adapter.verify_webhook(live_body, sign(live_body))


if __name__ == '__main__':
    unittest.main()
