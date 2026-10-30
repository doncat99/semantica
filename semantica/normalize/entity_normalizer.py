"""
Entity Normalization Module

This module provides comprehensive entity normalization capabilities for the
Semantica framework, enabling standardization of named entities and proper nouns
across various formats and naming conventions.

Key Features:
    - Entity name standardization
    - Alias resolution and mapping
    - Entity disambiguation (context-aware)
    - Name variant handling (titles, honorifics, formats)
    - Entity linking and resolution
    - Support for multiple entity types (Person, Organization, etc.)

Main Classes:
    - EntityNormalizer: Main entity normalization coordinator
    - AliasResolver: Entity alias resolution engine
    - EntityDisambiguator: Entity disambiguation engine
    - NameVariantHandler: Name variant processing engine

Example Usage:
    >>> from semantica.normalize import EntityNormalizer
    >>> normalizer = EntityNormalizer()
    >>> normalized = normalizer.normalize_entity("John Doe", entity_type="Person")
    >>> canonical = normalizer.resolve_aliases("J. Doe")

Author: Semantica Contributors
License: MIT
"""

import re
from typing import Any, Dict, List, Optional

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


class EntityNormalizer:
    """
    Entity normalization and standardization coordinator.

    This class provides comprehensive entity normalization capabilities, coordinating
    alias resolution, disambiguation, and name variant handling.

    Features:
        - Entity name normalization and standardization
        - Alias resolution and mapping
        - Entity disambiguation using context
        - Name format standardization
        - Entity linking to canonical forms
        - Support for multiple entity types

    Example Usage:
        >>> normalizer = EntityNormalizer()
        >>> normalized = normalizer.normalize_entity("John Doe", entity_type="Person")
        >>> canonical = normalizer.resolve_aliases("J. Doe")
        >>> linked = normalizer.link_entities(["John Doe", "J. Doe", "Johnny Doe"])
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize entity normalizer.

        Sets up the normalizer with alias resolver, disambiguator, and variant
        handler components.

        Args:
            config: Configuration dictionary (optional)
            **kwargs: Additional configuration options (merged into config)
        """
        self.logger = get_logger("entity_normalizer")
        self.config = config or {}
        self.config.update(kwargs)

        self.alias_resolver = AliasResolver(**self.config)
        self.disambiguator = EntityDisambiguator(**self.config)
        self.variant_handler = NameVariantHandler(**self.config)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.logger.debug("Entity normalizer initialized")

    def normalize_entity(
        self,
        entity_name: str,
        entity_type: Optional[str] = None,
        resolve_aliases: bool = True,
        **options,
    ) -> str:
        """
        Normalize entity name to standard form.

        This method normalizes an entity name by cleaning whitespace, resolving
        aliases, and standardizing the format based on entity type.

        Args:
            entity_name: Entity name to normalize
            entity_type: Entity type (optional, e.g., "Person", "Organization")
            resolve_aliases: Whether to resolve aliases (default: True)
            **options: Additional normalization options (unused)

        Returns:
            str: Normalized entity name in standard form
        """
        tracking_id = self.progress_tracker.start_tracking(
            message="Semantica: Normalizing entity", file=None
        )
        try:
            if not entity_name:
                self.progress_tracker.stop_tracking(tracking_id, status="completed")
                return ""

            normalized = entity_name.strip()

            # Clean and standardize
            normalized = re.sub(r"\s+", " ", normalized)
            normalized = normalized.title() if entity_type == "Person" else normalized

            # Resolve aliases
            if resolve_aliases:
                resolved = self.alias_resolver.resolve_aliases(
                    normalized, entity_type=entity_type
                )
                if resolved:
                    normalized = resolved

            # Handle name variants
            normalized = self.variant_handler.normalize_name_format(
                normalized, format_type="standard"
            )

            self.progress_tracker.stop_tracking(tracking_id, status="completed")
            return normalized
        except Exception as e:
            self.progress_tracker.stop_tracking(tracking_id, status="failed")
            raise

    def resolve_aliases(self, entity_name: str, **context) -> Optional[str]:
        """
        Resolve entity aliases and variants.

        This method attempts to resolve an entity name to its canonical form
        using alias mapping.

        Args:
            entity_name: Entity name to resolve
            **context: Context information (e.g., entity_type)

        Returns:
            Optional[str]: Resolved canonical form if found, None otherwise
        """
        tracking_id = self.progress_tracker.start_tracking(
            message="Semantica: Resolving aliases", file=None
        )
        try:
            result = self.alias_resolver.resolve_aliases(entity_name, **context)
            self.progress_tracker.stop_tracking(tracking_id, status="completed")
            return result
        except Exception as e:
            self.progress_tracker.stop_tracking(tracking_id, status="failed")
            raise

    def disambiguate_entity(self, entity_name: str, **context) -> Dict[str, Any]:
        """
        Disambiguate entity when multiple candidates exist.

        This method disambiguates an entity name when multiple candidates exist,
        using context information to select the most likely candidate.

        Args:
            entity_name: Entity name to disambiguate
            **context: Context information (e.g., entity_type, context text)

        Returns:
            dict: Disambiguation result containing:
                - entity_name: Original entity name
                - entity_type: Detected entity type
                - confidence: Confidence score (0.0 to 1.0)
                - candidates: List of candidate entity names
        """
        tracking_id = self.progress_tracker.start_tracking(
            message="Semantica: Disambiguating entity", file=None
        )
        try:
            result = self.disambiguator.disambiguate(entity_name, **context)
            self.progress_tracker.stop_tracking(tracking_id, status="completed")
            return result
        except Exception as e:
            self.progress_tracker.stop_tracking(tracking_id, status="failed")
            raise

    def link_entities(self, entities: List[str], **options) -> Dict[str, str]:
        """
        Link entities to canonical forms.

        This method links a list of entity names to their canonical forms,
        creating a mapping from original names to normalized names.

        Args:
            entities: List of entity names to link
            **options: Linking options (passed to normalize_entity)

        Returns:
            dict: Dictionary mapping original entity names to canonical forms
        """
        tracking_id = self.progress_tracker.start_tracking(
            message="Semantica: Linking entities", file=None
        )
        try:
            linked = {}

            for entity in entities:
                canonical = self.normalize_entity(entity, **options)
                linked[entity] = canonical

            self.progress_tracker.stop_tracking(tracking_id, status="completed")
            return linked
        except Exception as e:
            self.progress_tracker.stop_tracking(tracking_id, status="failed")
            raise


