"""Typed contracts shared by planning, execution, validation, and the UI."""

import math
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


class PlanFilter(BaseModel):
    dataset: str = Field(min_length=1)
    column: str = Field(min_length=1)
    operator: Literal[
        "eq",
        "ne",
        "gt",
        "in",
        "not_in",
        "between",
        "gte",
        "lt",
        "lte",
        "is_null",
        "not_null",
    ]
    value: Any = None


class MetricOperand(BaseModel):
    description: str = Field(min_length=1)
    aggregation: str = Field(min_length=1)
    filters: List[PlanFilter] = Field(default_factory=list)


class PlannedMetric(BaseModel):
    key: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    label: str = Field(min_length=1)
    metric_id: Optional[str] = None
    metric_type: Literal[
        "count",
        "sum",
        "average",
        "rate",
        "share",
        "ratio",
        "difference",
        "other",
    ]
    definition: str = Field(min_length=1)
    calculation: str = Field(min_length=1)
    numerator: Optional[MetricOperand] = None
    denominator: Optional[MetricOperand] = None
    filters: List[PlanFilter] = Field(default_factory=list)
    value_scale: Literal["raw", "fraction", "percent"] = "raw"


class JoinRequirement(BaseModel):
    left_dataset: str = Field(min_length=1)
    right_dataset: str = Field(min_length=1)
    join_keys: List[str] = Field(min_length=1)
    how: Literal["inner", "left", "right", "outer"]
    left_grain: str = Field(min_length=1)
    right_grain: str = Field(min_length=1)
    relationship: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"]
    pre_join_aggregation: Optional[str] = None


class MetricCandidateRejection(BaseModel):
    metric_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    superseded_by: Optional[str] = None


class AnalysisPlan(BaseModel):
    """Planner contract for business semantics; readiness is checked separately."""

    intent: Literal[
        "lookup",
        "filtering",
        "aggregation",
        "ranking",
        "trend",
        "cohort",
        "data_quality",
        "metric_diagnostic",
        "modeling",
    ]
    analysis_scope: Optional[str] = None
    entity_grain: Optional[str] = None
    metric_ids: List[str] = Field(default_factory=list)
    metrics: List[PlannedMetric] = Field(default_factory=list)
    rejected_metrics: List[MetricCandidateRejection] = Field(default_factory=list)
    required_columns: List[str] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list)
    filters: List[PlanFilter] = Field(default_factory=list)
    # Kept for compatibility with persisted metadata and older downstream readers.
    # V1.5 puts calculation semantics on each PlannedMetric instead.
    aggregation: Optional[str] = None
    time_field: Optional[str] = None
    time_grain: Optional[Literal["day", "week", "month", "quarter", "year"]] = None
    joins: List[JoinRequirement] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


class PlanCompletenessIssue(BaseModel):
    code: str
    field: str
    message: str


class PlanCompletenessReport(BaseModel):
    schema_valid: bool = True
    ready_for_code_generation: bool
    valid_clarification: bool = False
    issues: List[PlanCompletenessIssue] = Field(default_factory=list)


class PlanNormalizationAction(BaseModel):
    code: str
    field: str
    before: Any = None
    after: Any = None


class PlanNormalizationResult(BaseModel):
    normalized_payload: Dict[str, Any] = Field(default_factory=dict)
    actions: List[PlanNormalizationAction] = Field(default_factory=list)
    unresolved_issues: List[PlanCompletenessIssue] = Field(default_factory=list)


class PlanGenerationOutcome(BaseModel):
    """Planner result that preserves partial semantics when no canonical plan exists."""

    plan: Optional[AnalysisPlan] = None
    raw_payload: Optional[Dict[str, Any]] = None
    normalized_partial_payload: Dict[str, Any] = Field(default_factory=dict)
    normalization_actions: List[PlanNormalizationAction] = Field(default_factory=list)
    validation_errors: List[Dict[str, Any]] = Field(default_factory=list)
    unresolved_issues: List[PlanCompletenessIssue] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


ScalarValue = Union[float, int, str, bool]


