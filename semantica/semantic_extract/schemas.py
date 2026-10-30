from typing import Any, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict, create_model
from pydantic.json_schema import SkipJsonSchema

def validate_fact_qualifiers(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("fact qualifiers must be an object")
    if set(value) - {"polarity", "condition", "time", "unit", "value"}:
        raise ValueError("fact qualifiers contain unsupported keys")
    if value.get("polarity") not in {"positive", "negative"}:
        raise ValueError("fact qualifiers require positive or negative polarity")
    if any(not isinstance(item, str) or not item.strip()
           for key, item in value.items() if key != "polarity"):
        raise ValueError("fact qualifier values must be non-empty strings")
    return value


class IdentityProfileOut(BaseModel):
    """Readable description with its separately located source support."""
    model_config = ConfigDict(extra="forbid")
    description: Optional[str] = Field(default=None, min_length=1, max_length=512)
    evidence: str = Field(min_length=1, max_length=1600)
    evidence_occurrence: int = Field(ge=0)
    referent_kind: Optional[Literal["named_entity", "institution", "dependent_entity", "concept", "role", "framework", "standard", "report", "index"]] = None
    owner: Optional[str] = Field(default=None, min_length=1, max_length=256)
    instance: Optional[str] = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def grounded_owner(self):
        if self.owner and self.owner not in self.evidence:
            raise ValueError("identity owner must occur exactly in profile evidence")
        if self.instance and self.instance not in self.evidence:
            raise ValueError("identity instance must occur exactly in profile evidence")
        if not any((self.description, self.owner, self.referent_kind, self.instance)):
            raise ValueError("identity profile requires an identifying fact")
        return self


class EntityOut(BaseModel):
    """Canonical schema for entity extraction output."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    
    text: str = Field(..., description="The text content of the entity")
    label: str = Field(..., description="The type or label of the entity (e.g., PERSON, ORG)")
    start: int = Field(0, description="Start character index", alias="start_char")
    end: int = Field(0, description="End character index", alias="end_char")
    confidence: float = Field(0.9, description="Confidence score between 0 and 1")
    occurrence: Optional[int] = Field(None, ge=0, description="Zero-based exact text occurrence")
    attributes: dict = Field(default_factory=dict, description="Typed attributes defined by the extraction specification")
    identity_profile: Optional[IdentityProfileOut] = None
    metadata: dict = Field(default_factory=dict, description="Additional metadata including provenance")

    @field_validator("text", mode="before")
    @classmethod
    def clean_text(cls, v):
        if isinstance(v, str):
            return v.strip()
        return str(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, v):
        if isinstance(v, str):
            try:
                v = float(v)
            except ValueError:
                return 0.9
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return 0.9
    
    @model_validator(mode="before")
    @classmethod
    def handle_aliases(cls, data):
        if isinstance(data, dict):
            # Handle 'type' as alias for 'label'
            if "label" not in data and "type" in data:
                data["label"] = data["type"]
            # Handle 'value' or 'span' as alias for 'text'
            if "text" not in data:
                if "value" in data:
                    data["text"] = data["value"]
                elif "span" in data:
                    data["text"] = data["span"]
        return data

class RelationOut(BaseModel):
    """Canonical schema for relation extraction output."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    subject: str = Field(..., description="Source entity text")
    object: str = Field(..., description="Target entity text")
    predicate: str = Field(..., description="Relation type or predicate")
    confidence: float = Field(0.9, description="Confidence score between 0 and 1")
    subject_id: Optional[str] = Field(None, description="Exact source entity mention identifier")
    object_id: Optional[str] = Field(None, description="Exact target entity mention identifier")
    evidence: Optional[str] = Field(None, description="Exact supporting source quote")
    evidence_occurrence: Optional[int] = Field(None, ge=0, description="Zero-based evidence quote occurrence")
    qualifiers: dict = Field(default_factory=dict, description="Grounded relation qualifiers")
    metadata: dict = Field(default_factory=dict, description="Additional metadata including provenance")

    @model_validator(mode="before")
    @classmethod
    def handle_aliases(cls, data):
        if isinstance(data, dict):
            if "subject" not in data and "source" in data:
                data["subject"] = data["source"]
            if "object" not in data and "target" in data:
                data["object"] = data["target"]
            if "predicate" not in data and "label" in data:
                data["predicate"] = data["label"]
        return data

    @property
    def source(self):
        return self.subject
        
    @property
    def target(self):
        return self.object
        
    @property
    def label(self):
        return self.predicate

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, v):
        if isinstance(v, str):
            try:
                v = float(v)
            except ValueError:
                return 0.9
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return 0.9