class AliasResolver:
    """
    Entity alias resolution engine.

    This class provides alias resolution capabilities, mapping entity name
    variations and aliases to canonical forms.

    Features:
        - Entity alias and nickname resolution
        - Name variation mapping
        - Support for different naming conventions
        - Cultural and linguistic variation handling

    Example Usage:
        >>> resolver = AliasResolver(alias_map={"j. doe": "John Doe"})
        >>> canonical = resolver.resolve_aliases("J. Doe")
    """

    def __init__(self, **config):
        """
        Initialize alias resolver.

        Sets up the resolver with alias mapping dictionary.

        Args:
            **config: Configuration options:
                - alias_map: Dictionary mapping aliases to canonical forms
        """
        self.logger = get_logger("alias_resolver")
        self.config = config
        self.alias_map = config.get("alias_map", {})

        self.logger.debug(f"Alias resolver initialized ({len(self.alias_map)} aliases)")

    def resolve_aliases(self, entity_name: str, **context) -> Optional[str]:
        """
        Resolve entity aliases to canonical form.

        This method looks up an entity name in the alias map and returns
        its canonical form if found.

        Args:
            entity_name: Entity name to resolve
            **context: Context information (e.g., entity_type, currently unused)

        Returns:
            Optional[str]: Resolved canonical form if found in alias map,
                          None otherwise
        """
        # Check alias map
        entity_lower = entity_name.lower()

        if entity_lower in self.alias_map:
            return self.alias_map[entity_lower]

        # Check for common aliases
        for alias, canonical in self.alias_map.items():
            if alias.lower() == entity_lower:
                return canonical

        return None

    def map_variants(self, entity_name: str, entity_type: str) -> str:
        """
        Map entity name variants.

        This method maps entity name variants to a standard form based on
        entity type. Currently returns the name as-is; can be extended for
        variant mapping.

        Args:
            entity_name: Entity name to map
            entity_type: Entity type (e.g., "Person", "Organization")

        Returns:
            str: Mapped variant (currently returns entity_name as-is)
        """
        # Simple variant mapping - can be extended
        return entity_name

    def handle_cultural_variations(
        self, entity_name: str, culture: Optional[str] = None
    ) -> str:
        """
        Handle cultural and linguistic variations.

        This method handles cultural and linguistic variations in entity names.
        Currently returns the name as-is; can be extended for cultural
        normalization.

        Args:
            entity_name: Entity name to process
            culture: Culture identifier (optional, e.g., "en-US", "zh-CN")

        Returns:
            str: Culturally appropriate form (currently returns entity_name as-is)
        """
        return entity_name


