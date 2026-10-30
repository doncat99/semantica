from semantica.kg.entity_resolver import EntityResolver


def mention(key, name, context="", description="", **properties):
    return dict(id=key, name=name, type="ORG", context=context,
                description=description, properties=properties)


def resolve(*rows, **config):
    return EntityResolver(strategy="contextual", **config).resolve_entities(list(rows))


def test_same_name_is_not_identity_without_grounded_support():
    assert len(resolve(mention("a", "Mercury"), mention("b", "Mercury"))) == 2
    assert len(resolve(mention("a", "Mercury", "Mercury manufactures engines."),
                       mention("b", "Mercury", "Mercury publishes newspapers."))) == 2


def test_grounded_definition_links_full_name_and_abbreviation():
    context = "International Business Machines (IBM) manufactures computers."
    assert len(resolve(mention("a", "International Business Machines", context),
                       mention("b", "IBM", context))) == 1


def test_abbreviation_alone_does_not_prove_identity():
    assert len(resolve(mention("a", "International Business Machines"),
                       mention("b", "IBM"))) == 2


def test_generic_description_does_not_prove_identity_across_unscoped_mentions():
    context = "Acme is a manufacturer of precision medical instruments."
    description = "manufacturer of precision medical instruments"
    assert len(resolve(mention("a", "Acme", context, description),
                       mention("b", "Acme", context, description))) == 2
    assert len(resolve(mention("a", "Acme", context, description),
                       mention("b", "Other", "Other is a " + description, description))) == 2


def test_trusted_identifier_conflict_vetoes_context():
    config = {"deduplication": {"similarity": {"property_schema": {"lei": {"identity": True}}}}}
    context = "Acme manufactures engines."
    assert len(resolve(mention("a", "Acme", context, lei="1"),
                       mention("b", "Acme", context, lei="2"), **config)) == 2


def test_identity_match_recalls_different_names():
    config = {"deduplication": {"similarity": {"property_schema": {"lei": {"identity": True}}}}}
    assert len(resolve(mention("a", "Old Name", lei="1"),
                       mention("b", "New Name", lei="1"), **config)) == 1


def test_context_bridge_cannot_join_incompatible_group():
    a = "Alpha Holdings (AH) operates hospitals."
    b = "Another Holding (AH) operates mines."
    rows = [mention("a", "Alpha Holdings", a), mention("bridge", "AH", a + " " + b),
            mention("b", "Another Holding", b)]
    groups = resolve(*rows)
    assert all(set(row.get("merged_from", [])) != {"a", "bridge", "b"} for row in groups)
    assert sum(len(row.get("merged_from") or [row["id"]]) for row in groups) == 3


def test_identical_context_is_not_identity_for_distinct_homonyms():
    context = "Mercury in London acquired Mercury in New York."
    assert len(resolve(mention("a", "Mercury", context),
                       mention("b", "Mercury", context))) == 2


def test_repeated_located_occurrence_can_merge_without_description():
    rows = [mention(key, "Mercury", "Mercury manufactures marine engines.")
            for key in ("a", "b")]
    for row in rows:
        row["evidence_ids"] = ["evidence:same-mention"]
    assert len(resolve(*rows)) == 1


def test_shared_context_span_does_not_identify_distinct_occurrences():
    rows = [mention(key, "Mercury", "Mercury in London acquired Mercury in New York.")
            for key in ("a", "b")]
    for row in rows:
        row["evidence_ids"] = ["evidence:context", "evidence:" + row["id"]]
        row["metadata"] = {"identity_context_evidence_id": "evidence:context"}
    assert len(resolve(*rows)) == 2


def test_shared_description_support_is_not_the_same_located_occurrence():
    rows = [mention(key, 'Mercury', 'Mercury in London acquired Mercury in New York.')
            for key in ('a', 'b')]
    for row in rows:
        row['evidence_ids'] = ['evidence:description', 'evidence:' + row['id']]
        row['metadata'] = {'description_evidence_ids': ['evidence:description']}
    assert len(resolve(*rows)) == 2


def test_legacy_confidence_does_not_invent_identity_evidence():
    from semantica.normalize.entity_normalizer import EntityDisambiguator
    assert EntityDisambiguator().calculate_confidence(["Mercury", "Acme"]) == {
        "Mercury": 0.0, "Acme": 0.0}


