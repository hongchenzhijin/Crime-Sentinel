"""Typed contracts shared by the ingestion pipeline and the API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Category(str, Enum):
    NEWS_REPORTING = "NEWS_REPORTING"
    ACADEMIC_OR_RESEARCH = "ACADEMIC_OR_RESEARCH"
    PREVENTION_OR_SUPPORT = "PREVENTION_OR_SUPPORT"
    NEUTRAL_DISCUSSION = "NEUTRAL_DISCUSSION"
    GLORIFICATION_OR_PRAISE = "GLORIFICATION_OR_PRAISE"
    ENCOURAGEMENT_OR_RECRUITMENT = "ENCOURAGEMENT_OR_RECRUITMENT"
    EXPLICIT_THREAT_OR_INTENT = "EXPLICIT_THREAT_OR_INTENT"
    UNCERTAIN_REQUIRES_REVIEW = "UNCERTAIN_REQUIRES_REVIEW"


# Content categories that may need safety attention. Used only for aggregate
# content metrics and review prioritisation, never to score people.
HARMFUL_CATEGORIES = {
    Category.GLORIFICATION_OR_PRAISE,
    Category.ENCOURAGEMENT_OR_RECRUITMENT,
    Category.EXPLICIT_THREAT_OR_INTENT,
}

ReviewStatus = Literal["pending", "confirmed", "corrected", "marked_uncertain"]
ReviewPriority = Literal["urgent", "high", "normal", "low"]
SourceType = Literal["synthetic", "permitted_research"]


class MediaRef(BaseModel):
    """An image attached to a post. `file` is a bare file name inside the dataset's media folder."""

    file: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-]+\.(png|jpg|jpeg)$")
    alt_text: str = Field(default="", max_length=500)


class PostIn(BaseModel):
    """A record as it arrives from a dataset file, before minimisation."""

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    source_type: SourceType
    source_name: str = Field(min_length=1, max_length=200)
    source_url: str | None = None
    published_at: datetime
    text: str = Field(min_length=1, max_length=5000)
    language: str = Field(default="en", min_length=2, max_length=8)
    hashtags: list[str] = Field(default_factory=list)
    public_topic_ids: list[str] = Field(default_factory=list)
    author_reference: str | None = None
    interaction_reference_ids: list[str] = Field(default_factory=list)
    is_synthetic: bool
    media: list[MediaRef] = Field(default_factory=list, max_length=4)

    @field_validator("hashtags")
    @classmethod
    def normalise_hashtags(cls, v: list[str]) -> list[str]:
        return sorted({h.strip().lstrip("#").lower() for h in v if h.strip().lstrip("#")})

    @model_validator(mode="after")
    def synthetic_flag_consistent(self) -> "PostIn":
        if (self.source_type == "synthetic") != self.is_synthetic:
            raise ValueError("is_synthetic must be true exactly when source_type is 'synthetic'")
        return self


class Post(BaseModel):
    id: str
    source_type: SourceType
    source_name: str
    source_url: str | None
    published_at: datetime
    text: str
    language: str
    hashtags: list[str]
    public_topic_ids: list[str]
    author_reference: str | None  # non-reversible pseudonym, or None
    interaction_reference_ids: list[str]
    is_synthetic: bool
    media: list[MediaRef] = Field(default_factory=list)


class EvidenceSpan(BaseModel):
    start: int
    end: int
    text: str
    cue_category: Category | Literal["KEYWORD_SIGNAL"]
    note: str


class MediaObservation(BaseModel):
    """What a vision model reported about one attached image."""

    file: str
    observation: str = ""
    image_text: str = ""        # text visible in the image (OCR by the vision model)
    visual_evidence: str = ""   # what in the image supports the category, if harmful
    engine: str


class ClassificationResult(BaseModel):
    """Output of a classifier for one post (model output only)."""

    category: Category
    confidence: float = Field(
        ge=0.0, le=1.0, description="Model confidence in the category. NOT a probability that anyone is dangerous."
    )
    evidence_spans: list[EvidenceSpan]
    explanation: str
    signals: list[str]
    model_name: str
    model_version: str
    category_scores: dict[str, float] = Field(default_factory=dict)
    media_observations: list[MediaObservation] = Field(default_factory=list)


class Classification(ClassificationResult):
    post_id: str
    classified_at: datetime
    review_status: ReviewStatus = "pending"
    review_priority: ReviewPriority = "normal"
    reviewer_category: Category | None = None
    reviewer_note: str | None = None
    reviewed_at: datetime | None = None

    @property
    def effective_category(self) -> Category:
        return self.reviewer_category or self.category


class Topic(BaseModel):
    id: str
    label: str
    description: str
    is_synthetic: bool = True


class PostWithClassification(BaseModel):
    post: Post
    classification: Classification
    topics: list[Topic] = Field(default_factory=list)


class ReviewAction(str, Enum):
    CONFIRM = "confirm"
    CHANGE = "change"
    MARK_UNCERTAIN = "mark_uncertain"


class ReviewRequest(BaseModel):
    action: ReviewAction
    reviewer_category: Category | None = None
    reviewer: str = Field(default="demo_reviewer", min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def category_required_for_change(self) -> "ReviewRequest":
        if self.action == ReviewAction.CHANGE and self.reviewer_category is None:
            raise ValueError("reviewer_category is required when action is 'change'")
        if self.action != ReviewAction.CHANGE and self.reviewer_category is not None:
            raise ValueError("reviewer_category is only allowed when action is 'change'")
        return self


class AuditEntry(BaseModel):
    id: int
    timestamp: datetime
    actor: str
    action: str
    post_id: str | None
    details: dict


class PostPage(BaseModel):
    items: list[PostWithClassification]
    total: int
    page: int
    page_size: int


class DatasetInfo(BaseModel):
    source_names: list[str]
    is_synthetic: bool
    synthetic_count: int
    total_posts: int
    period_start: datetime | None
    period_end: datetime | None
    ingested_at: datetime | None
    retention_days: int


class GraphNode(BaseModel):
    id: str
    type: Literal["POST", "HASHTAG", "TOPIC", "PUBLIC_COMMUNITY_REFERENCE"]
    label: str
    category: Category | None = None
    weight: int = 1
    provenance: str
    community: str | None = None  # GraphRAG community of a POST node, if communities have been built


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: Literal["USES_HASHTAG", "MENTIONS_TOPIC", "SIMILAR_CONTENT", "PUBLICLY_LINKED_TO", "SHARES_IMAGE"]
    weight: float = 1.0
    method: str
    provenance: str


class Graph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    disclaimer: str
    truncated: bool = False
