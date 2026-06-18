from typing import Any, Literal

from pydantic import BaseModel, Field


Role = Literal["admin", "manager", "nailist"]
OrgType = Literal["headquarters", "branch"]
Visibility = Literal["company", "headquarters", "branch", "manager_only", "admin_only"]
ManualStatus = Literal["draft", "published", "archived"]


class User(BaseModel):
    id: str
    name: str
    role: Role
    org_type: OrgType
    branch_id: str | None = None


class ManualBase(BaseModel):
    title: str
    category: str
    body: str
    visibility: Visibility
    status: ManualStatus = "published"
    branch_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class Manual(ManualBase):
    id: str
    version: int
    updated_at: str


class ManualCreate(ManualBase):
    pass


class ManualUpdate(ManualBase):
    pass


class SearchRequest(BaseModel):
    user_id: str
    query: str
    top_k: int = 5


class AnswerRequest(SearchRequest):
    pass


class SourceChunk(BaseModel):
    chunk_id: str
    manual_id: str
    manual_title: str
    manual_version: int
    text: str
    vector_score: float
    keyword_score: float
    hybrid_score: float
    rerank_score: float


class AnswerResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    filtered_out_count: int
    audit_log_id: str


class EvaluationResult(BaseModel):
    user_id: str
    query: str
    expected_manual_ids: list[str]
    retrieved_manual_ids: list[str]
    recall: float
    precision: float
    top_k_hit: bool
    leaked_manual_ids: list[str]


class ErrorResponse(BaseModel):
    detail: str
    hint: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

