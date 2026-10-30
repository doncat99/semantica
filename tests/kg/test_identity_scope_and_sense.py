import pytest

from semantica.normalize.entity_normalizer import EntityDisambiguator
from tests.kg.test_contextual_identity import scoped, resolve


@pytest.mark.parametrize('name', ['Board', 'Board of Directors', 'Company',
    'Audit Committee', 'Executive Leadership Team', 'Foundation'])
def test_dependent_organizations_do_not_merge_across_unrelated_sources(name):
    rows = [scoped('a', name, f'Our {name} oversees operations.', 'company:a'),
            scoped('b', name, f'Our {name} oversees operations.', 'company:b')]
    assert len(resolve(*rows)) == 2


def test_ticker_parenthesis_is_not_an_abbreviation_definition():
    text = "Signet's shares are listed on the New York Stock Exchange (SIG)."
    rows = [scoped('exchange', 'New York Stock Exchange', text), scoped('ticker', 'SIG', text)]
    assert len(resolve(*rows)) == 2


@pytest.mark.parametrize('name', ['President and Chief Executive Officer',
                                'Chief Human Resources Officer', 'Code of Conduct'])
def test_local_roles_and_policies_are_not_global_concepts_despite_type_noise(name):
    rows = [scoped('a', name, f'Our {name} oversees operations.', 'a'),
            scoped('b', name, f'Our {name} oversees operations.', 'b')]
    for row in rows:
        row['type'] = 'CONCEPT'
    assert len(resolve(*rows)) == 2


@pytest.mark.parametrize('name', ['Scope 1', 'Scope 2', 'Scope 3',
                                'GRI 2: General Disclosures 2021'])
def test_same_named_concept_does_not_require_a_parenthetical_definition(name):
    rows = [scoped('a', name, f'We report {name}.', 'document:a'),
            scoped('b', name, f'We report {name}.', 'document:b')]
    for row in rows:
        row['type'] = 'CONCEPT'
    assert len(resolve(*rows)) == 1


def test_conflicting_descriptions_require_disambiguation_instead_of_certain_merge():
    rows = [scoped('a', 'Mercury', 'Mercury manufactures marine engines.',
                   'document:a', 'manufactures marine engines'),
            scoped('b', 'Mercury', 'Mercury publishes newspapers.',
                   'document:b', 'publishes newspapers')]
    assert len(resolve(*rows)) == 2
    owner = EntityDisambiguator()
    owner.prepare(rows)
    assert owner.compare(*rows)['decision'] == 'unknown'


def test_type_noise_cannot_split_the_same_located_occurrence():
    rows = [scoped('a', 'GRI 2', 'GRI 2 is cited.'), scoped('b', 'GRI 2', 'GRI 2 is cited.')]
    rows[0]['type'], rows[1]['type'] = 'CONCEPT', 'PRODUCT'
    rows[0]['evidence_ids'] = rows[1]['evidence_ids'] = ['exact-span']
    assert len(resolve(*rows)) == 1


def test_same_named_concept_and_dependent_instance_are_not_identity():
    rows = [scoped('a', 'Board', 'Board is a governance concept.'),
            scoped('b', 'Board', 'Our Board oversees operations.')]
    for row, kind in zip(rows, ['concept', 'dependent_entity']):
        row['metadata']['identity_profile'] = {'referent_kind': kind}
    assert len(resolve(*rows)) == 2


def test_source_supported_owner_reuses_dependent_identity_across_documents():
    rows = [scoped('a', 'Audit Committee', 'Acme Audit Committee meets.', 'a'),
            scoped('b', 'Audit Committee', 'Acme Audit Committee reports.', 'b'),
            scoped('c', 'Audit Committee', 'Other Audit Committee meets.', 'c')]
    for row, owner in zip(rows, ['Acme', 'Acme', 'Other']):
        row['metadata']['identity_profile'] = {
            'referent_kind': 'dependent_entity', 'owner': owner,
            'evidence': row['context']}
    assert {frozenset(row.get('merged_from') or [row['id']]) for row in resolve(*rows)} == {
        frozenset({'a', 'b'}), frozenset({'c'})}


def test_missing_description_does_not_bridge_two_incompatible_described_groups():
    rows = [scoped('a', 'Mercury', 'Mercury manufactures engines.', description='manufactures engines'),
            scoped('b', 'Mercury', 'Mercury publishes newspapers.', description='publishes newspapers'),
            scoped('missing', 'Mercury', 'Mercury reports.')]
    assert len(resolve(*rows)) == 3
    assert len(resolve(*rows[::-1])) == 3


def test_missing_description_still_reuses_one_grounded_definition():
    rows = [scoped('a', 'Acme', 'Acme manufactures engines.', description='manufactures engines'),
            scoped('b', 'Acme', 'Acme reports.', 'other-document')]
    assert len(resolve(*rows)) == 1


def test_reusing_owner_does_not_keep_previous_descriptions():
    owner = EntityDisambiguator()
    owner.prepare([scoped('a', 'Acme', 'Acme manufactures engines.', description='manufactures engines'),
                   scoped('b', 'Acme', 'Acme publishes newspapers.', description='publishes newspapers')])
    rows = [scoped('c', 'Acme', 'Acme reports.'), scoped('d', 'Acme', 'Acme reports.')]
    owner.prepare(rows)
    assert owner.compare(*rows)['decision'] == 'same'