class TripletOut(BaseModel):
    """Canonical schema for triplet extraction output."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    subject: str = Field(..., description="Subject of the triplet")
    predicate: str = Field(..., description="Predicate or relation")
    object: str = Field(..., description="Object of the triplet")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score between 0 and 1")
    # Provenance is constructed by the extractor, not generated by the model.
    metadata: SkipJsonSchema[dict] = Field(default_factory=dict)

class EntitiesResponse(BaseModel):
    """Wrapper for list of entities."""
    entities: List[EntityOut] = Field(default_factory=list)


class GroundedEntityOut(EntityOut):
    """Entity output whose exact source occurrence is mandatory."""
    occurrence: int = Field(..., ge=0, description="Zero-based exact text occurrence")


class GroundedEntitiesResponse(BaseModel):
    """Strict source-grounded entity extraction response."""
    entities: List[dict[str, Any] | GroundedEntityOut | Any] = Field(...)


class RelationsResponse(BaseModel):
    """Wrapper for list of relations."""
    relations: List[RelationOut] = Field(default_factory=list)


class GroundedRelationOut(BaseModel):
    """Strict relation output keyed by source mention IDs.

    Endpoint text is derived from the supplied mention IDs by the grounded
    parser, so the model does not have to generate the same endpoint twice.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    predicate: str = Field(..., description="Relation type or predicate")
    confidence: float = Field(0.9, description="Confidence score between 0 and 1")
    subject_id: str = Field(..., description="Exact source entity mention identifier")
    object_id: str = Field(..., description="Exact target entity mention identifier")
    evidence: str = Field(..., description="Exact supporting source quote")
    evidence_occurrence: int = Field(..., ge=0, description="Zero-based evidence quote occurrence")
    qualifiers: dict = Field(..., description="Grounded relation qualifiers")
    supporting_refs: List[str] = Field(default_factory=list, description="Exact supplied structural source references supporting this relation")

    @field_validator("qualifiers", mode="before")
    @classmethod
    def unwrap_singleton_qualifiers(cls, value):
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
            return value[0]
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, v):
        if isinstance(v, str):
            try:
                v = float(v)
            except ValueError:
                return 0.9
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return 0.9


class GroundedRelationsResponse(BaseModel):
    """Strict source-grounded relation extraction response."""
    # Keep the envelope typed while retaining raw siblings for independent
    # validation in the grounded parser.
    relations: List[dict[str, Any] | GroundedRelationOut | Any] = Field(
        ..., description="Relation candidates validated independently by the grounded parser"
    )


class GroundedQualifiersWire(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polarity: Literal["positive", "negative"]
    condition: Optional[str] = None
    time: Optional[str] = None
    unit: Optional[str] = None
    value: Optional[str] = None


class GroundedRelationWire(BaseModel):
    model_config = ConfigDict(extra="forbid")
    predicate: str
    confidence: float = Field(ge=0, le=1)
    subject_id: str
    object_id: str
    evidence: str
    evidence_occurrence: int = Field(ge=0)
    qualifiers: GroundedQualifiersWire
    supporting_refs: List[str]


class GroundedRelationsWire(BaseModel):
    """Closed transport contract; native grounding still validates each candidate."""
    model_config = ConfigDict(extra="forbid")
    relations: List[GroundedRelationWire]


def grounded_entities_wire(specification=None):
    """Derive the closed wire schema from the existing extraction specification."""
    types = {"string": str, "number": float, "integer": int, "boolean": bool,
             "string_list": List[str], "number_list": List[float]}
    entities = []
    for index, entity_type in enumerate(specification.entity_types if specification else [None]):
        fields = {}
        for name, attribute in (entity_type.attributes.items() if entity_type else []):
            value_type = types[attribute.type]
            fields[name] = (value_type if attribute.required else Optional[value_type],
                            Field(... if attribute.required else None, description=attribute.description))
        attributes = create_model(f"GroundedAttributes{index}", __config__=ConfigDict(extra="forbid"), **fields)
        entities.append(create_model(f"GroundedEntityWire{index}", __config__=ConfigDict(extra="forbid"),
            text=(str, ...), label=(Literal[entity_type.name] if entity_type else str, ...),
            occurrence=(int, Field(ge=0)), confidence=(float, Field(ge=0, le=1)),
            attributes=(attributes, ...), identity_profile=(Optional[IdentityProfileOut], None)))
    item = entities[0] if len(entities) == 1 else Union[tuple(entities)]
    return create_model("GroundedEntitiesWire", __config__=ConfigDict(extra="forbid"), entities=(List[item], ...))


class TripletsResponse(BaseModel):
    """Wrapper for list of triplets."""
    triplets: List[TripletOut] = Field(default_factory=list)


class RelationWithTemporalOut(BaseModel):
    """Schema for relation extraction output with temporal validity bounds."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    subject: str = Field(..., description="Source entity text")
    object: str = Field(..., description="Target entity text")
    predicate: str = Field(..., description="Relation type or predicate")
    confidence: float = Field(0.9, description="Confidence score between 0 and 1")
    metadata: dict = Field(default_factory=dict, description="Additional metadata including provenance")

    valid_from: Optional[str] = Field(
        None,
        description="ISO 8601 date or natural-language phrase for when this relation became valid. Null if no temporal signal in text.",
    )
    valid_until: Optional[str] = Field(
        None,
        description="ISO 8601 date or phrase for when this relation ceased to be valid. Null if open-ended or not stated.",
    )
    temporal_confidence: float = Field(
        0.0,
        description="Confidence that temporal information was present and correctly extracted. 0.0 if no temporal signal.",
    )
    temporal_source_text: Optional[str] = Field(
        None,
        description="Exact verbatim substring from the source text containing the temporal signal. Null when temporal_confidence is 0.0.",
    )

    @model_validator(mode="before")
    @classmethod
    def handle_aliases(cls, data):
        if isinstance(data, dict):
            if "subject" not in data and "source" in data:
                data["subject"] = data["source"]
            if "object" not in data and "target" in data:
                data["object"] = data["target"]
            if "predicate" not in data and "label" in data:
                data["predicate"] = data["label"]
        return data

    @field_validator("confidence", "temporal_confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, v):
        if isinstance(v, str):
            try:
                v = float(v)
            except ValueError:
                return 0.0
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return 0.0


class RelationsWithTemporalResponse(BaseModel):
    """Wrapper for list of relations with temporal validity bounds."""
    relations: List[RelationWithTemporalOut] = Field(default_factory=list)
