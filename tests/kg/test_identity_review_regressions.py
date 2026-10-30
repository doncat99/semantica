"""Reviewed semantic counterexamples through located source -> native resolver."""
from types import SimpleNamespace

import pytest

from semantica.semantic_artifact_builder import _build_source, _resolve_native_entities


def mention(name, context, scope='a', *, description=None, owner=None, kind=None, instance=None, type='ORG'):
    return dict(name=name, context=context, scope=scope, description=description,
                owner=owner, kind=kind, instance=instance, type=type)


def project(rows):
    mentions = []
    for scope in dict.fromkeys(row['scope'] for row in rows):
        source_rows = [row for row in rows if row['scope'] == scope]
        text = '\n'.join(row['context'] for row in source_rows)
        extracted, begin = [], 0
        for index, row in enumerate(source_rows):
            start = begin + row['context'].index(row['name'])
            item = dict(id=f'{scope}:{index}', name=row['name'], type=row['type'],
                        attributes={}, _start=start, _end=start + len(row['name']))
            if any(row[key] is not None for key in ('description', 'owner', 'kind', 'instance')):
                item['identity_profile'] = dict(description=row['description'], owner=row['owner'],
                    referent_kind=row['kind'], instance=row['instance'], evidence=row['context'], evidence_occurrence=0,
                    evidence_start=begin, evidence_end=begin + len(row['context']))
            extracted.append(item)
            begin += len(row['context']) + 1
        source = SimpleNamespace(source_id='source:' + scope, name=scope, mime_type='text/plain',
                                 material_revision='b3-' + '1' * 64)
        built = _build_source(source, False, dict(entities=extracted, relations=[]),
                             (text, dict(text=text), 'native', 'b3-' + '1' * 64, 'text', '1'))
        mentions.extend(built['entities'])
    before = [item.model_dump() for item in mentions]
    result = _resolve_native_entities(mentions)
    assert before == [item.model_dump() for item in mentions]
    assert len(result[2]) == len(rows)
    return result


CASES = [
    ('generic_body_at_sentence_end_is_not_owner', 2, [mention('Board',
        'Ultimate oversight rests with our Board of Directors.', scope) for scope in ('a', 'b')]),
    ('generic_body_is_not_its_owner', 2, [mention('Board', 'Our Board of Directors oversees operations.', 'a'),
        mention('Board', 'Our Board of Directors oversees operations.', 'b')]),
    ('expanded_generic_body_stays_owner_scoped', 2, [mention('Board',
        'Our Board of Directors (Board) oversees operations.', scope) for scope in ('a', 'b')]),
    ('context_homonyms', 2, [mention('Mercury', 'Mercury manufactures marine engines.'),
        mention('Mercury', 'Mercury publishes a daily newspaper.', 'b')]),
    ('subsidiary_boards', 2, [mention('Board', 'The Board of Acme oversees manufacturing.'),
        mention('Board', 'The Board of Beta, our subsidiary, oversees banking.')]),
    ('defining_owner', 1, [mention('Audit Committee', 'Acme Audit Committee oversees financial reporting.',
        description='Acme financial oversight committee.', owner='Acme', kind='dependent_entity'),
        mention('Audit Committee', 'The Audit Committee met four times this year.')]),
    ('description_paraphrases', 1, [mention('Acme', 'Acme manufactures engines.', description='An engine manufacturer.'),
        mention('Acme', 'Acme is a manufacturer of engines.', 'b', description='A manufacturer of engines.')]),
    ('report_versions', 2, [mention('Annual Report', f'Acme Annual Report covers fiscal year {year}.', str(year),
        description=f'The {year} annual report.', owner='Acme', kind='report') for year in (2023, 2024)]),
    ('unowned_reports', 2, [mention('Sustainability Report', f'{owner} published its Sustainability Report.', owner,
        description='A sustainability report.', kind='report') for owner in ('Acme', 'Beta')]),
    ('broad_kind_noise', 1, [mention('TCFD', 'TCFD issued climate-related disclosure recommendations.', scope,
        description='Issuer of climate-related disclosure recommendations.', kind=kind)
        for scope, kind in [('a', 'named_entity'), ('b', 'framework')]]),
    ('acronym_hijack', 2, [mention('American Broadcasting Company',
        'American Broadcasting Company (ABC) broadcasts television.'),
        mention('ABC', 'ABC manufactures industrial bearings in Germany.', 'b')]),
    ('irregular_acronym', 1, [mention('International Organization for Standardization',
        'International Organization for Standardization (ISO) publishes standards.'),
        mention('ISO', 'ISO publishes international standards.', 'b')]),
    ('person_local_role', 1, [mention('Jane Smith', 'Jane Smith is Acme chief financial officer.', type='PERSON'),
        mention('Jane Smith', 'Jane Smith, our chief financial officer, signed this report.', type='PERSON')]),
    ('article_variant', 1, [mention(name, f'{name} operates home improvement stores.', scope)
        for name, scope in [('Home Depot', 'a'), ('The Home Depot', 'b')]]),
    ('owner_alias', 1, [mention('Audit Committee', 'Acme Inc. (Acme) Audit Committee oversees financial reporting.',
        description='Financial oversight committee.', owner='Acme Inc.', kind='dependent_entity'),
        mention('Audit Committee', 'Acme Inc. (Acme) Audit Committee oversees financial reporting.', 'b',
        description='Financial oversight committee.', owner='Acme', kind='dependent_entity')]),
]


