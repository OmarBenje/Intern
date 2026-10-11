import base64
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from django.test import SimpleTestCase, override_settings

from jobboard.api.core import APIError
from jobboard.integrations.submission import GreenhouseAdapter, basic_form


def question(name='question_1', kind='input_text', required=True, values=None):
    field = {'name': name, 'type': kind}
    if values is not None:
        field['values'] = values
    return {'label': 'Question', 'required': required, 'fields': [field]}


@override_settings(GREENHOUSE_API_KEYS={'acme': 'test-partner-key'})
class SubmissionAdapterTests(SimpleTestCase):
    def setUp(self):
        self.board = SimpleNamespace(provider='greenhouse', instance='global', board_key='acme', enabled=True, submission_mode='partner_api')
        self.source = SimpleNamespace(board=self.board, external_id='123')
        self.adapter = GreenhouseAdapter(self.source)

    def fetch(self, questions, **extra):
        payload = {'id': 123, 'questions': questions, **extra}
        client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
        with patch('jobboard.integrations.submission.httpx.Client', return_value=client):
            return self.adapter.fetch_form()

    def revision(self, form=None):
        return SimpleNamespace(answers=[{'field_key': 'first_name', 'value': 'Ada'}, {'field_key': 'email', 'value': 'ada@example.com'}], form_snapshot=form or basic_form())

    def test_minimal_form_does_not_invent_resume_requirement(self):
        form = self.fetch([])
        self.assertTrue(form['supported'])
        self.assertEqual({f['key'] for f in form['fields']}, {'first_name', 'last_name', 'email'})
        self.assertTrue(all(f['required'] for f in form['fields']))
        optional = self.fetch([question('resume', 'input_file', required=False)])
        self.assertFalse(next(f for f in optional['fields'] if f['key'] == 'resume')['required'])

    def test_file_alternative_uses_verified_file_field(self):
        resume = question('resume', 'input_file')
        resume['fields'].append({'name': 'resume_text', 'type': 'textarea'})
        form = self.fetch([resume])
        self.assertTrue(form['supported'])
        self.assertIn('resume', {f['key'] for f in form['fields']})
        self.assertNotIn('resume_text', {f['key'] for f in form['fields']})

    def test_malformed_forms_are_rejected_before_a_dossier_is_created(self):
        empty = question()
        empty['fields'] = []
        cases = [
            [empty], [None], [question(required='false')],
            [question(), question()],
            [question('first_name', 'multi_value_single_select', values=[{'value': 1, 'label': 'One'}])],
            [question(kind='multi_value_single_select', values=[{}])],
            [question(kind='multi_value_single_select', values=None)],
            [question(kind='multi_value_single_select', values=[{'value': [], 'label': 'Invalid'}])],
            [question(kind='multi_value_single_select', values=[{'value': True, 'label': 'Invalid'}])],
            [question(kind='multi_value_single_select', values=[{'value': 1, 'label': 2}])],
            [question(kind='multi_value_single_select', values=[{'value': 1, 'label': 'One'}, {'value': 1, 'label': 'Duplicate'}])],
            [question(values=[{'value': 1, 'label': 'Unexpected'}])],
            [question('resume', 'textarea')],
            [question(name=f'question_{i}') for i in range(201)],
        ]
        for questions in cases:
            with self.subTest(questions=questions[:1]):
                with self.assertRaises(APIError) as raised:
                    self.fetch(questions)
                self.assertEqual(raised.exception.code, 'form_unavailable')
                self.assertEqual(raised.exception.status, 503)

    def test_options_are_normalized_and_fingerprint_ignores_fetch_time(self):
        questions = [question(kind='multi_value_single_select', values=[{'value': 0, 'label': 'No'}, {'value': 1, 'label': 'Yes', 'extra': 'ignored'}])]
        first, second = self.fetch(questions), self.fetch(questions)
        self.assertEqual(first['form_fingerprint'], second['form_fingerprint'])
        self.assertEqual(first['fields'][-1]['options'][-1], {'value': 1, 'label': 'Yes'})

    def test_compliance_and_unsupported_transport_fields_fail_closed(self):
        for section in ['location_questions', 'compliance', 'data_compliance', 'demographic_questions']:
            with self.subTest(section=section):
                form = self.fetch([], **{section: [{'required': True}]})
                self.assertFalse(form['supported'])
                self.assertEqual(form['notices'][0]['kind'], section)
        self.assertFalse(self.fetch([question('resume_url')])['supported'])
        self.assertFalse(self.fetch([question('question_1', 'input_file')])['supported'])

    def test_form_network_errors_redirects_and_size_are_safe(self):
        for mode in ['redirect', 'timeout', 'oversize']:
            calls = []

            def handler(request):
                calls.append(request)
                if mode == 'timeout':
                    raise httpx.ReadTimeout('timeout', request=request)
                if mode == 'redirect':
                    return httpx.Response(302, headers={'Location': 'http://localhost/private'})
                return httpx.Response(200, content=b'x' * (2 * 1024 * 1024 + 1))

            client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
            with patch('jobboard.integrations.submission.httpx.Client', return_value=client):
                with self.assertRaises(APIError):
                    self.adapter.fetch_form()
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0].url.host, 'boards-api.greenhouse.io')

    def test_submit_statuses_never_retry_and_preserve_uncertainty(self):
        for status, expected in [(200, 'succeeded'), (201, 'succeeded'), (400, 'failed'), (401, 'failed'), (403, 'failed'), (404, 'failed'), (413, 'failed'), (422, 'failed'), (429, 'failed'), (500, 'uncertain'), (503, 'uncertain'), (302, 'uncertain'), (408, 'uncertain')]:
            with self.subTest(status=status):
                calls = []

                def handler(request):
                    calls.append(request)
                    return httpx.Response(status, content=b'acknowledgement')

                client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
                with patch('jobboard.integrations.submission.httpx.Client', return_value=client):
                    result = self.adapter.submit(self.revision(), {})
                self.assertEqual(result.status, expected)
                self.assertEqual(len(calls), 1)
                if expected == 'succeeded':
                    self.assertIn(f'greenhouse:http-{status}:sha256:', result.receipt)

    def test_submit_timeout_and_oversized_response_are_uncertain(self):
        for mode in ['timeout', 'oversize']:
            calls = []

            def handler(request):
                calls.append(request)
                if mode == 'timeout':
                    raise httpx.ReadTimeout('timeout', request=request)
                return httpx.Response(200, content=b'x' * (1024 * 1024 + 1))

            client = httpx.Client(transport=httpx.MockTransport(handler))
            with patch('jobboard.integrations.submission.httpx.Client', return_value=client):
                self.assertEqual(self.adapter.submit(self.revision(), {}).status, 'uncertain')
            self.assertEqual(len(calls), 1)

    def test_submit_files_payload_and_private_credentials(self):
        form = self.fetch([question('resume', 'input_file')])
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, content=b'ack')

        client = httpx.Client(transport=httpx.MockTransport(handler))
        document = SimpleNamespace(original_name='resume.pdf')
        with patch('jobboard.integrations.submission.httpx.Client', return_value=client):
            result = self.adapter.submit(self.revision(form), {'resume': (document, b'%PDF-verified-by-service')})
        self.assertEqual(result.status, 'succeeded')
        payload = json.loads(calls[0].content)
        self.assertEqual(base64.b64decode(payload['resume_content']), b'%PDF-verified-by-service')
        self.assertEqual(payload['resume_content_filename'], 'resume.pdf')
        self.assertNotIn('test-partner-key', calls[0].content.decode())
        self.assertEqual(calls[0].url.host, 'boards-api.greenhouse.io')
        self.assertTrue(calls[0].headers['authorization'].startswith('Basic '))

    def test_unrequested_file_rejected_before_network(self):
        with patch('jobboard.integrations.submission.httpx.Client') as client:
            with self.assertRaises(APIError):
                self.adapter.submit(self.revision(), {'resume': (SimpleNamespace(original_name='resume.pdf'), b'bytes')})
        client.assert_not_called()

    def test_submission_requires_explicit_provider_mode_key_and_enabled_board(self):
        for field, value in [('provider', 'unknown'), ('enabled', False), ('submission_mode', 'unsupported')]:
            previous = getattr(self.board, field)
            setattr(self.board, field, value)
            with self.assertRaises(APIError):
                self.adapter.ensure_enabled()
            setattr(self.board, field, previous)
        for key in [None, '', ' ', 123]:
            self.adapter.key = key
            with self.assertRaises(APIError):
                self.adapter.ensure_enabled()
