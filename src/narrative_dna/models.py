"""Strict Pydantic contracts for JSON-first narrative DNA artifacts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictBaseModel(BaseModel):
    """Base model that rejects undeclared JSON fields."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
        use_enum_values=True,
    )


class FunctionCode(str, Enum):
    ASSERTION = "A"
    CLAIM = "K"
    OPINION = "O"
    DEFINITION = "F"
    CAUSAL_EXPLANATION = "Y"
    EVIDENCE = "D"
    QUOTE = "Q"
    QUESTION = "P"
    ANSWER = "R"
    EXAMPLE = "E"
    STORY = "H"
    ANALOGY = "G"
    CONTRAST = "C"
    REFUTATION = "B"
    RISK = "X"
    TRANSITION = "T"
    METACOMMENTARY = "M"
    LIST = "L"
    CONCLUSION = "Z"
    SOLUTION = "S"
    INSTRUCTION = "I"
    UTILITY = "U"
    VIEWER_CALL = "V"
    UNCLASSIFIED = "N"


class Certainty(str, Enum):
    NONE = "none"
    STRONG = "strong"
    TENTATIVE = "tentative"
    UNCERTAIN = "uncertain"


class EmotionCode(str, Enum):
    NEUTRAL = "N"
    JOY_ENTHUSIASM = "A"
    LOVE_ADMIRATION = "L"
    CALM_TRUST = "C"
    SURPRISE = "S"
    ANGER_INDIGNATION = "E"
    FEAR_ANXIETY = "M"
    SADNESS_DISAPPOINTMENT = "T"
    DISGUST_CONTEMPT = "D"
    FRUSTRATION_RESIGNATION = "F"
    IRONY_SARCASM = "I"