def test_shared_description_cannot_bind_two_homonyms_in_one_context():
    context = "Mercury in London acquired Mercury in New York, both manufacturers of marine engines."
    description = "manufacturers of marine engines"
    assert len(resolve(mention("a", "Mercury", context, description),
                       mention("b", "Mercury", context, description))) == 2


def test_context_must_contain_the_actual_name_not_a_substring():
    context = "Using the database improves operational reporting across organizations."
    description = "improves operational reporting across organizations"
    assert len(resolve(mention("a", "US", context, description),
                       mention("b", "US", context, description))) == 2


def scoped(key, name, context, scope="document:1", description=""):
    row = mention(key, name, context, description)
    row["metadata"] = {"identity_scope": scope}
    row["evidence_ids"] = ["evidence:" + key]
    return row


def test_scoped_same_name_reuses_identity_without_repeating_description():
    rows = [scoped("a", "Home Depot", "Home Depot reports emissions."),
            scoped("b", "Home Depot", "Home Depot publishes annual results.")]
    assert len(resolve(*rows)) == 1
    assert len(resolve(rows[0], {**rows[1], "metadata": {"identity_scope": "document:2"}})) == 1


def test_repeated_name_in_a_sentence_is_not_itself_evidence_of_ambiguity():
    context = "Home Depot reports Home Depot emissions."
    assert len(resolve(scoped("a", "Home Depot", context), scoped("b", "Home Depot", context))) == 1


def test_definition_is_reused_throughout_its_scope_without_initialism_guessing():
    full = "Task Force on Climate-related Financial Disclosures"
    rows = [scoped("full", full, full + " (TCFD) provides recommendations."),
            scoped("a", "TCFD", "TCFD recommends disclosure."),
            scoped("b", "TCFD", "We follow TCFD guidelines.")]
    assert len(resolve(*rows)) == 1
    # A remote unqualified acronym is a candidate, not a source definition.
    assert len(resolve(*rows, scoped("other", "TCFD", "TCFD reports progress.", "document:2"))) == 2


def test_competing_definitions_do_not_merge_unqualified_acronym():
    rows = [scoped("a", "Alpha Holdings", "Alpha Holdings (AH) operates hospitals."),
            scoped("b", "Another Holding", "Another Holding (AH) operates mines."),
            scoped("c", "AH", "AH reports results."),
            scoped("d", "AH", "AH publishes accounts.")]
    assert len(resolve(*rows)) == 4


def test_scoped_conflicting_identifiers_cannot_be_bridged_by_missing_information():
    rows = [scoped(key, "Acme", "Acme reports results.") for key in ("a", "b", "c")]
    rows[0]["properties"] = {"lei": "one"}
    rows[2]["properties"] = {"lei": "two"}
    assert len(resolve(*rows, deduplication={"similarity": {"property_schema": {
        "lei": {"identity": True}}}})) == 3


def test_scope_does_not_turn_common_person_names_into_identity():
    for name, kind in [("John Smith", "PERSON")]:
        rows = [scoped(key, name, name + " appears in this report.") for key in ("a", "b")]
        for row in rows:
            row["type"] = kind
        assert len(resolve(*rows)) == 2


def test_grounded_description_survives_first_member_without_description():
    description = "manufacturer of precision medical instruments"
    rows = [scoped("a", "Acme", "Acme reports results."),
            scoped("b", "Acme", "Acme is a " + description + ".", description=description)]
    merged, = resolve(*rows, merger={"strategy": {"default_strategy": "keep_first"}})
    assert merged["description"] == description
    assert description in merged["context"]
    assert merged["metadata"]["description_mention_id"] == "b"
    assert merged["metadata"]["description_evidence_ids"] == ["evidence:b"]


def test_reusing_resolver_does_not_leak_definition_between_runs():
    resolver = EntityResolver(strategy="contextual")
    resolver.resolve_entities([scoped("a", "Alpha Holdings", "Alpha Holdings (AH) operates hospitals.")])
    rows = [scoped("b", "AH", "AH reports results."),
            scoped("c", "Alpha Holdings", "Alpha Holdings reports results.")]
    assert len(resolver.resolve_entities(rows)) == 2


def test_grounded_definition_reuse_tolerates_extracted_type_noise():
    full = "Task Force on Climate-related Financial Disclosures"
    rows = [scoped("full", full, full + " (TCFD) issues recommendations."),
            scoped("short", "TCFD", full + " (TCFD) guides disclosure.", "document:2")]
    rows[1]["type"] = "CONCEPT"
    assert len(resolve(*rows)) == 1