@pytest.mark.parametrize('label,expected,rows', CASES, ids=[case[0] for case in CASES])
def test_reviewed_source_chain(label, expected, rows):
    for order in (rows, rows[::-1]):
        entities, _, _ = project(order)
        assert len(entities) == expected


@pytest.mark.parametrize('name', ['Supplier Code of Conduct', 'Human Rights Policy',
    'Compensation and Human Capital Committee', 'Vendor Code of Conduct', 'Sustainability Report'])
def test_real_corpus_owned_objects_do_not_cross_merge(name):
    rows = [mention(name, f'Our {name} sets expectations.', scope) for scope in ('dycom', 'wmg')]
    assert len(project(rows)[0]) == 2


@pytest.mark.parametrize('name,expanded', [
    ('Council', 'Council of Navigators'),
    ('Team', 'Team of Inventors'),
    ('Department', 'Department of Safety'),
])
def test_of_name_complement_is_not_owner_or_global_identity(name, expanded):
    for title in (expanded, f'{expanded} ({name.upper()})'):
        rows = [mention(name, f'Our {title} meets.', scope) for scope in ('a', 'b')]
        assert len(project(rows)[0]) == 2
    rows = [mention(expanded, f'Our {expanded} ({name.upper()}) meets.', scope)
            for scope in ('a', 'b')]
    assert len(project(rows)[0]) == 2


def test_title_adjacency_alone_does_not_establish_owner():
    rows = [mention('Policy', 'Global Policy applies.', scope) for scope in ('a', 'b')]
    assert len(project(rows)[0]) == 2


@pytest.mark.parametrize('apostrophe', ["'", '’'])
def test_possessive_owner_reuse_remains_available(apostrophe):
    rows = [mention('Council', f'Zorblax{apostrophe}s Council meets.', scope)
            for scope in ('a', 'b')]
    rows.append(mention('Council', f'Nebulon{apostrophe}s Council meets.', 'c'))
    assert len(project(rows)[0]) == 2


def test_grounded_owner_does_not_need_possessive_syntax_or_description():
    rows = [mention('Council', 'Council of Zorblax meets.', scope,
                    owner='Zorblax', kind='dependent_entity') for scope in ('a', 'b')]
    assert len(project(rows)[0]) == 1


def test_of_phrase_in_independent_institution_name_is_not_an_owner_requirement():
    name = 'Institute of Navigation'
    rows = [mention(name, f'{name} (ION) issued guidance.', scope) for scope in ('a', 'b')]
    assert len(project(rows)[0]) == 1


def test_ambiguous_local_owners_do_not_inherit_arbitrary_definition():
    rows = [mention('Audit Committee', f'{owner} Audit Committee meets.', owner=owner,
                    kind='dependent_entity') for owner in ('Acme', 'Beta')]
    rows.append(mention('Audit Committee', 'The Audit Committee meets.'))
    assert len(project(rows)[0]) == 3


def test_same_owner_does_not_override_description_contradiction():
    rows = [mention('Team', text, scope, description=description, owner='Acme', kind='dependent_entity')
        for scope, text, description in [('a', 'Acme Team manufactures engines.', 'Engine manufacturer.'),
                                        ('b', 'Acme Team publishes newspapers.', 'Newspaper publisher.')]]
    assert len(project(rows)[0]) == 2


