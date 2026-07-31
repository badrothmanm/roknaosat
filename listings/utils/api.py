from __future__ import annotations
from typing import Any
from django.http import JsonResponse

def api_success(message: str = "", data: dict[str, Any] | None = None, status: int = 200) -> JsonResponse:
    return JsonResponse(
        {"ok": True, "message": message, "data": data or {}, "error": "", "errors": {}},
        status=status,
    )

def api_error(error: str = "حدث خطأ", *, errors: dict[str, Any] | None = None, status: int = 400, data: dict[str, Any] | None = None) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "message": "", "data": data or {}, "error": error, "errors": errors or {}},
        status=status,
    )