def test_definition_formatting_is_not_competing_identity():
    rows = [scoped("a", "Alpha Holdings", "Alpha Holdings (AH) reports."),
            scoped("b", "Alpha\n\nHoldings", "Alpha\n\nHoldings (AH) reports.", "document:2"),
            scoped("c", "AH", "Alpha Holdings (AH) publishes results.", "document:3")]
    assert len(resolve(*rows)) == 1


def test_cross_document_competing_acronyms_keep_unqualified_mentions_separate():
    rows = [scoped("a", "Alpha Holdings", "Alpha Holdings (AH) operates hospitals."),
            scoped("b", "Another Holding", "Another Holding (AH) operates mines.", "document:2"),
            scoped("c", "AH", "AH reports.", "document:3"),
            scoped("d", "AH", "AH publishes.", "document:4")]
    assert len(resolve(*rows)) == 4


def test_incompatible_named_types_remain_distinct_across_documents():
    rows = [scoped("a", "Jordan", "Jordan reports results."),
            scoped("b", "Jordan", "Jordan reports results.", "document:2")]
    rows[0]["type"], rows[1]["type"] = "PERSON", "GPE"
    assert len(resolve(*rows)) == 2


def test_local_definition_wins_over_competing_document_and_project_definitions():
    rows = [scoped("a", "Alpha Holdings", "Alpha Holdings (AH) operates hospitals."),
            scoped("a-short", "AH", "Alpha Holdings (AH) operates hospitals."),
            scoped("b", "Another Holding", "Another Holding (AH) operates mines."),
            scoped("b-short", "AH", "Another Holding (AH) operates mines."),
            scoped("unqualified", "AH", "AH publishes results.", "document:2")]
    groups = resolve(*rows)
    memberships = {frozenset(row.get("merged_from") or [row["id"]]) for row in groups}
    assert memberships == {frozenset({"a", "a-short"}), frozenset({"b", "b-short"}),
                           frozenset({"unqualified"})}


def test_local_definition_does_not_bind_an_acronym_with_two_local_expansions():
    context = "Alpha Holdings (AH) acquired Another Holding (AH)."
    rows = [scoped("a", "Alpha Holdings", context), scoped("short", "AH", context),
            scoped("b", "Another Holding", context)]
    assert len(resolve(*rows)) == 3


def test_located_occurrence_wins_over_remote_definition_ambiguity():
    rows = [scoped("a", "Alpha Holdings", "Alpha Holdings (AH) reports."),
            scoped("b", "Another Holding", "Another Holding (AH) reports."),
            scoped("c", "AH", "AH reports results.", "document:2"),
            scoped("d", "AH", "AH reports results.", "document:2")]
    rows[2]["evidence_ids"] = rows[3]["evidence_ids"] = ["evidence:located-short"]
    groups = resolve(*rows)
    assert {frozenset(row.get("merged_from") or [row["id"]]) for row in groups} == {
        frozenset({"a"}), frozenset({"b"}), frozenset({"c", "d"})}


def test_identifier_conflict_still_vetoes_explicit_local_definition():
    context = "Alpha Holdings (AH) reports results."
    rows = [scoped("a", "Alpha Holdings", context), scoped("short", "AH", context)]
    rows[0]["properties"], rows[1]["properties"] = {"lei": "one"}, {"lei": "two"}
    assert len(resolve(*rows, deduplication={"similarity": {"property_schema": {
        "lei": {"identity": True}}}})) == 2


def test_local_definition_uses_the_mentions_own_context_window():
    rows = [scoped("a", "Alpha Holdings", "We support Alpha Holdings (AH) and its partners."),
            scoped("a-short", "AH", "Alpha Holdings (AH) and its partners."),
            scoped("b", "Another Holding", "Another Holding (AH) reports results.")]
    groups = resolve(*rows)
    assert {frozenset(row.get("merged_from") or [row["id"]]) for row in groups} == {
        frozenset({"a", "a-short"}), frozenset({"b"})}


def test_local_binding_can_override_a_different_document_definition():
    rows = [scoped("a", "Alpha Holdings", "Alpha Holdings (AH) reports."),
            scoped("b", "Another Holding", "Another Holding (AH) reports.", "document:2"),
            scoped("b-short", "AH", "Another Holding (AH) reports.")]
    assert {frozenset(row.get("merged_from") or [row["id"]]) for row in resolve(*rows)} == {
        frozenset({"a"}), frozenset({"b", "b-short"})}