class EntityDisambiguator:
    """
    Entity disambiguation engine.

    This class provides entity disambiguation capabilities, using context
    information to resolve ambiguous entity references.

    Features:
        - Context-aware entity disambiguation
        - Entity type classification
        - Confidence score calculation
        - Candidate entity generation

    Example Usage:
        >>> disambiguator = EntityDisambiguator()
        >>> result = disambiguator.disambiguate("Apple", context="technology company")
        >>> entity_type = disambiguator.classify_entity_type("John Doe")
    """

    def __init__(self, **config):
        """
        Initialize entity disambiguator.

        Sets up the disambiguator with configuration options.

        Args:
            **config: Configuration options (currently unused)
        """
        self.logger = get_logger("entity_disambiguator")
        self.config = config
        self._scope_definitions = {}
        self._source_definitions = {}
        self._project_definitions = {}
        self._context_definitions = {}
        self._defined_referents = set()
        self._definition_variants = {}
        self._local_owners = {}
        self._owner_aliases = {}
        self._identity_facts = {}
        self._described_scopes = set()
        self._supported_facts = {}
        self._instances = {}
        self.logger.debug("Entity disambiguator initialized")

    @staticmethod
    def _identity_name(value):
        return " ".join(str(value).translate(str.maketrans("‐‑–—", "----")).split()).casefold()

    def disambiguate(self, entity_name: str, **context) -> Dict[str, Any]:
        """
        Disambiguate entity using context.

        This method disambiguates an entity name using context information.
        Currently provides a basic implementation; can be extended with
        machine learning models for improved disambiguation.

        Args:
            entity_name: Entity name to disambiguate
            **context: Context information containing:
                - entity_type: Entity type (optional)
                - context: Text context (optional)

        Returns:
            dict: Disambiguation result containing:
                - entity_name: Original entity name
                - entity_type: Detected entity type
                - confidence: Confidence score (0.0 to 1.0)
                - candidates: List of candidate entity names
        """
        if "candidate" in context:
            return self.compare(context["entity"], context["candidate"],
                                identity=context.get("identity", {}))
        entity_type = context.get("entity_type")

        return {
            "entity_name": entity_name,
            "entity_type": entity_type,
            "confidence": 0.0,
            "decision": "unknown",
            "candidates": [entity_name],
        }

    @staticmethod
    def _scope(entity):
        return entity.get("metadata", {}).get("identity_scope")

    @staticmethod
    def _source_ids(entity):
        """Return the material source provenance, distinct from a representation scope."""
        values = entity.get("metadata", {}).get("source_ids", [])
        if isinstance(values, str):
            values = [values]
        return frozenset(str(value) for value in values if value)

    @classmethod
    def _same_source(cls, left, right):
        sources = cls._source_ids(left) & cls._source_ids(right)
        return bool(sources)

    @classmethod
    def _profile(cls, entity):
        return entity.get("metadata", {}).get("identity_profile") or {}

    def _owner(self, entity):
        profile = self._profile(entity)
        owner = str(profile.get("owner") or "").strip()
        quote = str(profile.get("evidence") or "")
        if owner and re.search(r"(?<!\w)" + re.escape(owner) + r"(?!\w)", quote, re.I):
            normalized = self._identity_name(owner)
            definitions = self._owner_aliases.get((self._scope(entity), normalized), set())
            return next(iter(definitions)) if len(definitions) == 1 else normalized
        return ""

    @classmethod
    def _dependent(cls, entity, referent):
        kind = cls._profile(entity).get("referent_kind")
        if kind and kind != "named_entity":
            return kind in {"dependent_entity", "role", "report", "index"}
        head, separator, _ = referent.partition(' of ')
        if separator and cls._dependent(entity, head):
            return True
        if re.search(r'\b(?:company|foundation)$', referent) and len(referent.split()) > 1:
            return referent.split()[0] in {'the', 'our', 'this'}
        # The syntactic head is open to arbitrary modifiers; modifiers never
        # turn a policy or committee into a globally unique proper name.
        return bool(re.search(r"\b(?:board(?: of directors)?|committee|team|foundation|company|"
            r"department|division|council|management|officer|president|policy|report|index)$|"
            r"\bcode of \w+$", referent))

    @staticmethod
    def _abbreviation(full, short):
        # Explicit source definitions can use internal letters (ISO), not only initials.
        letters = iter(re.sub(r"[^\w]", "", full.casefold()))
        return all(any(char == letter for letter in letters) for char in short.casefold())

    @classmethod
    def _referent_name(cls, value):
        name = cls._identity_name(value)
        return name[4:] if name.startswith('the ') and len(name.split()) > 2 else name

    @classmethod
    def _words(cls, text):
        """Order-independent literal support; this does not infer semantic synonyms."""
        stop = {'a', 'an', 'the', 'of', 'and', 'is', 'are', 'our', 'its', 'in', 'for', 'to'}
        return frozenset(word[:-1] if len(word) > 3 and word.endswith('s') else word
            for word in re.findall(r'[^\W_]+', cls._identity_name(text)) if word not in stop)

    @staticmethod
    def _definition_lexeme(word):
        """Collapse only conservative English inflection in grounded names."""
        if word.endswith('ability') and len(word) > 9:
            return word[:-7]
        if word.endswith('able') and len(word) > 6:
            return word[:-4]
        if word.endswith('ies') and len(word) > 5:
            return word[:-3] + 'y'
        return word[:-1] if len(word) > 4 and word.endswith('s') else word

    @classmethod
    def _definition_fingerprint(cls, value):
        return frozenset(cls._definition_lexeme(word) for word in re.findall(
            r'[^\W_]+', cls._identity_name(value)))

    @classmethod
    def _definition_fingerprints(cls, value):
        normalized = cls._identity_name(value)
        compact = re.sub(r'[^a-z0-9]+', '', normalized)
        return (
            ("tokens", cls._definition_fingerprint(value)),
            ("compact", compact),
        )

    @classmethod
    def _description_key(cls, entity):
        value = str(entity.get('description') or '')
        supported = entity.get('metadata', {}).get('description_evidence_ids')
        if value and (supported or value.casefold() in str(entity.get('context', '')).casefold()):
            return cls._words(value)
        return frozenset()

    @classmethod
    def _context_definition(cls, entity):
        name = str(entity.get('name', ''))
        match = re.search(r'(?<!\w)' + re.escape(name) +
            r'(?:\s*\([\"“”\w -]+\))?\s+is\s+((?:not\s+)?(?:an?|the)\s+[^.!?;\n]+)',
            str(entity.get('context', '')), re.I)
        return cls._words(match[1]) if match else frozenset()

    @classmethod
    def _context_fact(cls, entity):
        """Only explicit subject definitions supply a context identity hint.

        Different hints request review; they never prove different identities.
        Other prose is missing information, including ordinary reporting activity.
        """
        name = str(entity.get('name', ''))
        text = str(entity.get('context', ''))
        definition = cls._context_definition(entity)
        if definition:
            return definition
        match = re.search(r'(?<!\w)' + re.escape(name) +
            r'(?:\s*\([\"“”\w -]+\))?\s+'
            r'(?:manufactures?|publish(?:es)?|operates?)\s+([^.!?;\n]+)', text, re.I)
        return cls._words(match[1]) if match else frozenset()

    def _explicit_owner(self, entity):
        owner = self._owner(entity)
        if owner:
            return owner
        if str(entity.get('type', '')).upper() == 'PERSON':
            match = re.search(r'(?<!\w)' + re.escape(str(entity.get('name', ''))) +
                r'\s+is\s+([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*)*)\s+chief\s+(?:\w+\s+){0,4}officer\b',
                str(entity.get('context', '')))
            return self._identity_name(match[1]) if match else ''
        if not self._dependent(entity, self._identity_name(entity.get('name', ''))):
            return ''
        name, context = str(entity.get('name', '')), str(entity.get('context', ''))
        # Adjacency and "of" may complete a name; only a possessive states ownership.
        proper = r'([A-Z][\w&.-]*(?:[ \t]+[A-Z][\w&.-]*)*)'
        match = re.search(r'(?<!\w)' + proper + r"['’]s\s+" + re.escape(name) + r'(?!\w)', context)
        if not match:
            return ''
        owner = self._identity_name(match[1])
        if owner in {'the', 'our', 'a', 'an'}:
            return ''
        definitions = self._owner_aliases.get((self._scope(entity), owner), set())
        return next(iter(definitions)) if len(definitions) == 1 else owner

    def _effective_owner(self, entity):
        owner = self._explicit_owner(entity)
        if owner:
            return owner
        owners = self._local_owners.get((self._scope(entity), self._referent(entity)), set())
        return next(iter(owners)) if len(owners) == 1 else ''

    def _instance(self, entity):
        profile = self._profile(entity)
        value = profile.get('instance')
        if value and value in str(profile.get('evidence', '')):
            normalized = self._identity_name(value)
            year = re.fullmatch(r'(?:(?:fiscal year|edition|version)\s+)?((?:19|20)\d{2})', normalized)
            return year[1] if year else normalized
        if profile.get('referent_kind') not in {'report', 'index', 'standard'} and not re.search(
                r'\b(report|index|standard)\b', self._identity_name(entity.get('name', ''))):
            return ''
        # Years in a title/description identify an instance. Incidental years
        # elsewhere in a paragraph do not.
        text = str(entity.get('name', '')) + ' ' + str(entity.get('description') or '')
        versions = set(re.findall(r'\b(?:19|20)\d{2}\b', text))
        if not versions:
            versions = set(re.findall(r'\b(?:fiscal year|edition|version)\s+((?:19|20)\d{2})\b',
                                      str(entity.get('context', '')), re.I))
        return next(iter(versions)) if len(versions) == 1 else ''

    @staticmethod
    def _compatible_support(left, right):
        if not left or not right:
            return True
        if bool(left & {'no', 'not', 'never', 'non'}) != bool(right & {'no', 'not', 'never', 'non'}):
            return False
        return left <= right or right <= left

    @staticmethod
    def _contradictory_support(left, right):
        """Different prose is neutral; negating shared content is a conflict hint."""
        negative = {'no', 'not', 'never', 'non'}
        return bool(left - negative) and bool(right - negative) and bool(
            (left - negative) & (right - negative)) and (
            bool(left & negative) != bool(right & negative))

    def _supported_fact(self, entity):
        if id(entity) in self._supported_facts:
            return self._supported_facts[id(entity)]
        key = (self._scope(entity), self._referent(entity),
               self._effective_owner(entity), self._instance(entity))
        fact = (self._context_definition(entity) if key in self._described_scopes
                and not self._description_key(entity) else self._context_fact(entity))
        if fact:
            return fact
        observed = self._identity_facts.get(key, set())
        if observed and all(self._compatible_support(a, b) for a in observed for b in observed):
            return max(observed, key=lambda words: (len(words), tuple(sorted(words))))
        return frozenset()

    def prepare(self, entities):
        """Index source-grounded definitions once per resolution, never across runs.

        Scope records provenance, not an entity identity boundary.
        Only an extracted full name actually followed by its parenthetical
        abbreviation supplies a binding; old canonical aliases do not supply one.
        """
        self._scope_definitions = {}
        self._source_definitions = {}
        self._project_definitions = {}
        self._context_definitions = {}
        self._defined_referents = set()
        self._definition_variants = {}
        self._local_owners = {}
        self._owner_aliases = {}
        self._identity_facts = {}
        self._described_scopes = set()
        self._supported_facts = {}
        for entity in entities:
            scope = self._scope(entity)
            if not scope:
                continue
            name = str(entity.get("name", "")).strip()
            if re.fullmatch(r'[A-Z][A-Z0-9-]{1,15}', name):
                pattern = (r'(?<!\w)([A-Z][\w&.-]*(?:[ \t]+(?:[A-Z][\w&.-]*|of|for|and|the)){1,15})'
                           r'\s*\(["“]?' + re.escape(name) + r'["”]?\)')
                for match in re.finditer(pattern, str(entity.get('context', ''))):
                    full = match[1]
                    if self._abbreviation(full, name):
                        referent = self._referent_name(full)
                        self._scope_definitions.setdefault((scope, name.casefold()), set()).add(referent)
                        self._project_definitions.setdefault(name.casefold(), set()).add(referent)
                        self._defined_referents.add(referent)
            full = re.sub(r"\s*\([A-Z][A-Z0-9-]+\)$", "", name).strip()
            if len(full.split()) < 2:
                continue
            pattern = r"(?<!\w)" + re.escape(full) + r"\s*\([\"“]?([A-Z][A-Z0-9-]+)[\"”]?\)"
            for match in re.finditer(pattern, str(entity.get("context", ""))):
                short, referent = match[1].casefold(), self._referent_name(full)
                prefix = str(entity.get('context', ''))[:match.start()]
                preceding = re.search(r'([A-Z][\w&.-]*)[ \t]+$', prefix)
                if preceding and preceding[1] not in {'The', 'A', 'An', 'Our', 'Its', 'Their', 'This'}:
                    # An extracted suffix inside a longer proper name is not
                    # a second definition of that name's abbreviation.
                    continue
                if not self._abbreviation(full, short):
                    continue
                self._scope_definitions.setdefault((scope, short), set()).add(referent)
                self._project_definitions.setdefault(short, set()).add(referent)
                self._defined_referents.add(referent)
        # Only independently grounded expansions of the same abbreviation may
        # share a separator variant; compact spelling alone is not identity.
        variants = {}
        for short, definitions in self._project_definitions.items():
            for full in definitions:
                if len(full.split()) >= 4:
                    for fingerprint in self._definition_fingerprints(full):
                        variants.setdefault((short, fingerprint), set()).add(full)
        for definitions in variants.values():
            if len(definitions) < 2:
                continue
            canonical = min(definitions)
            for full in definitions:
                self._definition_variants[full] = canonical
        self._defined_referents = {self._definition_variants.get(full, full)
                                  for full in self._defined_referents}
        # Mentions in one sentence can have different bounded context windows.
        # Match indexed expansions in each mention's own window, never another's.
        for entity in entities:
            scope = self._scope(entity)
            name = self._identity_name(entity.get("name", ""))
            definitions = self._project_definitions.get(name, set())
            if not scope or not definitions:
                continue
            context = self._identity_name(entity.get("context", ""))
            if len(re.findall(r"(?<!\w)" + re.escape(name) + r"(?!\w)", context)) != 1:
                continue
            local = {full for full in definitions if re.search(
                r"(?<!\w)" + re.escape(full) + r"\s*\(\s*[\"“]?" + re.escape(name) + r"[\"”]?\s*\)", context)}
            # With one acronym occurrence, nested suffix matches describe the
            # same definition span; only its longest grounded name is local.
            local = {full for full in local if not any(
                other.endswith(' ' + full) for other in local if other != full)}
            if local:
                self._context_definitions[(scope, entity.get("context", ""), name)] = local
                # A located definition is valid even when extraction retained
                # only the acronym mention. Reuse it within this source.
                self._scope_definitions.setdefault((scope, name), set()).update(local)
                for source in self._source_ids(entity):
                    self._source_definitions.setdefault((source, name), set()).update(local)
        # Owner aliases use the same grounded definition mechanism. A legal
        # suffix is never stripped globally.
        for entity in entities:
            owner = str(self._profile(entity).get('owner') or '')
            quote = str(self._profile(entity).get('evidence') or '')
            if not owner:
                continue
            pattern = r'(?<!\w)([A-Z][\w&.-]*(?:[ \t]+[A-Z][\w&.-]*)*)\s*\(["“]?([\w -]+)["”]?\)'
            for match in re.finditer(pattern, quote):
                full, short = self._identity_name(match[1]), self._identity_name(match[2])
                if self._identity_name(owner) in {full, short} and self._abbreviation(full, short):
                    self._owner_aliases.setdefault((self._scope(entity), full), set()).add(full)
                    self._owner_aliases.setdefault((self._scope(entity), short), set()).add(full)
        for entity in entities:
            referent = self._referent(entity)
            owner = self._explicit_owner(entity)
            if owner and self._scope(entity):
                self._local_owners.setdefault((self._scope(entity), referent), set()).add(owner)
        self._instances = {}
        for entity in entities:
            if self._description_key(entity):
                self._described_scopes.add((self._scope(entity), self._referent(entity),
                    self._effective_owner(entity), self._instance(entity)))
        for entity in entities:
            referent = self._referent(entity)
            owner = self._effective_owner(entity)
            instance = self._instance(entity)
            self._instances.setdefault((referent, owner), set()).update([instance] if instance else [])
            key = (self._scope(entity), referent, owner, instance)
            fact = (self._context_definition(entity) if key in self._described_scopes
                    and not self._description_key(entity) else self._context_fact(entity))
            if fact:
                self._identity_facts.setdefault(key, set()).add(fact)
        self._supported_facts = {id(entity): self._supported_fact(entity) for entity in entities}

    def _definitions(self, entity, name):
        definitions = self._context_definitions.get((self._scope(entity), entity.get("context", ""), name), set())
        if definitions:
            return {self._definition_variants.get(full, full) for full in definitions}
        # A material-local located expansion is stronger than the project-wide
        # set: other documents may contain a different expansion for the same
        # acronym, but must not poison bare mentions in this source.
        source_definitions = set()
        for source in self._source_ids(entity):
            source_definitions.update(self._source_definitions.get((source, name), set()))
        definitions = source_definitions or self._scope_definitions.get((self._scope(entity), name), set())
        return {self._definition_variants.get(full, full) for full in definitions}

    def _grounded_full_definition(self, entity, referent):
        """A locally expanded full name is a named referent, not a generic dependent head."""
        name = self._referent_name(entity.get("name", ""))
        head, separator, _ = referent.partition(' of ')
        return not (separator and self._dependent(entity, head)) and name == referent and (
            referent in self._defined_referents or name in self._definition_variants)

    def _referent(self, entity):
        scope = self._scope(entity)
        name = self._referent_name(entity.get("name", ""))
        expanded = re.fullmatch(r"(.+?)\s*\(([a-z][a-z0-9-]+)\)", name)
        if expanded and expanded[1] in self._scope_definitions.get((scope, expanded[2]), set()):
            return self._definition_variants.get(expanded[1], expanded[1])
        definitions = self._definitions(entity, name)
        return next(iter(definitions)) if len(definitions) == 1 else self._definition_variants.get(name, name)

    def candidate_keys(self, entity: Dict[str, Any]) -> set:
        """Names retrieve candidates; an acronym is never merge permission."""
        names = [entity.get("name", ""), *entity.get("aliases", [])]
        keys = set()
        for name in names:
            normalized = self._identity_name(name)
            if normalized:
                keys.add(("name", normalized))
                if normalized.startswith('the ') and len(normalized.split()) > 2:
                    keys.add(('name', normalized[4:]))
            words = re.findall(r"[^\W_]+", str(name), re.UNICODE)
            if len(words) > 1:
                keys.add(("name", "".join(word[0] for word in words).casefold()))
        if self._scope(entity):
            keys.add(("reference", self._referent(entity)))
            for full in self._project_definitions.get(self._identity_name(entity.get('name', '')), set()):
                keys.add(('reference', self._definition_variants.get(full, full)))
        return keys

    def compare(self, left: Dict[str, Any], right: Dict[str, Any], *, identity=None) -> Dict[str, Any]:
        """Reuse grounded names across documents unless ambiguity is observed.

        Source scope records provenance, not a boundary for named identity.
        Person names and owner-dependent bodies still need stronger support.
        Conflicting identifiers and competing definitions veto that default.
        Repetition alone is not ambiguity. This is deterministic linking, not
        semantic inference over arbitrary prose.
        """
        identity = identity or {}
        result = {"decision": "unknown", "confidence": 0.0, "reason": "insufficient_identity_evidence"}
        if identity.get("conflicts"):
            return {**result, "decision": "different", "reason": "identity_conflict"}
        if identity.get("matches"):
            return {"decision": "same", "confidence": 1.0, "reason": "trusted_identifier"}
        names = [str(row.get("name", "")).strip() for row in (left, right)]
        contexts = [str(row.get("context", "")) for row in (left, right)]
        # Support must contain the actual mention, not merely an assigned label.
        occurrences = [len(re.findall(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.I))
                       if name else 0 for name, text in zip(names, contexts)]
        if not all(occurrences):
            return result
        if self._identity_name(names[0]) == self._identity_name(names[1]):
            # Located mention identity outranks ambiguity elsewhere in the corpus.
            # Shared context/description evidence does not identify an occurrence.
            spans = [set(row.get("evidence_ids", [])) - {
                row.get("metadata", {}).get("identity_context_evidence_id"),
                *row.get("metadata", {}).get("description_evidence_ids", [])}
                for row in (left, right)]
            if spans[0] & spans[1]:
                return {"decision": "same", "confidence": 1.0, "reason": "same_located_occurrence"}
        kinds = {self._profile(row).get("referent_kind") for row in (left, right)} - {None, "", "named_entity"}
        if len(kinds) > 1:
            return {**result, "decision": "different", "reason": "incompatible_referent_kinds"}
        owners = [self._effective_owner(row) for row in (left, right)]
        if all(owners) and owners[0] != owners[1]:
            return {**result, "decision": "different", "reason": "different_owners"}
        instances = [self._instance(row) for row in (left, right)]
        if all(instances) and instances[0] != instances[1]:
            return {**result, "decision": "different", "reason": "different_instances"}
        types = {str(row.get("type", "")).upper() for row in (left, right)} - {""}
        organizations = {"ORG", "ORGANIZATION", "COMPANY"}
        type_noise = types <= organizations | {"CONCEPT"} and bool(types & organizations)
        if len(types) > 1 and not type_noise:
            return {**result, "decision": "different", "reason": "incompatible_entity_types"}
        scope = self._scope(left)
        if scope and self._scope(right):
            referents = [self._referent(row) for row in (left, right)]
            descriptions = [self._description_key(row) for row in (left, right)]
            if self._contradictory_support(*descriptions):
                return {**result, "reason": "descriptions_require_disambiguation"}
            facts = [self._supported_fact(row) for row in (left, right)]
            definitions = [self._context_definition(row) for row in (left, right)]
            if all(definitions) and not self._compatible_support(*definitions):
                return {**result, "reason": "context_requires_disambiguation"}
            explicit_same_full_name = (
                self._identity_name(names[0]) == self._identity_name(names[1])
                and len(self._identity_name(names[0]).split()) > 1
                and all(self._grounded_full_definition(row, referent)
                        for row, referent in zip((left, right), referents))
            )
            # Nonidentical prose is not proof of a different entity. Explicit,
            # non-overlapping identifying claims do require a review decision.
            if all(facts) and not self._compatible_support(*facts) and not explicit_same_full_name:
                if not all(descriptions) or not self._compatible_support(*descriptions):
                    return {**result, "reason": "context_requires_disambiguation"}
            # Project definitions retrieve candidates; applying a remote alias
            # additionally needs compatible identifying support at this mention.
            if referents[0] != referents[1]:
                remote_binding = False
                for index in (0, 1):
                    definitions = self._project_definitions.get(self._identity_name(names[index]), set())
                    raw_definitions = set(definitions)
                    definitions = {self._definition_variants.get(full, full) for full in definitions}
                    if len(definitions) == 1 and referents[1 - index] in definitions:
                        # A bare remote acronym needs corroboration. Multiple
                        # grounded spellings must independently collapse to
                        # one referent, or the local contexts must agree.
                        if (len(raw_definitions) > 1 or
                                (all(facts) and self._compatible_support(*facts)) or
                                self._same_source(left, right)):
                            referents[index] = referents[1 - index]
                            remote_binding = True
                if not remote_binding:
                    return {**result, "reason": "unbound_name_variant"}
            if any(referent == self._identity_name(row.get("name", "")) and
                   len(self._definitions(row, referent)) > 1
                   for row, referent in zip((left, right), referents)):
                return {**result, "reason": "competing_scoped_definitions"}
            if referents[0] == referents[1]:
                dependent = any(self._dependent(row, referent) and
                                not self._grounded_full_definition(row, referent)
                                for row, referent in zip((left, right), referents))
                local_definition = any(self._grounded_full_definition(row, referents[0])
                                       for row in (left, right)) or (
                    (scope == self._scope(right) or self._same_source(left, right)) and
                    len(self._local_owners.get((scope, referents[0]), set())) <= 1 and
                    any(self._definitions(row, self._identity_name(row.get('name', ''))) == {referents[0]}
                        for row in (left, right)))
                if dependent and not local_definition and not (all(owners) and owners[0] == owners[1]):
                    if any(owners) or scope != self._scope(right):
                        return {**result, "reason": "unresolved_owner"}
                if dependent and not local_definition and not all(owners):
                    return {**result, "reason": "unresolved_owner"}
                if dependent and scope != self._scope(right) and (kinds & {'report', 'index'} or
                        any(re.search(r'\b(report|index)$', referent) for referent in referents)):
                    if not all(instances):
                        return {**result, "reason": "unresolved_instance"}
                if not all(instances) and len(self._instances.get((referents[0], owners[0]), set())) > 1:
                    return {**result, "reason": "unresolved_instance"}
                # Same acronym with competing project meanings remains unresolved
                # when neither mention carries a local binding.
                # Competing expansions make a bare acronym ambiguous, but they
                # do not make the explicitly grounded full name ambiguous.
                # The latter is positive identity evidence in its own right;
                # applying the project-wide veto to it fragmented every
                # repeated full-name mention (notably SASB).
                same_name_is_grounded = all(
                    self._identity_name(name) in self._defined_referents
                    for name in names
                )
                if len(self._project_definitions.get(self._identity_name(names[0]), set())) > 1 and all(
                        not self._definitions(row, self._identity_name(row.get('name', ''))) for row in (left, right)) \
                        and not same_name_is_grounded:
                    return {**result, "reason": "competing_scoped_definitions"}
                defined = referents[0] in self._defined_referents
                named_type = types <= {
                    "ORG", "ORGANIZATION", "COMPANY", "GPE", "LOC", "LOCATION",
                    "FAC", "FACILITY", "PRODUCT", "EVENT", "LAW", "WORK_OF_ART", "CONCEPT"}
                if types == {'PERSON'} and scope == self._scope(right):
                    roles = [re.search(r'\bchief\s+(?:\w+\s+){0,4}officer\b', text, re.I) for text in contexts]
                    if all(roles) and self._identity_name(roles[0][0]) == self._identity_name(roles[1][0]):
                        return {"decision": "same", "confidence": .9, "reason": "local_person_role"}
                if defined or named_type:
                    return {"decision": "same", "confidence": .9,
                            "reason": "grounded_definition" if defined else "grounded_same_name"}
        if names[0].casefold() != names[1].casefold():
            for full, short in (names, names[::-1]):
                words = re.findall(r"[^\W_]+", full, re.UNICODE)
                if len(words) < 2 or "".join(word[0] for word in words).casefold() != short.casefold():
                    continue
                definition = re.compile(r"(?<!\w)" + re.escape(full) + r"\s*\(\s*" + re.escape(short) + r"\s*\)", re.I)
                # Both mentions must carry the definition; an acronym elsewhere
                # in the project may refer to a different organization.
                if all(definition.search(text) and len(re.findall(
                        r"(?<!\w)" + re.escape(short) + r"(?!\w)", text, re.I)) == 1
                       for text in contexts):
                    return {"decision": "same", "confidence": 1.0, "reason": "grounded_abbreviation_definition"}
        return result

    def classify_entity_type(self, entity_name: str, **context) -> str:
        """
        Classify entity type for disambiguation.

        This method classifies the entity type using simple heuristics based
        on name format. Can be extended with more sophisticated classification.

        Args:
            entity_name: Entity name to classify
            **context: Context information (currently unused)

        Returns:
            str: Entity type classification:
                - "Person": If name starts with uppercase and contains space
                - "Organization": If name starts with uppercase
                - "Entity": Otherwise
        """
        if not entity_name:
            return "Entity"

        # Simple heuristic-based classification
        if entity_name[0].isupper() and " " in entity_name:
            return "Person"
        elif entity_name[0].isupper():
            return "Organization"
        else:
            return "Entity"

    def calculate_confidence(
        self, candidates: List[str], **context
    ) -> Dict[str, float]:
        """
        Calculate confidence scores for candidates.

        Names alone provide no identity evidence. Pairwise decisions use compare.

        Args:
            candidates: List of candidate entity names
            **context: Context information (currently unused)

        Returns:
            dict: Dictionary mapping candidate names to confidence scores
                 (0.0 to 1.0)
        """
        return {candidate: 0.0 for candidate in candidates}


