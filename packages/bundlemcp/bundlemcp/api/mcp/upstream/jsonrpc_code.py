from mcp.shared.exceptions import MCPError


def jsonrpc_code(exc: BaseException) -> int | None:
    """The code of the JSON-RPC error anywhere in ``exc``'s chain or groups, if there is one."""
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, MCPError):
            return current.code
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
    return None
