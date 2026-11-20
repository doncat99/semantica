"""Bounded publication input orchestration for the existing KG analytics owners."""
import json
import time

from ..semantic_worker_context import check_query_cancellation, count_query_work
from ..utils.exceptions import ProcessingError


def analyze_publication(owner, project, generation, *, max_nodes=1024,
        max_edges=2048, max_pages=32, max_bytes=2097152, max_millis=5000):
    from .centrality_calculator import CentralityCalculator
    from .community_detector import CommunityDetector
    from .connectivity_analyzer import ConnectivityAnalyzer
    from .graph_validator import GraphValidator

    limits = ((max_nodes, 1024), (max_edges, 2048), (max_pages, 32),
        (max_bytes, 2097152), (max_millis, 5000))
    if any(type(value) is not int or not 1 <= value <= maximum for value, maximum in limits):
        raise ProcessingError('Invalid native analysis budget')
    deadline = time.monotonic() + max_millis / 1000
    nodes, links = [], []
    pages = read_bytes = 0

    def check():
        check_query_cancellation()
        return time.monotonic() < deadline

    def response(status, metrics=None, detail=None):
        check_query_cancellation()
        result = dict(project=project, generation=generation, status=status,
            nodeCount=len(nodes), relationCount=len(links), pages=pages,
            projectionBytes=read_bytes, metrics=metrics or {})
        if detail:
            result['detail'] = detail
        if len(json.dumps(result, ensure_ascii=False).encode()) > 1048576:
            raise ProcessingError('Native analysis response exceeds byte budget')
        return result

    for kind, fields, destination, maximum in (
            ('nodes', ['id','name','entityType'], nodes, max_nodes),
            ('topology', ['id','source','target','predicate'], links, max_edges)):
        after = None
        while True:
            if not check() or pages >= max_pages or read_bytes >= max_bytes or len(destination) >= maximum:
                return response('incomplete', detail='Publication analysis reached its input or time budget.')
            remaining = max_bytes - read_bytes
            envelope = dict(project=project, generation=generation, nodes=[], links=[],
                fields=fields, next_cursor=None)
            if remaining < len(json.dumps(envelope, ensure_ascii=False).encode()):
                return response('incomplete', detail='Publication analysis reached its input byte budget.')
            page = owner.read_publication_scene(project, generation, dict(kind=kind, fields=fields,
                limit=min(128, maximum-len(destination)), maxBytes=min(262144, remaining),
                **({'after': after} if after else {})))
            pages += 1
            size = len(json.dumps(page, ensure_ascii=False).encode())
            if size > min(262144, remaining):
                raise ProcessingError('Native analysis scene exceeded its requested byte budget')
            read_bytes += size
            count_query_work('analysisScenePages')
            count_query_work('analysisProjectionBytes', size)
            rows = page['nodes' if kind == 'nodes' else 'links']
            destination.extend(rows)
            count_query_work('analysisProjectionRows', len(rows))
            cursor = page['next_cursor']
            if cursor is None:
                break
            if not rows or cursor == after:
                raise ProcessingError('Native analysis scene cursor did not advance')
            after = cursor

    ids = {node['id'] for node in nodes}
    if any(link['source'] not in ids or link['target'] not in ids for link in links):
        raise ProcessingError('Native analysis topology contains an unavailable endpoint')
    graph = dict(entities=[dict(id=node['id'], name=node['name'], text=node['name'], type=node['entityType'])
        for node in nodes], relationships=[dict(link, type=link['predicate']) for link in links])
    centrality = CentralityCalculator()
    operations = (
        ('centrality', lambda: centrality.calculate_degree_centrality(graph)),
        ('pagerank', lambda: centrality.calculate_pagerank(graph)),
        ('community', lambda: CommunityDetector().detect_communities(graph)),
        ('connectivity', lambda: ConnectivityAnalyzer().analyze_connectivity(graph)),
        ('validation', lambda: GraphValidator().validate(graph).to_dict()),
    )
    metrics = {}
    errors = 0
    for name, calculate in operations:
        if not check():
            return response('incomplete', detail='Publication analysis reached its calculation deadline.')
        try:
            metrics[name] = calculate()
        except Exception as error:
            check_query_cancellation()
            metrics[name] = dict(error=str(error)[:1024])
            errors += 1
        if not check():
            return response('incomplete', detail='Publication analysis reached its calculation deadline.')
    if errors == len(operations):
        raise ProcessingError('All requested native analytics metrics failed')
    return response('partial' if errors else 'ready', metrics)
