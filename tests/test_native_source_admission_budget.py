"""Measure actual admitted-source reads and process RSS independently of parsing."""
import json
from pathlib import Path
import subprocess
import sys

from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from semantica.semantic_source_artifact import _load_parsed_source
from tests.test_semantic_artifact import _request


def prepared(root, size):
    root.mkdir()
    source = root / 'source.txt'
    source.write_text('x' * size + '\nsource-tail-界')
    return SemanticArtifactBuildRequest.model_validate(_request(source, root / 'out')['params'])


def test_admission_never_reads_whole_native_artifact_and_hydrates_exact_tail(tmp_path, monkeypatch):
    request = prepared(tmp_path / 'source', 512*1024)
    source, ref = request.sources[0], request.parsed_sources[0]
    read_bytes = Path.read_bytes

    def reject_whole_artifact(path):
        assert path.resolve() != Path(ref.artifact_path).resolve(), 'native admission must not parse a whole source JSON'
        return read_bytes(path)

    monkeypatch.setattr(Path, 'read_bytes', reject_whole_artifact)
    parsed = _load_parsed_source(source, ref, False, {'mode': 'local'})
    assert not {'text', 'document', 'pages', 'sections'} & parsed.document.keys()
    assert parsed.text[len(parsed.text)-13:len(parsed.text)] == 'source-tail-界'
    assert parsed.windows[-1][2].endswith('source-tail-界')
    assert parsed.windows.ranges[-1][1] == len(parsed.text)
    assert not isinstance(parsed.text, str)


def test_admission_does_not_enumerate_window_or_scalar_address_maps(tmp_path, monkeypatch):
    from semantica import semantic_document_reader as reader
    request = prepared(tmp_path / 'source', 512*1024)
    def reject(*args, **kwargs):
        raise AssertionError('admission must retain lazy addresses without enumerating source maps')
    with monkeypatch.context() as scoped:
        scoped.setattr(reader, 'read_source_window_ranges', reject)
        scoped.setattr(reader, 'read_source_native_ranges', reject)
        parsed = _load_parsed_source(request.sources[0], request.parsed_sources[0], False, {'mode': 'local'})
    assert len(parsed.windows) > 1
    assert parsed.windows[-1][2].endswith('source-tail-界')


_RSS_PROBE = '''
import json, resource, sys
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from semantica.semantic_source_artifact import _load_parsed_source
from semantica import semantic_source_artifact as owner
from semantica.explorer.search_index import _file_identity
from semantica.semantic_document_reader import read_source_header
from blake3 import blake3
request=SemanticArtifactBuildRequest.model_validate_json(sys.argv[1])
baseline=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
phases=[]
def observe(name):
    original=getattr(owner,name)
    def call(*args,**kwargs):
        result=original(*args,**kwargs)
        phases.append((name,resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
        return result
    setattr(owner,name,call)
for name in ('_digest_file','source_content_revision','_source_reader_request'):
    observe(name)
source=_load_parsed_source(request.sources[0],request.parsed_sources[0],False,{'mode':'local'})
assert source.windows[-1][2].endswith('source-tail-界')
rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
unit=1 if sys.platform=='darwin' else 1024
print(json.dumps({'rssBytes':rss*unit,'baselineBytes':baseline*unit,'growthBytes':(rss-baseline)*unit,'length':len(source.text),'phases':phases}))
'''


def test_admission_rss_does_not_scale_with_source_body(tmp_path):
    measured = []
    for size in (512*1024, 16*1024*1024):
        request = prepared(tmp_path / str(size), size)
        child = subprocess.run([sys.executable, '-c', _RSS_PROBE, request.model_dump_json(by_alias=True)],
            capture_output=True, text=True, check=True, timeout=60)
        measured.append(json.loads(child.stdout.strip().splitlines()[-1]))
    assert measured[1]['length'] > measured[0]['length'] + 15*1024*1024
    assert measured[1]['growthBytes'] < 8*1024*1024, json.dumps(measured)