class VisualizationDataset(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    rows: List[Dict[str, Any]] = Field(default_factory=list, max_length=500)


class VisualizationSpec(BaseModel):
    type: Literal["bar", "line", "pie", "scatter", "histogram", "box", "heatmap", "table"]
    title: str = Field(min_length=1, max_length=180)
    dataset_id: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=400)
    x: Optional[str] = None
    y: Optional[str] = None
    value: Optional[str] = None
    series: Optional[str] = None
    lower: Optional[str] = None
    q1: Optional[str] = None
    median: Optional[str] = None
    q3: Optional[str] = None
    upper: Optional[str] = None

    @model_validator(mode="after")
    def validate_required_encodings(self) -> "VisualizationSpec":
        if self.type in {"bar", "line", "pie", "scatter", "histogram"} and not (self.x and self.y):
            raise ValueError(f"{self.type} visualizations require x and y fields")
        if self.type == "heatmap" and not (self.x and self.y and self.value):
            raise ValueError("heatmap visualizations require x, y, and value fields")
        if self.type == "box" and not all((self.x, self.lower, self.q1, self.median, self.q3, self.upper)):
            raise ValueError("box visualizations require x, lower, q1, median, q3, and upper fields")
        return self


class ResultEvidence(BaseModel):
    """Machine-readable evidence tied to a planned metric when one exists."""

    plan_metric_key: Optional[str] = Field(default=None, min_length=1)
    kind: Literal["scalar", "dataset"]
    value: Optional[ScalarValue] = None
    value_scale: Optional[Literal["raw", "fraction", "percent"]] = None
    unit: Optional[str] = None
    dataset_id: Optional[str] = Field(default=None, min_length=1)
    value_field: Optional[str] = Field(default=None, min_length=1)
    dimension_fields: List[str] = Field(default_factory=list)
    coordinates: Dict[str, ScalarValue] = Field(default_factory=dict)
    label: Optional[str] = None

    @model_validator(mode="after")
    def validate_evidence_shape(self) -> "ResultEvidence":
        if isinstance(self.value, (int, float)) and not isinstance(self.value, bool):
            if not math.isfinite(float(self.value)):
                raise ValueError("evidence scalar value must be finite")

        if self.kind == "scalar":
            if self.value is None:
                raise ValueError("scalar evidence requires value")
            if self.dataset_id or self.value_field or self.dimension_fields:
                raise ValueError("scalar evidence cannot declare dataset fields")
        else:
            if self.value is not None:
                raise ValueError("dataset evidence value must be null")
            if not self.dataset_id or not self.value_field:
                raise ValueError("dataset evidence requires dataset_id and value_field")
        return self


