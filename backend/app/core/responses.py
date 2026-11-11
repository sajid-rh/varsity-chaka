"""The standard JSON response envelope (docs/02-architecture.md, section 8)."""


def ok(data):
    return {"success": True, "data": data, "error": None}


def fail(code: str, message: str, details: list | None = None):
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"success": False, "data": None, "error": error}