class NameVariantHandler:
    """
    Name variant processing engine.

    This class provides name variant handling capabilities, processing different
    name formats, titles, and honorifics.

    Features:
        - Name format normalization (standard, title, lower)
        - Title and honorific handling
        - Name variant generation
        - Format standardization

    Example Usage:
        >>> handler = NameVariantHandler()
        >>> normalized = handler.normalize_name_format("Dr. John Doe", "standard")
        >>> title_info = handler.handle_titles_and_honorifics("Mr. John Doe")
    """

    def __init__(self, **config):
        """
        Initialize name variant handler.

        Sets up the handler with titles dictionary and configuration.

        Args:
            **config: Configuration options:
                - titles: Set of title strings (optional, uses default if not provided)
        """
        self.logger = get_logger("name_variant_handler")
        self.config = config
        self.titles = config.get(
            "titles", {"Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sir", "Madam"}
        )

        self.logger.debug(
            f"Name variant handler initialized ({len(self.titles)} titles)"
        )

    def process_variants(self, entity_name: str, **options) -> List[str]:
        """
        Process entity name variants.

        This method generates a list of name variants for an entity, including
        the original name and normalized forms.

        Args:
            entity_name: Entity name to process
            **options: Processing options (unused)

        Returns:
            list: List of name variant strings
        """
        variants = [entity_name]

        # Generate common variants
        normalized = self.normalize_name_format(entity_name, "standard")
        if normalized != entity_name:
            variants.append(normalized)

        return variants

    def normalize_name_format(
        self, entity_name: str, format_type: str = "standard"
    ) -> str:
        """
        Normalize name format.

        This method normalizes the format of an entity name, removing titles
        and applying the specified format type.

        Args:
            entity_name: Entity name to normalize
            format_type: Format type (default: "standard"):
                - "standard": Title case for each word part
                - "title": Title case for entire name
                - "lower": Lowercase

        Returns:
            str: Formatted name with titles removed
        """
        # Remove titles
        name = entity_name
        for title in self.titles:
            # Case-insensitive removal of titles from the beginning of the name
            pattern = re.compile(r"^" + re.escape(title) + r"\s*", re.IGNORECASE)
            name = pattern.sub("", name)

        name = name.strip()

        if format_type == "standard":
            # Title case for names
            parts = name.split()
            name = " ".join(part.capitalize() for part in parts)
        elif format_type == "title":
            name = name.title()
        elif format_type == "lower":
            name = name.lower()

        return name

    def handle_titles_and_honorifics(self, entity_name: str) -> Dict[str, Any]:
        """
        Handle titles and honorifics in names.

        This method extracts titles and honorifics from entity names, returning
        the name without title and the extracted title.

        Args:
            entity_name: Entity name with potential title

        Returns:
            dict: Dictionary containing:
                - name: Name without title
                - title: Extracted title (None if no title found)
        """
        title = None
        name = entity_name

        for t in self.titles:
            if entity_name.startswith(t):
                title = t
                name = entity_name.replace(t, "").strip()
                break

        return {"name": name, "title": title}
