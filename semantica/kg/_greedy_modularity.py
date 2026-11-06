"""Exact CNM merges with bulk maintenance of the survivor's priority queue.

Adapted from NetworkX 3.6.1 modularity_max.py; its BSD license is reproduced in
the notice below. Score arithmetic and community identifiers are kept
unchanged; only priority-queue maintenance is consolidated.

NetworkX is distributed with the 3-clause BSD license.

::

   Copyright (c) 2004-2025, NetworkX Developers
   Aric Hagberg <hagberg@lanl.gov>
   Dan Schult <dschult@colgate.edu>
   Pieter Swart <swart@lanl.gov>
   All rights reserved.

   Redistribution and use in source and binary forms, with or without
   modification, are permitted provided that the following conditions are
   met:

     * Redistributions of source code must retain the above copyright
       notice, this list of conditions and the following disclaimer.

     * Redistributions in binary form must reproduce the above
       copyright notice, this list of conditions and the following
       disclaimer in the documentation and/or other materials provided
       with the distribution.

     * Neither the name of the NetworkX Developers nor the names of its
       contributors may be used to endorse or promote products derived
       from this software without specific prior written permission.

   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
   "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
   LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
   A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
   OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
   SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
   LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
   DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
   THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
   (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
   OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
from collections import defaultdict

from networkx.utils.mapped_queue import MappedQueue


def greedy_modularity_partitions(graph, resolution=1):
    """Yield the initial partition, then alternating merge gains and partitions."""
    directed = graph.is_directed()
    q0 = 1 / graph.size()
    if directed:
        a = {node: degree * q0 for node, degree in graph.out_degree()}
        b = {node: degree * q0 for node, degree in graph.in_degree()}
    else:
        a = b = {node: degree * q0 * 0.5 for node, degree in graph.degree()}
    scores = defaultdict(lambda: defaultdict(float))
    for u, v in graph.edges():
        if u != v:
            scores[u][v] += 1
            scores[v][u] += 1
    for u, neighbors in scores.items():
        for v, value in neighbors.items():
            scores[u][v] = q0 * value - resolution * (a[u] * b[v] + b[u] * a[v])
    rows = {u: MappedQueue({(u, v): -dq for v, dq in scores[u].items()}) for u in graph}
    maxima = MappedQueue([rows[u].heap[0] for u in graph if len(rows[u])])
    communities = {node: frozenset([node]) for node in graph}
    yield communities.values()
    while len(maxima) > 1:
        negative_gain, u, v = maxima.pop()
        yield -negative_gain
        # Neither u nor v's intermediate roots can be consumed before this merge ends.
        maxima.remove(rows[v].heap[0])
        communities[v] = frozenset(communities[u] | communities[v])
        del communities[u]
        u_neighbors, v_neighbors = set(scores[u]), set(scores[v])
        all_neighbors = (u_neighbors | v_neighbors) - {u, v}
        both_neighbors = u_neighbors & v_neighbors
        for w in all_neighbors:
            if w in both_neighbors:
                gain = scores[v][w] + scores[u][w]
            elif w in v_neighbors:
                gain = scores[v][w] - resolution * (a[u] * b[w] + a[w] * b[u])
            else:
                gain = scores[u][w] - resolution * (a[v] * b[w] + a[w] * b[v])
            scores[v][w] = scores[w][v] = gain
            row = rows[w]
            old_max = row.heap[0]
            if w in v_neighbors:
                row.update((w, v), (w, v), priority=-gain)
                if w in u_neighbors:
                    row.remove((w, u))
            else:
                # Rename the old neighbor directly instead of push followed by remove.
                row.update((w, u), (w, v), priority=-gain)
            new_max = row.heap[0]
            if old_max != new_max or old_max.priority != new_max.priority:
                maxima.update(old_max, new_max)
        for w in scores[u]:
            del scores[w][u]
        del scores[u]
        del rows[u]
        rows[v] = MappedQueue({(v, w): -gain for w, gain in scores[v].items()})
        if len(rows[v]):
            maxima.push(rows[v].heap[0])
        a[v] += a[u]
        a[u] = 0
        if directed:
            b[v] += b[u]
            b[u] = 0
        yield communities.values()


def greedy_modularity_communities(graph, resolution=1):
    """Stop exact greedy merging before the next negative modularity gain."""
    partitions = greedy_modularity_partitions(graph, resolution)
    communities = next(partitions)
    while len(communities) > 1:
        try:
            gain = next(partitions)
        except StopIteration:
            break
        if gain < 0:
            break
        communities = next(partitions)
    return sorted(communities, key=len, reverse=True)