class Stance(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    NEUTRAL = "neutral"


class SourceType(str, Enum):
    TXT = "txt"
    JSON = "json"
    JSONL = "jsonl"
    UNKNOWN = "unknown"


class Method(str, Enum):
    NONE = "none"
    HEURISTIC = "heuristic"
    LLM = "llm"
    ADJUDICATED = "adjudicated"
    SYNTHETIC = "synthetic"
    DERIVED = "derived"
    MANUAL = "manual"


class RelationType(str, Enum):
    ANS = "ANS"
    SUP = "SUP"
    EXPL = "EXPL"
    ELAB = "ELAB"
    EXMP = "EXMP"
    ANLG = "ANLG"
    CONTR = "CONTR"
    REFUT = "REFUT"
    RISK = "RISK"
    SOLV = "SOLV"
    SEQ = "SEQ"
    SUM = "SUM"
    CALL = "CALL"
    CAUSE = "CAUSE"
    COND = "COND"


class ValidatorSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ReviewStatus(str, Enum):
    ACCEPTED = "accepted"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"
    PENDING = "pending"


class SyntheticDecision(str, Enum):
    ACCEPT = "accept"
    REVISE = "revise"
    REJECT = "reject"
    NEEDS_REVIEW = "needs_review"


class SyntheticGoldStatus(str, Enum):
    HIGH_CONFIDENCE = "synthetic_gold_high_confidence"
    MEDIUM_CONFIDENCE = "synthetic_gold_medium_confidence"
    REJECTED = "synthetic_gold_rejected"


class ConflictExplanationType(str, Enum):
    LIKELY_INCONSISTENCY = "likely_inconsistency"
    CONTEXT_EXPLAINS_DIFFERENCE = "context_explains_difference"
    ALLOWED_BY_TAXONOMY = "allowed_by_taxonomy"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class GoldType(str, Enum):
    HUMAN_GOLD = "human_gold"
    SYNTHETIC_HIGH_CONFIDENCE = "synthetic_gold_high_confidence"
    SYNTHETIC_MEDIUM_CONFIDENCE = "synthetic_gold_medium_confidence"
    SYNTHETIC_REJECTED = "synthetic_gold_rejected"


class Span(StrictBaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> Span:
        if self.end < self.start:
            raise ValueError("span end must be greater than or equal to start")
        return self


class EvidenceSpan(StrictBaseModel):
    text: str = Field(min_length=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    source: str | None = None

    @model_validator(mode="after")
    def validate_span_order(self) -> EvidenceSpan:
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError("char_end must be greater than or equal to char_start")
        if self.start_ms is not None and self.end_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return self


class RejectedLabel(StrictBaseModel):
    label: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ValidatorFlag(StrictBaseModel):
    rule_id: str = Field(min_length=1)
    severity: ValidatorSeverity
    message: str = Field(min_length=1)
    field: str | None = None


class InheritedFunction(StrictBaseModel):
    function: FunctionCode
    inherited_from: FunctionCode
    reason: str = Field(min_length=1)


class HeuristicCandidate(StrictBaseModel):
    label: FunctionCode
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class LLMVote(StrictBaseModel):
    model: str = Field(min_length=1)
    label: FunctionCode
    confidence: float = Field(ge=0, le=1)
    rationale: str | None = None


class SegmentationInfo(StrictBaseModel):
    strategy: str = Field(min_length=1)
    unit_count: int = Field(ge=0)
    notes: list[str] = Field(default_factory=list)


class ProjectRunManifest(StrictBaseModel):
    run_id: str = Field(min_length=1)
    created_at_utc: datetime
    project_version: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    validator_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    input_dir: str = Field(min_length=1)
    output_dir: str = Field(min_length=1)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    llm_config_snapshot: dict[str, Any] = Field(default_factory=dict)
    git_commit: str | None = None


class TaxonomyDefinition(StrictBaseModel):
    taxonomy_version: str = Field(min_length=1)
    reserved_stable_version: str | None = None
    function_codes: list[FunctionCode] = Field(min_length=1)
    relation_types: list[RelationType] = Field(min_length=1)
    notes: str | None = None

    @field_validator("function_codes", "relation_types")
    @classmethod
    def reject_duplicate_taxonomy_items(cls, values: list[Enum]) -> list[Enum]:
        if len(values) != len(set(values)):
            raise ValueError("taxonomy lists must not contain duplicates")
        return values


class NarrativeUnit(StrictBaseModel):
    document_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    sequence_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    previous_unit_id: str | None = None
    next_unit_id: str | None = None
    functions: list[FunctionCode] = Field(min_length=1)
    primary_function: FunctionCode
    secondary_functions: list[FunctionCode] = Field(default_factory=list)
    inherited_functions: list[InheritedFunction] = Field(default_factory=list)
    certainty: Certainty
    emotion_expressed: EmotionCode
    emotion_intensity: int = Field(ge=0, le=3)
    emotions_mentioned: list[EmotionCode] = Field(default_factory=list)
    stance: Stance
    target: str | None = None
    speech_act: str | None = None
    logic: dict[str, Any] | None = None
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    rejected_labels: list[RejectedLabel] = Field(default_factory=list)
    validator_flags: list[ValidatorFlag] = Field(default_factory=list)
    heuristic_candidates: list[HeuristicCandidate] = Field(default_factory=list)
    llm_votes: list[LLMVote] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    method: Method
    needs_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.PENDING
    final_notation: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    validator_version: str = Field(min_length=1)

    @field_validator("functions", "secondary_functions")
    @classmethod
    def reject_duplicate_functions(cls, functions: list[FunctionCode]) -> list[FunctionCode]:
        if len(functions) != len(set(functions)):
            raise ValueError("function lists must not contain duplicates")
        return functions

    @model_validator(mode="after")
    def validate_unit_consistency(self) -> NarrativeUnit:
        if FunctionCode.UNCLASSIFIED in self.functions and len(self.functions) > 1:
            raise ValueError("N must not coexist with other functions")
        if self.primary_function not in self.functions:
            raise ValueError("primary_function must be present in functions")
        if self.primary_function in self.secondary_functions:
            raise ValueError("primary_function must not appear in secondary_functions")
        if self.start_ms is not None and self.end_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError("char_end must be greater than or equal to char_start")
        return self


class NarrativeRelation(StrictBaseModel):
    run_id: str = Field(default="run_unknown", min_length=1)
    relation_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_unit_id: str = Field(min_length=1)
    target_unit_id: str = Field(min_length=1)
    relation_type: RelationType
    confidence: float = Field(ge=0, le=1)
    method: Method
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    rejected_relation_types: list[RelationType] = Field(default_factory=list)
    validator_flags: list[ValidatorFlag] = Field(default_factory=list)
    needs_review: bool = False
    taxonomy_version_effective: str = Field(default="v1_0", min_length=1)
    prompt_version_effective: str = Field(default="v1_0", min_length=1)
    validator_version_effective: str = Field(default="v1_0", min_length=1)

    @model_validator(mode="after")
    def validate_relation_endpoints(self) -> NarrativeRelation:
        if self.source_unit_id == self.target_unit_id:
            raise ValueError("source_unit_id and target_unit_id must differ")
        return self


class NarrativeChain(StrictBaseModel):
    run_id: str = Field(default="run_unknown", min_length=1)
    chain_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    chain_type: str = Field(min_length=1)
    unit_ids: list[str] = Field(min_length=1)
    relation_ids: list[str] = Field(default_factory=list)
    notation_sequence: list[str] = Field(default_factory=list)
    start_unit_id: str = Field(min_length=1)
    end_unit_id: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    narrative_function: str | None = None
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    evidence_summary: str | None = None
    validator_flags: list[ValidatorFlag] = Field(default_factory=list)
    needs_review: bool = False
    taxonomy_version_effective: str = Field(default="v1_0", min_length=1)
    prompt_version_effective: str = Field(default="v1_0", min_length=1)
    validator_version_effective: str = Field(default="v1_0", min_length=1)

    @model_validator(mode="after")
    def validate_chain_boundaries(self) -> NarrativeChain:
        if self.start_unit_id not in self.unit_ids:
            raise ValueError("start_unit_id must be present in unit_ids")
        if self.end_unit_id not in self.unit_ids:
            raise ValueError("end_unit_id must be present in unit_ids")
        return self


class NarrativeDocument(StrictBaseModel):
    document_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_type: SourceType
    language: str = Field(min_length=2, max_length=16)
    metadata: dict[str, Any] = Field(default_factory=dict)
    segmentation: SegmentationInfo
    units: list[NarrativeUnit] = Field(default_factory=list)
    relations: list[NarrativeRelation] = Field(default_factory=list)
    chains: list[NarrativeChain] = Field(default_factory=list)
    document_metrics: dict[str, Any] = Field(default_factory=dict)
    audit_summary: dict[str, Any] = Field(default_factory=dict)


class SimilarityConflict(StrictBaseModel):
    conflict_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    unit_id_a: str = Field(min_length=1)
    unit_id_b: str = Field(min_length=1)
    similarity: float = Field(ge=0, le=1)
    notation_distance: float = Field(default=0, ge=0, le=1)
    conflict_score: float = Field(default=0, ge=0, le=1)
    conflict_explanation_type: ConflictExplanationType = ConflictExplanationType.NEEDS_HUMAN_REVIEW
    differing_fields: list[str] = Field(min_length=1)
    explanation: str | None = None
    needs_review: bool = True


class ClusterInstability(StrictBaseModel):
    cluster_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    unit_ids: list[str] = Field(min_length=1)
    instability_score: float = Field(ge=0, le=1)
    dominant_labels: list[FunctionCode] = Field(default_factory=list)
    conflicting_labels: list[FunctionCode] = Field(default_factory=list)
    needs_review: bool = True


class ValidatorSummary(StrictBaseModel):
    run_id: str = Field(min_length=1)
    validator_version: str = Field(min_length=1)
    total_units: int = Field(ge=0)
    total_flags: int = Field(ge=0)
    errors: int = Field(ge=0)
    warnings: int = Field(ge=0)
    infos: int = Field(ge=0)
    flags_by_rule: dict[str, int] = Field(default_factory=dict)


class EvaluationMetrics(StrictBaseModel):
    run_id: str = Field(min_length=1)
    gold_path: str = Field(min_length=1)
    total_gold_units: int = Field(default=0, ge=0)
    total_predicted_units: int = Field(default=0, ge=0)
    matched_units: int = Field(default=0, ge=0)
    missing_predictions: int = Field(default=0, ge=0)
    unexpected_predictions: int = Field(default=0, ge=0)
    functions_exact_match: float = Field(ge=0, le=1)
    primary_function_accuracy: float = Field(ge=0, le=1)
    multilabel_jaccard: float = Field(ge=0, le=1)
    micro_f1: float = Field(ge=0, le=1)
    macro_f1: float = Field(ge=0, le=1)
    emotion_expressed_accuracy: float = Field(default=0, ge=0, le=1)
    emotion_intensity_mae: float = Field(default=0, ge=0)
    stance_accuracy: float = Field(default=0, ge=0, le=1)
    certainty_accuracy: float = Field(default=0, ge=0, le=1)
    overlabeling_rate: float = Field(default=0, ge=0, le=1)
    n_rate: float = Field(default=0, ge=0, le=1)
    validator_violation_rate: float = Field(ge=0, le=1)
    needs_review_rate: float = Field(ge=0, le=1)
    similarity_conflict_rate: float = Field(ge=0, le=1)
    relation_precision_recall_f1: float = Field(default=0, ge=0, le=1)
    regression_pass_rate: float = Field(default=0, ge=0, le=1)
    outputs: dict[str, str] = Field(default_factory=dict)
    taxonomy_version_effective: str = Field(default="v1_0", min_length=1)
    prompt_version_effective: str = Field(default="v1_0", min_length=1)
    validator_version_effective: str = Field(default="v1_0", min_length=1)


class AuditReport(StrictBaseModel):
    run_id: str = Field(min_length=1)
    summary: ValidatorSummary
    validator_flags: list[ValidatorFlag] = Field(default_factory=list)
    similarity_conflicts: list[SimilarityConflict] = Field(default_factory=list)
    cluster_instabilities: list[ClusterInstability] = Field(default_factory=list)
    taxonomy_version_effective: str = Field(min_length=1)
    prompt_version_effective: str = Field(min_length=1)
    validator_version_effective: str = Field(min_length=1)


class SyntheticReviewItem(StrictBaseModel):
    review_item_id: str = Field(min_length=1)
    item_type: Literal["unit", "similar_pair", "minimal_pair", "relation", "chain"]
    document_id: str = Field(min_length=1)
    unit_id: str | None = None
    unit_ids: list[str] = Field(default_factory=list)
    text: str = Field(min_length=1)
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)
    current_prediction_json: dict[str, Any] = Field(default_factory=dict)
    current_notation: str | None = None
    relevant_taxonomy_rules: list[dict[str, Any]] = Field(default_factory=list)
    relevant_decision_tree: str = ""
    relevant_minimal_pairs: list[dict[str, Any]] = Field(default_factory=list)
    validator_flags: list[dict[str, Any]] = Field(default_factory=list)
    similarity_conflict_info: dict[str, Any] | None = None
    expected_difficulty: Literal["easy", "medium", "hard", "adversarial"]
    review_goal: Literal["validate", "find_alternative", "resolve_confusion", "test_boundary"]
    taxonomy_version_effective: str = Field(min_length=1)
    prompt_version_effective: str = Field(min_length=1)
    validator_version_effective: str = Field(min_length=1)


class SyntheticReviewManifest(StrictBaseModel):
    run_id: str = Field(min_length=1)
    item_count: int = Field(ge=0)
    counts_by_item_type: dict[str, int] = Field(default_factory=dict)
    counts_by_review_goal: dict[str, int] = Field(default_factory=dict)
    source_documents: int = Field(ge=0)
    source_units: int = Field(ge=0)
    source_similarity_conflicts: int = Field(ge=0)
    taxonomy_version_effective: str = Field(min_length=1)
    prompt_version_effective: str = Field(min_length=1)
    validator_version_effective: str = Field(min_length=1)


class SyntheticReviewerOutput(StrictBaseModel):
    run_id: str = Field(default="run_unknown", min_length=1)
    review_item_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    decision: SyntheticDecision
    proposed_unit: NarrativeUnit | None = None
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1)
    validator_flags: list[ValidatorFlag] = Field(default_factory=list)
    taxonomy_version_effective: str = Field(default="v1_0", min_length=1)
    prompt_version_effective: str = Field(default="v1_0", min_length=1)
    validator_version_effective: str = Field(default="v1_0", min_length=1)


class SyntheticAggregatedReview(StrictBaseModel):
    run_id: str = Field(default="run_unknown", min_length=1)
    review_item_id: str = Field(min_length=1)
    decisions: list[SyntheticReviewerOutput] = Field(min_length=1)
    aggregate_decision: SyntheticDecision
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1)
    needs_final_adjudication: bool
    taxonomy_version_effective: str = Field(default="v1_0", min_length=1)
    prompt_version_effective: str = Field(default="v1_0", min_length=1)
    validator_version_effective: str = Field(default="v1_0", min_length=1)


