"""The JSON-RPC envelope the MCP edge speaks over HTTP."""

from typing import Any

from fastapi.responses import JSONResponse


def rpc_result(id_: Any, result: dict) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": result})


def rpc_error(
    id_: Any, code: int, message: str, status: int = 200, data: dict[str, Any] | None = None
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "error": error}, status_code=status)
