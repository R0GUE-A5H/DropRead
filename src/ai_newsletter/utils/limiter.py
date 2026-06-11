from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def get_user_or_ip(request: Request) -> str:
    user = request.session.get("user")
    return (
        f"user:{user['id']}" if user else f"ip:{get_remote_address(request)}"
    )  # use ip for unauth


limiter = Limiter(key_func=get_user_or_ip)
