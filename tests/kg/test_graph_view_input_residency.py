"""Graph normalization must not copy all raw input references before traversal."""
import tracemalloc

import pytest

from semantica.kg import _graph_view


@pytest.mark.parametrize('field,extract', [
    ('entities', _graph_view._extract_nodes),
    ('relationships', _graph_view._extract_edges),
])
def test_dictionary_input_traversal_does_not_allocate_a_project_sized_list(field, extract):
    records = [{'id': str(index), 'source': str(index), 'target': str(index + 1)}
               for index in range(16_384)]
    graph = {field: records}
    tracemalloc.start()
    try:
        values = extract(graph)
        for index, value in enumerate(values):
            assert value is records[index]
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert index + 1 == len(records)
    assert peak < 16_384, f'raw graph traversal allocated {peak} bytes'


def test_dictionary_input_preserves_collection_order_and_normalized_graph():
    graph = {
        'entities': {'isolated': {}, 'a': {}}, 'nodes': [{'id': 'b'}, 'a'],
        'relationships': [{'source': 'a', 'target': 'b'}],
        'edges': [('b', 'c'), ('a', 'b'), ('c', 'c')],
    }
    assert list(_graph_view._extract_nodes(graph)) == ['isolated', 'a', {'id': 'b'}, 'a']
    view = _graph_view.build_graph_view(graph)
    assert view.nodes == ['isolated', 'a', 'b', 'c']
    assert view.edges == [('a', 'b'), ('b', 'c'), ('c', 'c')]
