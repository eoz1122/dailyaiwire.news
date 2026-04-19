"""
Pydantic schemas for structured Gemini outputs.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DesignTokens(BaseModel):
    model_config = ConfigDict(extra='ignore')

    intensity: str = "standard"
    sentiment_pallet: str = "techno-optimist"
    component_triggers: list[str] = Field(default_factory=list)


class ArticleMetadata(BaseModel):
    model_config = ConfigDict(extra='allow')

    ai_detected: bool = True
    model: str = ""
    label: str = ""


class ArticleAnalysis(BaseModel):
    model_config = ConfigDict(extra='ignore')

    status: Literal["SUCCESS", "INSUFFICIENT_DATA"]
    batch_id: int
    headline: str
    seo_slug: str
    image_query: str = ""
    category: str
    gist: str
    key_details: list[str] = Field(default_factory=list)
    why_it_matters: str
    optimistic_outlook: str
    pessimistic_outlook: str
    hashtags: list[str] = Field(default_factory=list)
    thought_provoking_question: str
    eli5: str
    importance_score: int
    deep_analysis: str
    narration_script: str
    metadata: ArticleMetadata = Field(default_factory=ArticleMetadata)
    design_tokens: DesignTokens = Field(default_factory=DesignTokens)
    mermaid_diagram: str | None = None

    @field_validator(
        'headline', 'seo_slug', 'category', 'gist', 'why_it_matters',
        'optimistic_outlook', 'pessimistic_outlook', 'thought_provoking_question',
        'eli5', 'deep_analysis', 'narration_script', mode='before'
    )
    @classmethod
    def _normalize_required_text(cls, value: Any) -> str:
        if value is None:
            raise ValueError("required text field missing")
        text = str(value).strip()
        if not text:
            raise ValueError("required text field empty")
        return text

    @field_validator('image_query', mode='before')
    @classmethod
    def _normalize_image_query(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator('key_details', 'hashtags', mode='before')
    @classmethod
    def _normalize_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            cleaned = value.strip()
            return [cleaned] if cleaned else []
        raise ValueError("expected list of strings")

    @field_validator('importance_score', mode='before')
    @classmethod
    def _normalize_importance_score(cls, value: Any) -> int:
        score = int(value)
        return max(0, min(100, score))


class LeadExtractionResult(BaseModel):
    model_config = ConfigDict(extra='ignore')

    company_name: str = ""
    email: str | None = None
    confidence: int = 0
    product_value: Literal["HIGH_VALUE", "MID_VALUE", "LOW_VALUE"] = "LOW_VALUE"
    reason: str = ""

    @field_validator('company_name', 'reason', mode='before')
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator('email', mode='before')
    @classmethod
    def _normalize_email(cls, value: Any) -> str | None:
        email = str(value or "").strip()
        return email or None

    @field_validator('confidence', mode='before')
    @classmethod
    def _normalize_confidence(cls, value: Any) -> int:
        score = int(value or 0)
        return max(0, min(100, score))


class DuplicatePair(BaseModel):
    model_config = ConfigDict(extra='ignore')

    keep_id: int
    delete_id: int
    reason: str = ""

    @field_validator('reason', mode='before')
    @classmethod
    def _normalize_reason(cls, value: Any) -> str:
        return str(value or "").strip()


class DuplicateReviewPayload(BaseModel):
    model_config = ConfigDict(extra='ignore')

    duplicate_pairs: list[DuplicatePair] = Field(default_factory=list)