def test_negation_is_not_description_compatibility():
    rows = [mention('Acme', 'Acme is a manufacturer.', description='A manufacturer.'),
        mention('Acme', 'Acme is not a manufacturer.', 'b', description='Not a manufacturer.')]
    assert len(project(rows)[0]) == 2


def test_quoted_abbreviation_and_non_initialism_alias_are_grounded():
    rows = [mention('Sustainability Accounting Standards Board',
        'Sustainability Accounting Standards Board ("SASB") publishes standards.'),
        mention('SASB', 'SASB publishes standards.')]
    assert len(project(rows)[0]) == 1


def test_unique_local_board_definition_reuses_repeated_acronym():
    rows = [mention('Sustainability Accounting Standards Board',
        'Sustainability Accounting Standards Board ("SASB") publishes standards.'),
        mention('SASB', 'We apply SASB standards.'),
        mention('SASB', 'Our report references SASB standards.')]
    for order in (rows, rows[::-1]):
        assert len(project(order)[0]) == 1


def test_source_local_definition_wins_over_competing_project_expansions():
    rows = [
        mention('SASB', 'Sustainability Accounting Standards Board (SASB) sets standards.', 'a'),
        mention('SASB', '| SASB | Topic | Metric |', 'a'),
        mention('SASB', 'Social Accountability Standards Board (SASB) publishes standards.', 'b'),
    ]
    # The table mention is in the same material as a uniquely grounded
    # expansion. A competing expansion in another material must not split it.
    assert len(project(rows)[0]) == 2


def test_local_definition_does_not_require_a_separate_full_name_mention():
    rows = [mention('SASB', 'We follow Sustainability Accounting Standards Board (SASB) standards.'),
        mention('SASB', 'Our report references SASB standards.'),
        mention('SASB', '| Context | SASB |'),
        mention('Social Accountability Standards Board',
            'Social Accountability Standards Board (SASB) publishes standards.', 'b'),
        mention('Sustainable Accounting Standards Board',
            'Sustainable Accounting Standards Board (SASB) publishes standards.', 'c')]
    for order in (rows, rows[::-1]):
        _, remap, registry = project(order)
        local = [row.entity_id for row in registry if row.source_ids == ['source:a']]
        assert len(set(local)) == 1


def test_article_before_expansion_does_not_create_competing_acronym_identity():
    rows = [mention('SASB', 'The Sustainability Accounting Standards Board (SASB) sets standards.'),
            mention('Sustainability Accounting Standards Board',
                    'Sustainability Accounting Standards Board (SASB) sets standards.'),
            mention('SASB', 'We reference SASB standards.')]
    assert len(project(rows)[0]) == 1


def test_extracted_article_prefixed_full_name_uses_the_same_acronym_definition():
    text = 'The Sustainability Accounting Standards Board (SASB) sets standards.'
    rows = [mention('The Sustainability Accounting Standards Board', text),
            mention('SASB', text), mention('SASB', 'We reference SASB standards.')]
    for order in (rows, rows[::-1]):
        assert len(project(order)[0]) == 1


def test_extracted_suffix_does_not_create_another_acronym_expansion():
    text = 'Sustainability Accounting Standards Board (SASB) sets standards.'
    rows = [mention('Sustainability Accounting Standards Board', text),
            mention('Standards Board', text), mention('SASB', text),
            mention('SASB', 'We reference SASB standards.')]
    for order in (rows, rows[::-1]):
        _, _, registry = project(order)
        named = [row.entity_id for row in registry if row.canonical_name != 'Standards Board']
        assert len(set(named)) == 1


def test_remote_short_expansion_cannot_shadow_a_long_local_definition():
    rows = [mention('SASB', 'Sustainability Accounting Standards Board (SASB) sets standards.'),
            mention('SASB', 'We reference SASB standards.'),
            mention('SASB', '| Standards Board (SASB) Index .', 'b')]
    for order in (rows, rows[::-1]):
        _, _, registry = project(order)
        local = [row.entity_id for row in registry if row.source_ids == ['source:a']]
        assert len(set(local)) == 1
        assert len({row.entity_id for row in registry}) == 2


def test_grounded_inflection_variant_of_acronym_definition_is_reused():
    rows = [mention('Sustainability Accounting Standards Board',
                    'Sustainability Accounting Standards Board (SASB) sets standards.'),
            mention('Sustainable Accounting Standards Board',
                    'Sustainable Accounting Standards Board (SASB) publishes standards.', 'b'),
            mention('SASB', 'We reference SASB standards.', 'c')]
    assert len(project(rows)[0]) == 1


