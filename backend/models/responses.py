"""Unified response format for all API endpoints."""

from typing import Generic, TypeVar, Optional, Dict, Any
from pydantic import BaseModel

T = TypeVar("T")


class ResponseCode:
    """API response codes."""
    SUCCESS = 0
    # Parameter errors: 1000-1999
    PARAM_ERROR = 1001
    NOT_FOUND = 1002
    ALREADY_EXISTS = 1003
    
    # LLM errors: 2000-2999
    LLM_ERROR = 2001
    LLM_TIMEOUT = 2002
    LLM_RATE_LIMIT = 2003
    
    # Database errors: 3000-3999
    DB_ERROR = 3001
    DB_CONNECTION_ERROR = 3002
    
    # System errors: 4000-4999
    INTERNAL_ERROR = 4001
    SERVICE_UNAVAILABLE = 4002


class BaseResponse(BaseModel, Generic[T]):
    """Base API response wrapper."""
    code: int = ResponseCode.SUCCESS
    message: str = "success"
    data: Optional[T] = None


class ErrorResponse(BaseResponse):
    """Error response."""
    data: Optional[Dict[str, Any]] = None


def success(data: T = None, message: str = "success") -> BaseResponse[T]:
    """Create success response."""
    return BaseResponse(
        code=ResponseCode.SUCCESS,
        message=message,
        data=data
    )


def error(
    code: int = ResponseCode.INTERNAL_ERROR,
    message: str = "error",
    data: Dict[str, Any] = None
) -> ErrorResponse:
    """Create error response."""
    return ErrorResponse(
        code=code,
        message=message,
        data=data
    )


def param_error(message: str = "Invalid parameters", data: Dict[str, Any] = None) -> ErrorResponse:
    """Create parameter error response."""
    return error(ResponseCode.PARAM_ERROR, message, data)


def not_found(message: str = "Resource not found") -> ErrorResponse:
    """Create not found error response."""
    return error(ResponseCode.NOT_FOUND, message)


def already_exists(message: str = "Resource already exists") -> ErrorResponse:
    """Create already exists error response."""
    return error(ResponseCode.ALREADY_EXISTS, message)


def llm_error(message: str = "LLM service error", data: Dict[str, Any] = None) -> ErrorResponse:
    """Create LLM error response."""
    return error(ResponseCode.LLM_ERROR, message, data)


def db_error(message: str = "Database error", data: Dict[str, Any] = None) -> ErrorResponse:
    """Create database error response."""
    return error(ResponseCode.DB_ERROR, message, data)


def internal_error(message: str = "Internal server error") -> ErrorResponse:
    """Create internal error response."""
    return error(ResponseCode.INTERNAL_ERROR, message)
