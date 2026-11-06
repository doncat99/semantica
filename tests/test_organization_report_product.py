"""The product handoff survives a worker crash after adoption, without model calls."""
import json
import os
import subprocess
import sys
import threading
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest

from semantica.semantic_artifact_schema import stable_digest


@pytest.mark.parametrize('damage', ['operation', 'digest', 'payload', 'boolean-number'])
def test_adoption_rejects_unbound_or_changed_ack(monkeypatch, damage):
    from semantica import semantic_publication_builder as b
    from semantica.semantic_artifact_schema import KnowledgeReport, ModelReceipt
    identity = dict(projectId='项目/ESG😀', inputRevision='input', recipeDigest='recipe', modelId='model', targetId='target')
    report = KnowledgeReport(id='report:overview:' + b.sha256(b'target').hexdigest()[:24], report_type='overview',
        title='Title', model_receipt_ids=['receipt:r'], content_hash='sha256:' + 'a' * 64, metadata={'number': 1, 'tiny': 1e-7})
    receipts = [ModelReceipt(id='receipt:r', operation='knowledge_explanation', provider='fixture', model='model',
        input_digest='sha256:' + 'a' * 64, output_digest='sha256:' + 'b' * 64)]
    result = dict(report=report.model_dump(mode='json'), receipts=[item.model_dump(mode='json') for item in receipts],
        operationId=stable_digest(list(identity.values())), digest='sha256:' + 'c' * 64)
    if damage == 'operation':
        result['operationId'] = 'sha256:' + 'd' * 64
    elif damage == 'digest':
        result['digest'] = 'not-a-receipt'
    elif damage == 'payload':
        result['receipts'][0]['output_digest'] = 'sha256:' + 'd' * 64
    else:
        result['report']['metadata']['number'] = True
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return json.dumps(result).encode()
    monkeypatch.setattr(b.urllib.request, 'urlopen', lambda *a, **kw: Response())
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture')
    request = SimpleNamespace(organization_reports=SimpleNamespace(base_url='http://127.0.0.1/v1/products/semantic-organization', authorization_env='OPENAI_API_KEY'))
    token = b._native_build.set((request, None, None))
    try:
        with pytest.raises(b.SemanticArtifactError, match='receipt identity|ACK differs'):
            b._organization_report_product('adopt', identity, report=report, receipts=receipts)
    finally:
        b._native_build.reset(token)


def test_paid_report_adoption_survives_worker_exit_and_revalidates_grounding(tmp_path):
    saved = {}
    class Product(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.headers['Authorization'] == 'Bearer fixture-token'
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            key = stable_digest([payload[name] for name in ('projectId', 'inputRevision', 'recipeDigest', 'modelId', 'targetId')])
            if self.path.endswith('/adopt'):
                saved[key] = dict(report=payload['report'], receipts=payload['receipts'], operationId=key, digest='sha256:' + 'a' * 64)
            body = json.dumps(saved.get(key, {'report': None})).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Product)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    script = r'''
import os, sys
from pathlib import Path
from types import SimpleNamespace as NS
from semantica import semantic_publication_builder as b
from semantica.semantic_artifact_schema import EvidenceSpan, ModelReceipt, ReportSection
counter = Path(sys.argv[2])
def model(context, relay):
    counter.write_text(counter.read_text() + 'paid\n' if counter.exists() else 'paid\n')
    return [ReportSection(title='Finding', text='Exact source', evidence_ids=['e1'])], [ModelReceipt(id='r1', operation='knowledge_explanation', provider='fixture', model='test', input_digest='sha256:'+'1'*64, output_digest='sha256:'+'2'*64)]
b._grounded_explanation = model
span = EvidenceSpan(id='e1', representation_id='source', quote='Exact source', locator=dict(representation_id='source', quote='Exact source', origin='adapter', quality='precise', start_char=0, end_char=12))
request = NS(input_revision='input', organization_reports=NS(base_url=sys.argv[1], authorization_env='OPENAI_API_KEY', recipe_digest='sha256:'+'a'*64))
token = b._native_build.set((request, None, None))
try:
    reports, receipts = b._explanation_reports('项目😀', [{'passages':[span]}], [], [], [], [], [], [span], NS(model_id='test'), target_ids=['项目😀'])
    assert reports[0].evidence_ids == ['e1'] and receipts[0].id == 'r1'
    assert 'summary' not in reports[0].model_dump(mode='json')
    assert reports[0].sections[0].text == 'Exact source'
finally:
    b._native_build.reset(token)
os._exit(int(sys.argv[3]))
'''
    env = {**os.environ, 'OPENAI_API_KEY': 'fixture-token'}
    args = [sys.executable, '-c', script, f'http://127.0.0.1:{server.server_port}/v1/products/semantic-organization', str(tmp_path / 'calls')]
    try:
        assert subprocess.run([*args, '73'], env=env, timeout=30).returncode == 73
        assert subprocess.run([*args, '0'], env=env, timeout=30).returncode == 0
        assert (tmp_path / 'calls').read_text() == 'paid\n'
        next(iter(saved.values()))['report']['metadata']['input_digest'] = 'sha256:' + 'b' * 64
        result = subprocess.run([*args, '0'], env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode != 0 and 'grounding identity is invalid' in result.stderr
        assert (tmp_path / 'calls').read_text() == 'paid\n'
    finally:
        server.shutdown()
        server.server_close()


def test_organization_report_has_one_canonical_body_and_rejects_duplicate_summary():
    from pydantic import ValidationError
    from semantica.semantic_artifact_schema import KnowledgeReport, ReportSection
    report = KnowledgeReport(id='report:overview', report_type='overview', title='Overview',
        sections=[ReportSection(title='Finding', text='Complete paid prose', evidence_ids=['e1'])],
        content_hash='sha256:' + 'a' * 64)
    payload = report.model_dump(mode='json')
    assert 'summary' not in payload
    assert json.dumps(payload).count('Complete paid prose') == 1
    with pytest.raises(ValidationError):
        KnowledgeReport.model_validate({**payload, 'summary': 'Complete paid prose'})
