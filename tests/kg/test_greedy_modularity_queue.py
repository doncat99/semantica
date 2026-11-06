"""Exact CNM oracle and deterministic hub queue-work regression."""
import itertools
from unittest.mock import patch

import networkx as nx
import pytest
from networkx.utils.mapped_queue import MappedQueue

from semantica.kg.community_detector import CommunityDetector


def assert_oracle(graph, resolution=1):
    result = CommunityDetector().detect_communities_greedy_modularity(graph, resolution)
    groups = nx.community.greedy_modularity_communities(graph, resolution=resolution)
    expected = sorted((sorted(group) for group in groups), key=tuple)
    assert result['communities'] == expected
    assert result['modularity'] == nx.community.modularity(graph, groups, resolution=resolution)


def test_hub_does_not_delete_and_reinsert_every_surviving_queue_entry():
    graph = nx.star_graph(127)
    operations = 0
    original_push, original_remove = MappedQueue.push, MappedQueue.remove

    def push(self, *args, **kwargs):
        nonlocal operations
        operations += 1
        return original_push(self, *args, **kwargs)

    def remove(self, *args, **kwargs):
        nonlocal operations
        operations += 1
        return original_remove(self, *args, **kwargs)

    with patch.object(MappedQueue, 'push', push), patch.object(MappedQueue, 'remove', remove):
        result = CommunityDetector().detect_communities_greedy_modularity(graph)
    assert result['communities'] == [list(range(128))]
    assert operations < 128 * 8, operations


def test_all_five_node_simple_graphs_match_networkx():
    pairs = list(itertools.combinations(range(5), 2))
    for mask in range(1, 1 << len(pairs)):
        graph = nx.Graph()
        graph.add_nodes_from(range(5))
        graph.add_edges_from(pair for bit, pair in enumerate(pairs) if mask & (1 << bit))
        assert_oracle(graph)


@pytest.mark.parametrize('resolution', [0.25, 1, 1.7, 4])
@pytest.mark.parametrize('directed,multi', [(False, False), (True, False), (False, True), (True, True)])
def test_seeded_topologies_and_ties_match_networkx(resolution, directed, multi):
    for seed in range(12):
        graph = nx.gnp_random_graph(24, 0.15, seed=seed, directed=directed)
        if multi:
            graph = nx.MultiDiGraph(graph) if directed else nx.MultiGraph(graph)
            graph.add_edges_from(list(graph.edges())[:4])
        graph.add_edge(0, 0)
        graph.add_node(99)
        graph = nx.relabel_nodes(graph, {node: f'n{node}' for node in graph})
        assert_oracle(graph, resolution)


def test_every_merge_gain_and_partition_matches_networkx():
    from networkx.algorithms.community.modularity_max import _greedy_modularity_communities_generator
    from semantica.kg._greedy_modularity import greedy_modularity_partitions

    graphs = [nx.star_graph(48), nx.complete_bipartite_graph(7, 13),
              nx.barbell_graph(8, 5), nx.balanced_tree(3, 3)]
    broom = nx.path_graph(16)
    broom.add_edges_from((15, node) for node in range(16, 40))
    graphs.append(broom)
    double_star = nx.star_graph(20)
    double_star.add_edges_from([(20, 21)] + [(21, node) for node in range(22, 44)])
    graphs.append(double_star)
    for graph in graphs:
        for mapping in ({node: node for node in graph},
                        {node: f'n{len(graph) - node}' for node in graph}):
            graph = nx.relabel_nodes(graph, mapping)
            for resolution in (0.25, 1, 1.7, 4):
                actual = greedy_modularity_partitions(graph, resolution)
                oracle = _greedy_modularity_communities_generator(graph, resolution=resolution)
                partition = True
                while True:
                    expected = next(oracle, None)
                    value = next(actual, None)
                    if expected is None:
                        assert value is None
                        break
                    if partition:
                        assert list(value) == list(expected)
                    else:
                        assert value == expected
                    partition = not partition
