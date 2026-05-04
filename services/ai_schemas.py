"""
Pydantic schemas for structured Gemini outputs.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    headline: Optional[str] = None
    seo_slug: Optional[str] = None
    image_query: str = ""
    category: Optional[str] = None
    gist: Optional[str] = None
    key_details: list[str] = Field(default_factory=list)
    why_it_matters: Optional[str] = None
    optimistic_outlook: Optional[str] = None
    pessimistic_outlook: Optional[str] = None
    hashtags: list[str] = Field(default_factory=list)
    thought_provoking_question: Optional[str] = None
    eli5: Optional[str] = None
    importance_score: int = 0
    deep_analysis: Optional[str] = None
    narration_script: Optional[str] = None
    metadata: ArticleMetadata = Field(default_factory=ArticleMetadata)
    design_tokens: DesignTokens = Field(default_factory=DesignTokens)
    mermaid_diagram: Optional[str] = None

    @field_validator(
        'headline', 'seo_slug', 'category', 'gist', 'why_it_matters',
        'optimistic_outlook', 'pessimistic_outlook', 'thought_provoking_question',
        'eli5', 'deep_analysis', 'narration_script', mode='before'
    )
    @classmethod
    def _normalize_text(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

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
        score = int(value or 0)
        return max(0, min(100, score))

    @model_validator(mode='after')
    def _success_requires_content(self):
        if self.status != "SUCCESS":
            return self

        required_fields = (
            'headline', 'seo_slug', 'category', 'gist', 'why_it_matters',
            'optimistic_outlook', 'pessimistic_outlook', 'thought_provoking_question',
            'eli5', 'deep_analysis', 'narration_script',
        )
        missing = [field for field in required_fields if not getattr(self, field)]
        if missing:
            raise ValueError(f"SUCCESS article missing required fields: {', '.join(missing)}")
        return self


class LeadExtractionResult(BaseModel):
    model_config = ConfigDict(extra='ignore')

    company_name: str = ""
    email: Optional[str] = None
    confidence: int = 0
    product_value: Literal["HIGH_VALUE", "MID_VALUE", "LOW_VALUE"] = "LOW_VALUE"
    reason: str = ""

    @field_validator('company_name', 'reason', mode='before')
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator('email', mode='before')
    @classmethod
    def _normalize_email(cls, value: Any) -> Optional[str]:
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