def test_one_definition_does_not_locate_another_acronym_occurrence():
    context = "Alpha Holdings (AH) acquired AH."
    rows = [scoped("a", "Alpha Holdings", context), scoped("short", "AH", context),
            scoped("b", "Another Holding", "Another Holding (AH) reports.")]
    assert len(resolve(*rows)) == 3


def test_local_explicit_tcfd_binding_does_not_require_initialism_guessing():
    full = "Task Force on Climate-related Financial Disclosures"
    alternative = "Task Force for Climate-related Financial Disclosures"
    rows = [scoped("full", full, full + " (TCFD) issues recommendations."),
            scoped("short", "TCFD", full.upper() + " (TCFD) issues recommendations."),
            scoped("other", alternative, alternative + " (TCFD) is cited.")]
    assert {frozenset(row.get("merged_from") or [row["id"]]) for row in resolve(*rows)} == {
        frozenset({"full", "short"}), frozenset({"other"})}


def test_independently_defined_spacing_variants_share_the_same_acronym():
    names = ["Task Force on Climate-related Financial Disclosures",
             "Taskforce on Climate-related Financial Disclosures",
             "Task Force on Climaterelated Financial Disclosures"]
    rows = [scoped(str(i), name, name + " (TCFD) issues recommendations.", f"document:{i}")
            for i, name in enumerate(names)]
    rows.append(scoped("short", "TCFD", names[0] + " (TCFD) issues recommendations.", "document:other"))
    assert len(resolve(*rows)) == 1
    assert len(resolve(*reversed(rows))) == 1


def test_compact_name_alone_does_not_authorize_a_variant_merge():
    rows = [scoped("a", "North Star Holdings", "North Star Holdings reports."),
            scoped("b", "Northstar Holdings", "Northstar Holdings reports.")]
    assert len(resolve(*rows)) == 2


def test_shared_acronym_does_not_erase_different_words():
    names = ["Task Force on Climate-related Financial Disclosures",
             "Task Force for Climate-related Financial Disclosures"]
    rows = [scoped(str(i), name, name + " (TCFD) reports.") for i, name in enumerate(names)]
    rows.append(scoped("short", "TCFD", "TCFD reports.", "document:other"))
    assert len(resolve(*rows)) == 3


def test_unknown_pair_does_not_veto_a_supported_identity_chain():
    rows = [scoped(key, "Acme", "Acme reports.") for key in ("a", "b", "c")]
    for row in rows:
        row["type"] = "CONCEPT"
    rows[0]["properties"] = {"lei": "one"}
    rows[1]["properties"] = {"lei": "one", "registration": "two"}
    rows[2]["properties"] = {"registration": "two"}
    assert len(resolve(*rows, deduplication={"similarity": {"property_schema": {
        "lei": {"identity": True}, "registration": {"identity": True}}}})) == 1


def test_ambiguous_bridge_preserves_both_identified_subgroups():
    rows = [scoped(key, "Acme", "Acme reports.") for key in ("a", "aa", "bridge", "b", "bb")]
    for row, identifier in zip(rows, ("one", "one", None, "two", "two")):
        row["properties"] = {"lei": identifier} if identifier else {}
    config = {"deduplication": {"similarity": {"property_schema": {"lei": {"identity": True}}}}}
    for ordered in (rows, rows[::-1]):
        assert {frozenset(row.get("merged_from") or [row["id"]]) for row in resolve(*ordered, **config)} == {
            frozenset({"a", "aa"}), frozenset({"b", "bb"}), frozenset({"bridge"})}


def test_full_report_object_does_not_merge_with_the_organization_modifier():
    full = "Task Force on Climate-related Financial Disclosures"
    rows = [scoped("org", full, full + " (TCFD) develops recommendations."),
            scoped("modifier", "TCFD", "Our TCFD report follows its recommendations."),
            scoped("report", "TCFD report", "Our TCFD report follows its recommendations.")]
    rows[2]["type"] = "REPORT"
    assert {frozenset(row.get("merged_from") or [row["id"]]) for row in resolve(*rows)} == {
        frozenset({"org", "modifier"}), frozenset({"report"})}
