"""Models module."""

from models.schemas import (
    # Common
    PaginationParams,
    PaginationResult,
    # Summary
    SummaryGenerateRequest,
    SummaryResponse,
    SummaryDetailResponse,
    # Tags
    TagSuggestRequest,
    TagSuggestResponse,
    TagSuggestionItem,
    TagCreateRequest,
    TagResponse,
    TagListResponse,
    # Bookmarks
    BookmarkCreateRequest,
    BookmarkUpdateRequest,
    BookmarkResponse,
    BookmarkDetailResponse,
    BookmarkListRequest,
    BookmarkListResponse,
    NoteCreateRequest,
    NoteUpdateRequest,
    NoteResponse,
    ExportFormat,
    # Search
    SearchRequest,
    SearchResultItem,
    SearchResponse,
    # Assist
    PolishRequest,
    FormatRequest,
    CheckCodeRequest,
    CheckCodeIssue,
    CheckCodeResponse,
    AssistResponse,
    # Compare
    CompareItem,
    CompareRequest,
    CompareResponse,
    # Config
    ProviderInfo,
    ConfigResponse,
    ProviderUpdate,
    ConfigUpdateRequest,
    # Admin
    StatsResponse,
    ReindexRequest,
    ReindexResponse,
    # Auth
    LoginRequest,
    LoginResponse,
    UserResponse,
    ChangePasswordRequest,
    # LLM
    LLMChatMessage,
    LLMChatRequest,
    LLMChatResponse,
)

from models.responses import (
    ResponseCode,
    BaseResponse,
    ErrorResponse,
    success,
    error,
    param_error,
    not_found,
    already_exists,
    llm_error,
    db_error,
    internal_error,
)

__all__ = [
    # Schemas - Common
    "PaginationParams",
    "PaginationResult",
    # Schemas - Summary
    "SummaryGenerateRequest",
    "SummaryResponse",
    "SummaryDetailResponse",
    # Schemas - Tags
    "TagSuggestRequest",
    "TagSuggestResponse",
    "TagSuggestionItem",
    "TagCreateRequest",
    "TagResponse",
    "TagListResponse",
    # Schemas - Bookmarks
    "BookmarkCreateRequest",
    "BookmarkUpdateRequest",
    "BookmarkResponse",
    "BookmarkDetailResponse",
    "BookmarkListRequest",
    "BookmarkListResponse",
    "NoteCreateRequest",
    "NoteUpdateRequest",
    "NoteResponse",
    "ExportFormat",
    # Schemas - Search
    "SearchRequest",
    "SearchResultItem",
    "SearchResponse",
    # Schemas - Assist
    "PolishRequest",
    "FormatRequest",
    "CheckCodeRequest",
    "CheckCodeIssue",
    "CheckCodeResponse",
    "AssistResponse",
    # Schemas - Compare
    "CompareItem",
    "CompareRequest",
    "CompareResponse",
    # Schemas - Config
    "ProviderInfo",
    "ConfigResponse",
    "ProviderUpdate",
    "ConfigUpdateRequest",
    # Schemas - Admin
    "StatsResponse",
    "ReindexRequest",
    "ReindexResponse",
    # Schemas - Auth
    "LoginRequest",
    "LoginResponse",
    "UserResponse",
    "ChangePasswordRequest",
    # Schemas - LLM
    "LLMChatMessage",
    "LLMChatRequest",
    "LLMChatResponse",
    # Responses
    "ResponseCode",
    "BaseResponse",
    "ErrorResponse",
    "success",
    "error",
    "param_error",
    "not_found",
    "already_exists",
    "llm_error",
    "db_error",
    "internal_error",
]