class SyntheticFinalAdjudication(StrictBaseModel):
    run_id: str = Field(default="run_unknown", min_length=1)
    review_item_id: str = Field(min_length=1)
    final_decision: SyntheticDecision
    gold_status: SyntheticGoldStatus | None = None
    selected_unit: NarrativeUnit | None = None
    reliability_score: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1)
    validator_flags: list[ValidatorFlag] = Field(default_factory=list)
    needs_human_review: bool
    taxonomy_version_effective: str = Field(default="v1_0", min_length=1)
    prompt_version_effective: str = Field(default="v1_0", min_length=1)
    validator_version_effective: str = Field(default="v1_0", min_length=1)


class SyntheticGoldCandidate(StrictBaseModel):
    run_id: str = Field(default="run_unknown", min_length=1)
    candidate_id: str = Field(min_length=1)
    review_item_id: str = Field(min_length=1)
    status: SyntheticGoldStatus
    unit: NarrativeUnit
    reliability_score: float = Field(ge=0, le=1)
    promotion_notes: str = Field(min_length=1)
    taxonomy_version_effective: str = Field(default="v1_0", min_length=1)
    prompt_version_effective: str = Field(default="v1_0", min_length=1)
    validator_version_effective: str = Field(default="v1_0", min_length=1)


class SyntheticReviewReport(StrictBaseModel):
    run_id: str = Field(min_length=1)
    total_review_items: int = Field(ge=0)
    reviewer_profile_count: int = Field(ge=0)
    reviewer_output_count: int = Field(ge=0)
    reviewer_failure_count: int = Field(ge=0)
    aggregated_count: int = Field(ge=0)
    final_adjudication_count: int = Field(ge=0)
    synthetic_gold_candidate_count: int = Field(ge=0)
    decisions_by_type: dict[str, int] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    taxonomy_version_effective: str = Field(min_length=1)
    prompt_version_effective: str = Field(min_length=1)
    validator_version_effective: str = Field(min_length=1)


