"""Pydantic schemas for request/response models."""

from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


# ============== Common Schemas ==============

class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginationResult(BaseModel):
    """Pagination result metadata."""
    page: int
    page_size: int
    total: int
    total_pages: int


# ============== Summary Schemas ==============

class SummaryGenerateRequest(BaseModel):
    """Request to generate summary."""
    thread_id: str = Field(..., min_length=1, description="Unique thread identifier")
    title: str = Field(..., min_length=1, description="Thread title")
    content: str = Field(..., min_length=1, description="Full conversation content")
    model: Optional[str] = Field(default=None, description="Model to use for generation")
    auto_tags: bool = Field(default=True, description="Whether to auto-generate tags")
    stream: bool = Field(default=False, description="Whether to stream the response via SSE")
    language: str = Field(default="中文", description="Response language: 中文 / English")


class SummaryResponse(BaseModel):
    """Summary response."""
    thread_id: str
    title: str
    summary: str
    auto_tags: List[str] = Field(default_factory=list)
    model_used: str
    tokens_used: int
    created_at: str
    updated_at: str


class SummaryDetailResponse(SummaryResponse):
    """Detailed summary response."""
    content_hash: str
    expires_at: Optional[str] = None


# ============== Tag Schemas ==============

class TagSuggestRequest(BaseModel):
    """Request to suggest tags."""
    content: str = Field(..., min_length=1, description="Content to analyze")
    existing_tags: List[str] = Field(default_factory=list, description="Already selected tags")
    max_suggestions: int = Field(default=5, ge=1, le=10)


class TagSuggestionItem(BaseModel):
    """Single tag suggestion with metadata."""
    name: str
    category: str = "custom"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class TagSuggestResponse(BaseModel):
    """Tag suggestion response."""
    suggested_tags: List["TagSuggestionItem"]


class TagCreateRequest(BaseModel):
    """Request to create a tag."""
    name: str = Field(..., min_length=1, max_length=50)
    category: str = Field(default="custom")


class TagResponse(BaseModel):
    """Tag response."""
    id: int
    name: str
    category: str
    created_at: str


class TagListResponse(BaseModel):
    """Tag list response."""
    items: List[TagResponse]
    categories: Dict[str, List[str]] = Field(default_factory=dict)


# ============== Bookmark/Knowledge Schemas ==============

class BookmarkCreateRequest(BaseModel):
    """Request to create a bookmark."""
    thread_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class BookmarkUpdateRequest(BaseModel):
    """Request to update a bookmark."""
    title: Optional[str] = None
    url: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


class BookmarkResponse(BaseModel):
    """Bookmark response."""
    bookmark_id: str
    thread_id: str
    title: str
    url: str
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class BookmarkDetailResponse(BookmarkResponse):
    """Detailed bookmark response with notes."""
    notes: Optional[str] = None


class BookmarkListRequest(BaseModel):
    """Request to list bookmarks."""
    tag: Optional[str] = None
    search: Optional[str] = None
    sort_by: Literal["created", "updated", "title"] = "created"
    sort_order: Literal["asc", "desc"] = "desc"


class BookmarkListResponse(BaseModel):
    """Bookmark list response."""
    pagination: PaginationResult
    items: List[BookmarkResponse]


class NoteCreateRequest(BaseModel):
    """Request to create a note."""
    content: str = Field(..., min_length=1)


class NoteUpdateRequest(BaseModel):
    """Request to update a note."""
    content: str = Field(..., min_length=1)


class NoteResponse(BaseModel):
    """Note response."""
    id: int
    bookmark_id: str
    content: str
    created_at: str
    updated_at: str


class ExportFormat(BaseModel):
    """Export format options."""
    format: Literal["json", "markdown", "csv"] = "json"
    include_notes: bool = True
    include_tags: bool = True


# ============== Search Schemas ==============

class SearchRequest(BaseModel):
    """Search request."""
    query: str = Field(..., min_length=1, description="Search query")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Optional filters")
    pagination: PaginationParams = Field(default_factory=PaginationParams)


