from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


# M-8: 프록시/로드밸런서 뒤에서 올바른 IP 추출
def _get_real_ip(request: Request) -> str:
    """X-Forwarded-For 헤더가 있으면 첫 번째 IP 사용"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_get_real_ip)
