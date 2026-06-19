from fastapi import Request


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def client_user_agent(request: Request) -> str | None:
    return request.headers.get("User-Agent") or None


def client_mac(request: Request) -> str | None:
    return request.headers.get("X-Mac-Address") or None
