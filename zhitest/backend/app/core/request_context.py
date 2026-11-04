from contextvars import ContextVar

from starlette.requests import Request

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return request_id_var.get()


def request_id_from(request: Request) -> str:
    current = get_request_id()
    if current != "-":
        return current
    state = request.scope.get("state")
    if isinstance(state, dict):
        value = state.get("request_id")
        if isinstance(value, str) and value:
            return value
    return current
