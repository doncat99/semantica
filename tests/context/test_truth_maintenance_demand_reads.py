"""Retrieval validates only declared dependencies at one committed version."""
import importlib.util

import pytest

from semantica.context import RetrievedContext, TruthMaintenanceContextFilter
from semantica.reasoning import FactSupport, TruthMaintenanceSession
from semantica.utils.exceptions import ProcessingError


def test_retired_tms_payload_apis_are_absent():
    import semantica.reasoning as public
    from semantica.reasoning import truth_maintenance_types
    for name in ('snapshot', 'to_checkpoint', 'from_checkpoint'):
        assert not hasattr(TruthMaintenanceSession, name)
    assert not hasattr(public, 'TruthMaintenanceSnapshot')
    assert not hasattr(truth_maintenance_types, 'TruthMaintenanceSnapshot')
    assert importlib.util.find_spec('semantica.reasoning._truth_maintenance_checkpoint') is None


class LookupOnly(dict):
    def __iter__(self):
        raise AssertionError('retrieval must not enumerate session state')
    def keys(self):
        raise AssertionError('retrieval must not enumerate session state')
    def values(self):
        raise AssertionError('retrieval must not enumerate session state')
    def items(self):
        raise AssertionError('retrieval must not enumerate session state')


def candidate():
    return RetrievedContext(content='selected', score=1, source='test', metadata={
        'truth_maintenance': {'schema_version': 1, 'session_id': 'session',
        'required_facts': ['A(x)'], 'required_support_ids': ['selected']}})


def test_dependency_validation_never_enumerates_unrelated_facts_or_supports():
    session = TruthMaintenanceSession(rules=[])
    session.apply(assertions=[FactSupport('selected', 'A(x)')])
    # Iteration-resistant indexes model arbitrarily many unrelated entries.
    session._state.active_facts = LookupOnly({'A(x)': True})
    session._state.active_supports = LookupOnly(session._state.active_supports)
    gate = TruthMaintenanceContextFilter(session, session_id='session')
    results = gate.filter_contexts([candidate()], version=gate.version)
    assert [item.content for item in results] == ['selected']
    assert results[0].metadata['truth_maintenance_validation']['version'] == session.version


def test_filter_fails_closed_if_candidates_mutate_session_during_iteration():
    session = TruthMaintenanceSession(rules=[])
    session.apply(assertions=[FactSupport('selected', 'A(x)')])
    gate = TruthMaintenanceContextFilter(session, session_id='session')
    version = gate.version
    def candidates():
        yield candidate()
        session.apply(retractions=['selected'])
    with pytest.raises(ProcessingError):
        gate.filter_contexts(candidates(), version=version)