def test_different_acronym_expansion_remains_unresolved():
    rows = [mention('Sustainability Accounting Standards Board',
                    'Sustainability Accounting Standards Board (SASB) sets standards.'),
            mention('Social Accountability Standards Board',
                    'Social Accountability Standards Board (SASB) publishes standards.', 'b')]
    assert len(project(rows)[0]) == 2


def test_repeated_grounded_full_name_is_not_split_by_competing_acronym_expansions():
    rows = [
        mention('Sustainability Accounting Standards Board',
                'Sustainability Accounting Standards Board (SASB) sets standards.', 'a'),
        mention('Sustainability Accounting Standards Board',
                'The Sustainability Accounting Standards Board publishes standards.', 'b'),
        mention('Social Accountability Standards Board',
                'Social Accountability Standards Board (SASB) publishes standards.', 'c'),
    ]
    entities, _, registry = project(rows)
    grounded = [row.entity_id for row in registry if row.source_ids != ['source:c']]
    assert len(set(grounded)) == 1
    assert len(entities) == 2


def test_repeated_full_name_survives_unrelated_context_sentences():
    rows = [
        mention('Sustainability Accounting Standards Board',
                'Sustainability Accounting Standards Board (SASB) sets standards.', 'a'),
        mention('Sustainability Accounting Standards Board',
                'The Sustainability Accounting Standards Board publishes investor metrics.', 'b'),
    ]
    assert len(project(rows)[0]) == 1


def test_repeated_full_name_does_not_override_conflicting_entity_descriptions():
    rows = [
        mention('Mercury Corporation', 'Mercury Corporation manufactures engines.', 'a',
                description='Manufacturer of marine engines.'),
        mention('Mercury Corporation', 'Mercury Corporation publishes newspapers.', 'b',
                description='Publisher of daily newspapers.'),
    ]
    assert len(project(rows)[0]) == 2


def test_grounded_acronym_reuses_definition_across_representations_of_one_source():
    """A material may have several representations, but remains one source."""
    from semantica.normalize.entity_normalizer import EntityDisambiguator

    rows = [
        dict(id='full', name='SASB', type='ORG', context=(
            'Sustainability Accounting Standards Board (SASB) sets standards.'),
            metadata={'identity_scope': 'representation:full', 'source_ids': ['source:report']}),
        dict(id='short', name='SASB', type='ORG', context='SASB INDEX lists disclosures.',
            metadata={'identity_scope': 'representation:index', 'source_ids': ['source:report']}),
    ]
    resolver = EntityDisambiguator()
    resolver.prepare(rows)
    assert resolver.compare(rows[0], rows[1])['decision'] == 'same'


def test_grounded_acronym_does_not_cross_bind_another_source():
    from semantica.normalize.entity_normalizer import EntityDisambiguator

    rows = [
        dict(id='full', name='SASB', type='ORG', context=(
            'Sustainability Accounting Standards Board (SASB) sets standards.'),
            metadata={'identity_scope': 'representation:full', 'source_ids': ['source:one']}),
        dict(id='short', name='SASB', type='ORG', context='SASB INDEX lists disclosures.',
            metadata={'identity_scope': 'representation:index', 'source_ids': ['source:two']}),
    ]
    resolver = EntityDisambiguator()
    resolver.prepare(rows)
    assert resolver.compare(rows[0], rows[1])['decision'] != 'same'


def test_unrelated_parenthetical_ticker_is_not_an_alias():
    text = 'Signet shares trade on New York Stock Exchange (SIG).'
    assert len(project([mention('New York Stock Exchange', text), mention('SIG', text)])[0]) == 2


def test_owner_without_description_survives_grounded_contract():
    entities, _, _ = project([mention('Audit Committee', 'Acme Audit Committee meets.',
        owner='Acme', kind='dependent_entity')])
    assert entities[0].metadata['identity_profile']['owner'] == 'Acme'


def test_unresolved_candidate_reason_is_persisted():
    _, _, registry = project([mention('Mercury', 'Mercury manufactures engines.'),
                              mention('Mercury', 'Mercury publishes newspapers.', 'b')])
    assert all(row.unresolved_candidates for row in registry)
    assert all(row.unresolved_candidates[0].reason for row in registry)