class SearchResultItem(BaseModel):
    """Single search result."""
    bookmark_id: str
    thread_id: str
    title: str
    url: str
    summary: Optional[str] = None
    highlight: Optional[str] = None  # Highlighted snippet
    score: float
    tags: List[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """Search response."""
    query: str
    pagination: PaginationResult
    results: List[SearchResultItem]
    suggestions: List[str] = Field(default_factory=list)


# ============== Assist Schemas ==============

class PolishRequest(BaseModel):
    """Request to polish text."""
    text: str = Field(..., min_length=1)
    style: Literal["professional", "casual", "academic", "concise"] = "professional"
    keep_length: bool = Field(default=True, description="Keep similar length")


class FormatRequest(BaseModel):
    """Request to format text."""
    text: str = Field(..., min_length=1)
    format_type: Literal["markdown", "json", "sql", "python"] = "markdown"


class CheckCodeRequest(BaseModel):
    """Request to check code."""
    code: str = Field(..., min_length=1)
    language: Optional[str] = None


class CheckCodeIssue(BaseModel):
    """Code issue."""
    line: int
    column: Optional[int] = None
    severity: Literal["error", "warning", "info"]
    message: str
    suggestion: Optional[str] = None


class CheckCodeResponse(BaseModel):
    """Code check response."""
    issues: List[CheckCodeIssue]
    fixed_code: Optional[str] = None
    summary: str


class AssistResponse(BaseModel):
    """Generic assist response."""
    result: str
    original_length: int
    result_length: int
    changes_made: List[str] = Field(default_factory=list)


# ============== Auth Schemas ==============

class LoginRequest(BaseModel):
    """Login request."""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    """Login response."""
    token: str
    user: "UserResponse"


class UserResponse(BaseModel):
    """User info response."""
    id: int
    username: str
    role: str
    is_active: bool
    created_at: str
    last_login: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    """Change password request."""
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128, description="At least 8 chars with letters and digits")


# ============== Admin Schemas ==============

class StatsResponse(BaseModel):
    """System stats response."""
    database: Dict[str, Any]
    llm_usage: Dict[str, Any]
    bookmarks: Dict[str, Any]
    summaries: Dict[str, Any]
    storage: Dict[str, Any]


class ReindexRequest(BaseModel):
    """Reindex request."""
    force: bool = Field(default=False)


class ReindexResponse(BaseModel):
    """Reindex response."""
    success: bool
    message: str
    indexed_count: int


# ============== LLM Schemas ==============

class LLMChatMessage(BaseModel):
    """LLM chat message."""
    role: Literal["system", "user", "assistant"] = "user"
    content: str


class LLMChatRequest(BaseModel):
    """LLM chat request."""
    messages: List[LLMChatMessage]
    model: Optional[str] = None
    stream: bool = False
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1)


class LLMChatResponse(BaseModel):
    """LLM chat response."""
    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: str


# ============== Compare Schemas ==============

class CompareItem(BaseModel):
    """Single item to compare."""
    bookmark_id: str
    title: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1, max_length=5000)


class CompareRequest(BaseModel):
    """Request to compare multiple bookmarks."""
    items: List[CompareItem] = Field(..., min_length=2, max_length=5, description="2-5 items to compare")
    focus: Optional[str] = Field(default=None, description="Comparison focus, e.g. '回测指标'")


class CompareResponse(BaseModel):
    """Comparison result."""
    table: str = Field(description="Markdown comparison table")
    summary: str = Field(description="Natural language comparison summary")
    recommendation: Optional[str] = Field(default=None, description="Which to read first")


# ============== Config Schemas ==============

class ProviderInfo(BaseModel):
    """Public provider information (no api_key)."""
    name: str
    base_url: str
    models: List[str] = Field(default_factory=list)
    builtin: bool = Field(default=False)
    has_api_key: bool = Field(default=False, description="Whether an API key is configured")
    protocol: str = Field(default="openai", description="openai or anthropic")