class GoldRecord(StrictBaseModel):
    gold_id: str = Field(min_length=1)
    gold_type: GoldType
    unit: NarrativeUnit
    provenance: str = Field(min_length=1)
    taxonomy_version_effective: str = Field(min_length=1)
    prompt_version_effective: str = Field(min_length=1)
    validator_version_effective: str = Field(min_length=1)


class SyntheticReliabilityMetrics(StrictBaseModel):
    run_id: str = Field(min_length=1)
    total_review_items: int = Field(ge=0)
    reviewer_output_count: int = Field(default=0, ge=0)
    aggregated_review_count: int = Field(default=0, ge=0)
    final_adjudication_count: int = Field(default=0, ge=0)
    synthetic_gold_candidate_count: int = Field(default=0, ge=0)
    high_confidence_count: int = Field(ge=0)
    medium_confidence_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    needs_review_count: int = Field(default=0, ge=0)
    needs_human_review_count: int = Field(default=0, ge=0)
    inter_reviewer_agreement: float = Field(ge=0, le=1)
    adjudicator_agreement: float = Field(ge=0, le=1)
    average_reviewer_confidence: float = Field(default=0, ge=0, le=1)
    average_aggregate_confidence: float = Field(default=0, ge=0, le=1)
    average_final_reliability: float = Field(default=0, ge=0, le=1)
    regression_eligible_count: int = Field(default=0, ge=0)
    regression_eligible_rate: float = Field(default=0, ge=0, le=1)
    reviewer_decisions_by_type: dict[str, int] = Field(default_factory=dict)
    aggregate_decisions_by_type: dict[str, int] = Field(default_factory=dict)
    final_decisions_by_type: dict[str, int] = Field(default_factory=dict)
    gold_status_counts: dict[str, int] = Field(default_factory=dict)
    agreement_by_item: dict[str, float] = Field(default_factory=dict)
    reliability_by_item: dict[str, float] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    taxonomy_version_effective: str = Field(default="v1_0", min_length=1)
    prompt_version_effective: str = Field(default="v1_0", min_length=1)
    validator_version_effective: str = Field(default="v1_0", min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> SyntheticReliabilityMetrics:
        total = self.high_confidence_count + self.medium_confidence_count + self.rejected_count
        if total > self.total_review_items:
            raise ValueError("confidence bucket counts must not exceed total_review_items")
        return self


SCHEMA_MODELS: dict[str, type[StrictBaseModel]] = {
    "run_manifest.schema.json": ProjectRunManifest,
    "taxonomy.schema.json": TaxonomyDefinition,
    "document.schema.json": NarrativeDocument,
    "unit.schema.json": NarrativeUnit,
    "relation.schema.json": NarrativeRelation,
    "chain.schema.json": NarrativeChain,
    "audit.schema.json": AuditReport,
    "gold.schema.json": GoldRecord,
    "similarity_conflict.schema.json": SimilarityConflict,
    "cluster_instability.schema.json": ClusterInstability,
    "validator_summary.schema.json": ValidatorSummary,
    "evaluation_metrics.schema.json": EvaluationMetrics,
    "synthetic_review_item.schema.json": SyntheticReviewItem,
    "synthetic_review_manifest.schema.json": SyntheticReviewManifest,
    "synthetic_reviewer_output.schema.json": SyntheticReviewerOutput,
    "synthetic_aggregated_review.schema.json": SyntheticAggregatedReview,
    "synthetic_final_adjudication.schema.json": SyntheticFinalAdjudication,
    "synthetic_gold_candidate.schema.json": SyntheticGoldCandidate,
    "synthetic_review_report.schema.json": SyntheticReviewReport,
    "synthetic_reliability_metrics.schema.json": SyntheticReliabilityMetrics,
}