def test_other_owner_description_does_not_poison_local_reuse():
    rows = [mention('Team', 'Acme Team is an engine manufacturer.', owner='Acme',
                    kind='dependent_entity', description='An engine manufacturer.'),
            mention('Team', 'Acme Team meets.', owner='Acme', kind='dependent_entity'),
            mention('Team', 'Beta Team is a newspaper publisher.', 'b', owner='Beta',
                    kind='dependent_entity', description='A newspaper publisher.')]
    assert len(project(rows)[0]) == 2


def test_matching_profiles_do_not_override_explicit_source_contradiction():
    rows = [mention('Mercury', f'Mercury is a {domain}.', str(index),
                    description='A company.') for index, domain in
            enumerate(['marine engine manufacturer', 'daily newspaper publisher'])]
    assert len(project(rows)[0]) == 2


def test_same_person_role_at_different_companies_does_not_merge():
    rows = [mention('Jane Smith', f'Jane Smith is {owner} chief financial officer.',
                    type='PERSON') for owner in ['Acme', 'Beta']]
    assert len(project(rows)[0]) == 2


def test_versionless_report_cannot_bridge_instances_in_one_source():
    rows = [mention('Annual Report', f'Acme Annual Report covers fiscal year {year}.',
                    owner='Acme', kind='report', instance=f'fiscal year {year}') for year in [2023, 2024]]
    rows.append(mention('Annual Report', 'Acme Annual Report is available.', owner='Acme', kind='report'))
    assert len(project(rows)[0]) == 3


def test_instance_year_agrees_with_explicit_fiscal_year():
    rows = [mention('Annual Report', 'Acme Annual Report covers fiscal year 2023.',
                    owner='Acme', kind='report', instance='fiscal year 2023'),
            mention('Annual Report', 'Acme Annual Report covers fiscal year 2023.', 'b',
                    owner='Acme', kind='report')]
    assert len(project(rows)[0]) == 1


def test_unbound_owner_alias_in_other_source_does_not_hijack_owner():
    rows = [mention('Team', 'Acme Inc. (Acme) Team meets.', owner='Acme Inc.', kind='dependent_entity'),
            mention('Team', 'Acme Team meets.', 'b', owner='Acme', kind='dependent_entity')]
    assert len(project(rows)[0]) == 2


def test_owner_only_profile_survives_merge():
    rows = [mention('Audit Committee', 'Acme Audit Committee meets.', owner='Acme', kind='dependent_entity'),
            mention('Audit Committee', 'The Audit Committee met four times this year.')]
    for order in (rows, rows[::-1]):
        entities, _, _ = project(order)
        assert len(entities) == 1
        assert entities[0].metadata['identity_profile']['owner'] == 'Acme'


@pytest.mark.parametrize('name', ['American Broadcasting Company', 'IFRS Foundation'])
def test_full_organization_name_is_not_an_unowned_generic_body(name):
    rows = [mention(name, f'{name} issued a statement.', scope) for scope in ['a', 'b']]
    assert len(project(rows)[0]) == 1


def test_grounded_institution_kind_is_not_a_company_owned_board():
    rows = [mention('Sustainability Accounting Standards Board',
        'Sustainability Accounting Standards Board is a standard-setting institution.', scope,
        description='A standard-setting institution.', kind='institution') for scope in ['a', 'b']]
    assert len(project(rows)[0]) == 1


def test_person_role_alone_does_not_override_known_owners():
    rows = [mention('Jane Smith', f'Jane Smith is {owner} chief financial officer.',
                    owner=owner, type='PERSON') for owner in ['Acme', 'Beta']]
    assert len(project(rows)[0]) == 2


def test_workplace_commitments_are_not_conflicting_entity_definitions():
    rows = [mention('The Home Depot', 'The Home Depot is a place where associates feel empowered.'),
            mention('Home Depot', 'The Home Depot is committed to conserving water.'),
            mention('Home Depot', 'More than 800 Home Depot stores participated.')]
    assert len(project(rows)[0]) == 1


def test_unresolved_samples_are_bounded_and_reset_between_resolutions():
    from semantica.kg.entity_resolver import EntityResolver
    resolver = EntityResolver(strategy='contextual')
    rows = [dict(id=str(index), name='Board', type='ORG', context='The Board meets.',
                 metadata={'identity_scope': str(index)}) for index in range(12)]
    resolver.resolve_entities(rows)
    assert resolver.duplicate_detector.identity_reviews
    resolver.resolve_entities([dict(id='single', name='Solo', type='ORG', context='Solo works.')])
    assert not resolver.duplicate_detector.identity_reviews
    resolver.resolve_entities(rows)
    resolver.resolve_entities([])
    assert not resolver.duplicate_detector.identity_reviews
    _, _, registry = project([mention('Board', 'The Board meets.', str(index)) for index in range(12)])
    assert all(entry.unresolved_candidate_count == 11 and len(entry.unresolved_candidates) == 8 for entry in registry)