class ConfigResponse(BaseModel):
    """Sanitized config returned to the client (never includes raw api_keys)."""
    host: str
    port: int
    data_dir: str
    default_model: str
    default_provider: str
    providers: Dict[str, ProviderInfo]


class ProviderUpdate(BaseModel):
    """Partial update for a single provider."""
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = Field(default=None, description="Plaintext API key; omit to keep current")
    models: Optional[List[str]] = None
    protocol: Optional[str] = Field(default=None, description="openai or anthropic")


class ConfigUpdateRequest(BaseModel):
    """Partial config update. Any omitted field is left unchanged."""
    default_model: Optional[str] = None
    default_provider: Optional[str] = None
    data_dir: Optional[str] = Field(default=None, description="Knowledge storage base directory")
    providers: Optional[Dict[str, ProviderUpdate]] = None
    delete_providers: Optional[List[str]] = Field(default=None, description="Provider IDs to delete")


# ============== Memory System Schemas ==============

class UserProfileItem(BaseModel):
    """Single user profile entry."""
    profile_key: str
    profile_value: str
    source: Literal["auto", "manual"] = "manual"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class UserProfileUpdateRequest(BaseModel):
    """Request to update user profile."""
    items: List[UserProfileItem]


class UserProfileResponse(BaseModel):
    """User profile response."""
    items: List[Dict[str, Any]]


class MemoryItemCreate(BaseModel):
    """Request to create a memory item."""
    memory_type: Literal["user_fact", "strategy_insight", "preference", "skill_observation"]
    content: str = Field(..., min_length=1, max_length=2000)
    importance: int = Field(default=3, ge=1, le=5)
    source_thread_id: Optional[str] = None


class MemoryItemResponse(BaseModel):
    """Memory item response."""
    id: int
    memory_type: str
    content: str
    importance: int
    is_active: bool
    access_count: int
    created_at: str


class MemoryItemListResponse(BaseModel):
    """Memory item list response."""
    items: List[MemoryItemResponse]


class ReadingEventRequest(BaseModel):
    """Request to record a reading event."""
    thread_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    duration_seconds: int = Field(default=0, ge=0)
    scroll_depth: float = Field(default=0.0, ge=0.0, le=1.0)


class MemoryStatsResponse(BaseModel):
    """Memory system statistics."""
    total_memories: int
    active_memories: int
    total_readings: int
    total_sessions: int
    total_strategies: int
    profile_keys: int


# ============== Chat Session Schemas ==============

class ChatSessionCreate(BaseModel):
    """Request to create a chat session."""
    thread_id: Optional[str] = None
    page_url: Optional[str] = None
    page_title: Optional[str] = None


class ChatSessionResponse(BaseModel):
    """Chat session response."""
    id: str
    title: str
    thread_id: Optional[str] = None
    page_url: Optional[str] = None
    page_title: Optional[str] = None
    message_count: int
    summary: Optional[str] = None
    created_at: str
    updated_at: str


class ChatSessionListResponse(BaseModel):
    """Chat session list response."""
    items: List[ChatSessionResponse]
    pagination: PaginationResult


class ChatMessageInSession(BaseModel):
    """Request to send a message in a session."""
    message: str = Field(..., min_length=1)
    context: Optional[str] = None
    language: str = Field(default="中文")
    stream: bool = Field(default=False, description="Return server-sent events instead of a single JSON response")


class ChatMessageResponse(BaseModel):
    """Chat message response."""
    id: int
    role: str
    content: str
    tokens_used: int
    created_at: str


class ChatSessionDetailResponse(ChatSessionResponse):
    """Chat session with messages."""
    messages: List[ChatMessageResponse]


# ============== Strategy Entity Schemas ==============

class StrategyExtractRequest(BaseModel):
    """Request to extract strategy from content."""
    thread_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class StrategyEntityResponse(BaseModel):
    """Strategy entity response."""
    id: int
    thread_id: str
    name: str
    strategy_type: Optional[str] = None
    asset_class: Optional[str] = None
    structured_data: Dict[str, Any]
    confidence: float
    created_at: str