class AnalysisResult(BaseModel):
    answer_type: Literal["number", "table", "text"]
    primary_value: Optional[ScalarValue] = None
    unit: Optional[str] = None
    summary: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    columns_used: List[str] = Field(default_factory=list)
    metric_id: Optional[str] = None
    assumptions: List[str] = Field(default_factory=list)
    insights: List[str] = Field(default_factory=list, max_length=8)
    datasets: List[VisualizationDataset] = Field(default_factory=list, max_length=12)
    visualizations: List[VisualizationSpec] = Field(default_factory=list, max_length=12)
    evidence: List[ResultEvidence] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_visualization_contract(cls, value: Any) -> Any:
        """Repair common, unambiguous omissions in LLM-authored chart specs."""
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        datasets = [dict(item) for item in payload.get("datasets", []) if isinstance(item, dict)]
        visuals = [dict(item) for item in payload.get("visualizations", []) if isinstance(item, dict)]
        evidence_items: List[Dict[str, Any]] = []
        for raw_item in payload.get("evidence", []):
            if not isinstance(raw_item, dict):
                continue
            item = dict(raw_item)
            for field in ("plan_metric_key", "value_scale", "unit", "dataset_id", "value_field", "label"):
                if item.get(field) == "":
                    item[field] = None
            if item.get("kind") == "scalar":
                item["dataset_id"] = None
                item["value_field"] = None
                item["dimension_fields"] = []
            evidence_items.append(item)
        payload["evidence"] = evidence_items

        # Models sometimes emit every intermediate distribution as a dataset even
        # though only a few are visualized. Keep the referenced evidence when the
        # bounded transport contract would otherwise be exceeded.
        if len(datasets) > 12 and visuals:
            referenced = {item.get("dataset_id") for item in visuals}
            referenced.update(
                item.get("dataset_id")
                for item in evidence_items
                if isinstance(item, dict) and item.get("kind") == "dataset"
            )
            datasets = [item for item in datasets if item.get("id") in referenced]

        rows_by_id = {
            item.get("id"): item.get("rows", [])
            for item in datasets
            if item.get("id")
        }
        for visual in visuals:
            rows = rows_by_id.get(visual.get("dataset_id"), [])
            fields = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
            numeric_fields = [
                field for field in fields
                if any(isinstance(row.get(field), (int, float)) and not isinstance(row.get(field), bool) for row in rows)
            ]
            chart_type = visual.get("type")

            if chart_type == "heatmap":
                for field in ("x", "y", "value"):
                    if not visual.get(field) and field in fields:
                        visual[field] = field
            elif chart_type == "box":
                for field in ("lower", "q1", "median", "q3", "upper"):
                    if not visual.get(field) and field in fields:
                        visual[field] = field
                if not visual.get("x"):
                    visual["x"] = next(
                        (field for field in fields if field not in {"lower", "q1", "median", "q3", "upper"}),
                        None,
                    )
            elif chart_type == "histogram":
                if not visual.get("x"):
                    visual["x"] = next((field for field in ("bin", "bin_start", "range") if field in fields), None)
                if not visual.get("y"):
                    visual["y"] = next((field for field in ("count", "frequency", "density") if field in fields), None)
            elif chart_type in {"bar", "line", "pie", "scatter"}:
                if not visual.get("x"):
                    visual["x"] = next((field for field in fields if field not in numeric_fields), fields[0] if fields else None)
                if not visual.get("y"):
                    visual["y"] = next((field for field in numeric_fields if field != visual.get("x")), None)

        payload["datasets"] = datasets
        payload["visualizations"] = visuals
        return payload

    @model_validator(mode="after")
    def validate_visualization_references(self) -> "AnalysisResult":
        dataset_ids = [dataset.id for dataset in self.datasets]
        if len(dataset_ids) != len(set(dataset_ids)):
            raise ValueError("dataset IDs must be unique")
        if sum(len(dataset.rows) for dataset in self.datasets) > 2000:
            raise ValueError("visualization datasets may contain at most 2000 rows in total")

        datasets = {dataset.id: dataset for dataset in self.datasets}
        for visual in self.visualizations:
            dataset = datasets.get(visual.dataset_id)
            if dataset is None:
                raise ValueError(f"visualization references unknown dataset: {visual.dataset_id}")
            available_fields = {key for row in dataset.rows for key in row}
            referenced_fields = {
                field for field in (
                    visual.x, visual.y, visual.value, visual.series,
                    visual.lower, visual.q1, visual.median, visual.q3, visual.upper,
                ) if field
            }
            missing_fields = sorted(referenced_fields - available_fields)
            if missing_fields:
                raise ValueError(
                    f"visualization '{visual.title}' references missing fields: {', '.join(missing_fields)}"
                )

        for evidence in self.evidence:
            if evidence.kind != "dataset":
                continue
            dataset = datasets.get(evidence.dataset_id)
            if dataset is None:
                raise ValueError(f"evidence references unknown dataset: {evidence.dataset_id}")
            available_fields = {key for row in dataset.rows for key in row}
            referenced_fields = {evidence.value_field, *evidence.dimension_fields}
            missing_fields = sorted(field for field in referenced_fields if field not in available_fields)
            if missing_fields:
                raise ValueError(
                    "evidence references missing dataset fields: " + ", ".join(missing_fields)
                )
        return self


class MetricDefinition(BaseModel):
    id: str
    domain: Literal["ecommerce", "saas"]
    name: str
    aliases: List[str] = Field(default_factory=list)
    description: str
    formula: str
    entity: str
    grain: str
    required_concepts: List[str] = Field(default_factory=list)
    time_concept: Optional[str] = None
    default_population: Optional[str] = None
    denominator_policy: Optional[str] = None
    default_filters: List[str] = Field(default_factory=list)
    allowed_dimensions: List[str] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    version: str = "1.0"


class MetricMatch(BaseModel):
    metric: MetricDefinition
    score: float
    matched_terms: List[str] = Field(default_factory=list)
    match_type: Literal["exact", "token_overlap"]
    decision_required: bool = False
    shadowed_by: Optional[str] = None
    field_bindings: Dict[str, List[Dict[str, str]]] = Field(default_factory=dict)
    missing_concepts: List[str] = Field(default_factory=list)
    time_field_candidates: List[Dict[str, str]] = Field(default_factory=list)
    knowledge_context: Dict[str, Any] = Field(default_factory=dict)


class ValidationCheck(BaseModel):
    name: str
    status: Literal["pass", "warning", "fail"]
    message: str


class ValidationReport(BaseModel):
    passed: bool
    confidence: Literal["high", "medium", "low"]
    checks: List[ValidationCheck] = Field(default_factory=list)
    unsupported_numbers: List[float] = Field(default_factory=list)