@pytest.mark.parametrize('change', [dict(unresolved_candidate_count=0),
    dict(unresolved_candidates=[dict(entity_id='entity:canonical', reason='ambiguous')]),
    dict(unresolved_candidates=[dict(entity_id='entity:other', reason='')])])
def test_invalid_unresolved_registry_result_is_rejected(change):
    from pydantic import ValidationError
    from semantica.semantic_artifact_schema import IdentityRegistryEntry
    data = dict(mention_id='mention:m', entity_id='entity:canonical', canonical_name='Board', type='ORG',
                unresolved_candidate_count=1,
                unresolved_candidates=[dict(entity_id='entity:other', reason='unresolved_owner')])
    IdentityRegistryEntry.model_validate(data)
    with pytest.raises(ValidationError):
        IdentityRegistryEntry.model_validate({**data, **change})


def test_complementary_descriptions_do_not_require_more_evidence():
    rows = [mention('Acme', 'Acme manufactures industrial equipment.',
                    description='An industrial equipment manufacturer.'),
            mention('Acme', 'Acme has its headquarters in London.', 'b',
                    description='Headquartered in London.'),
            mention('Acme', 'Acme released its results.', 'c')]
    for order in (rows, rows[::-1]):
        assert len(project(order)[0]) == 1


def test_other_source_homonym_does_not_split_local_named_mentions():
    rows = [mention('Mercury', 'Mercury manufactures engines.'),
            mention('Mercury', 'Mercury released its results.'),
            mention('Mercury', 'Mercury publishes newspapers.', 'b')]
    for order in (rows, rows[::-1]):
        _, _, registry = project(order)
        local = [row.entity_id for row in registry if row.source_ids == ['source:a']]
        remote = [row.entity_id for row in registry if row.source_ids == ['source:b']]
        assert len(set(local)) == 1
        assert remote[0] != local[0]


def test_indirect_conflict_preserves_compatible_subgroups():
    from itertools import permutations
    from semantica.deduplication.duplicate_detector import DuplicateDetector, DuplicateCandidate

    rows = {key: dict(id=key, name='Example Organization') for key in 'abcd'}
    decisions = {('a', 'b'): 'same', ('b', 'c'): 'same', ('c', 'd'): 'same',
                 ('a', 'd'): 'different'}
    detector = DuplicateDetector(contextual_identity=True)

    def compare(left, right, score):
        decision = decisions.get(tuple(sorted((left['id'], right['id']))), 'unknown')
        return DuplicateCandidate(left, right, score, 1.,
            metadata=dict(decision=decision, merge_allowed=decision == 'same'))

    detector._create_duplicate_candidate = compare
    edges = [compare(rows[a], rows[b], 1.) for a, b in [('a', 'b'), ('b', 'c'), ('c', 'd')]]
    for order in permutations(edges):
        groups = detector._build_duplicate_groups(list(order))
        assert {frozenset(row['id'] for row in group.entities) for group in groups} == {
            frozenset('ab'), frozenset('cd')}


def test_compact_reviews_preserve_exact_post_merge_counts_without_pair_tuples():
    from semantica.kg.entity_resolver import EntityResolver

    rows = [dict(id=str(i), name='Board', type='ORG', context='The Board meets.',
                 metadata={'identity_scope': str(i)}) for i in range(128)]
    resolver = EntityResolver(strategy='contextual')
    resolver.resolve_entities(rows)
    detector = resolver.duplicate_detector
    assert len(detector.identity_reviews) == len(rows)
    assert all(len(reasons) == 1 and next(iter(reasons.values())).bit_count() == 127
               for reasons in detector.identity_reviews.values())
    # Multiple unknown mentions may later resolve to one canonical candidate.
    remap = {str(i): f'entity:{i // 2}' for i in range(128)}
    summaries = list(detector.iter_identity_review_summaries(remap))
    assert len(summaries) == 128
    assert all(count == 63 and len(sample) == 8 for _, count, sample in summaries)
    assert all(remap[mention_id] not in {candidate_id for candidate_id, _ in sample}
               for mention_id, _, sample in summaries)
