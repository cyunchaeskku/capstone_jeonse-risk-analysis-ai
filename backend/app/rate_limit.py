"""로그인·가입 시도 제한. 무차별 대입과 Argon2 메모리 고갈(해시 1회당 64MiB) 차단.

인메모리 슬라이딩 윈도우. Cloud Run max instances=1 전제 — 다중 인스턴스면 Redis 필요.
"""

import time
from threading import Lock

from fastapi import HTTPException, Request, status

IP_MAX, IP_WINDOW = 10, 300  # IP별 login+signup 합산, 5분
EMAIL_MAX, EMAIL_WINDOW = 5, 900  # 계정별 로그인 실패, 15분
_SWEEP_INTERVAL = 600  # 미사용 키 정리 주기

_hits: dict[str, list[float]] = {}
_lock = Lock()
_last_sweep = 0.0


def client_ip(request: Request) -> str:
    """Cloud Run이 X-Forwarded-For 끝에 실제 IP를 덧붙임 → 마지막 값만 신뢰(앞쪽은 위조 가능)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _sweep(now: float) -> None:
    """키 누적 자체가 메모리 고갈 경로 → 주기적으로 만료 키 삭제."""
    global _last_sweep
    if now - _last_sweep < _SWEEP_INTERVAL:
        return
    _last_sweep = now
    stale = max(IP_WINDOW, EMAIL_WINDOW)
    for key in [k for k, v in _hits.items() if not v or now - v[-1] > stale]:
        del _hits[key]


def _fresh(key: str, window: int, now: float) -> list[float]:
    """만료 기록 제거 후 남은 목록. 저장까지 한다."""
    hits = [t for t in _hits.get(key, ()) if now - t < window]
    _hits[key] = hits
    return hits


def _too_many(retry_after: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(retry_after)},
    )


def enforce_ip(request: Request) -> None:
    """성공·실패 무관하게 1건 기록. 해시 계산 전에 호출해야 DoS가 막힌다."""
    now = time.monotonic()
    key = f"ip:{client_ip(request)}"
    with _lock:
        _sweep(now)
        hits = _fresh(key, IP_WINDOW, now)
        if len(hits) < IP_MAX:
            hits.append(now)
            return
        retry_after = int(IP_WINDOW - (now - hits[0])) + 1
    raise _too_many(retry_after, "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")


def enforce_email(email: str) -> None:
    """실패 누적만 검사. 기록은 record_failure가 한다."""
    now = time.monotonic()
    with _lock:
        hits = _fresh(f"email:{email}", EMAIL_WINDOW, now)
        if len(hits) < EMAIL_MAX:
            return
        retry_after = int(EMAIL_WINDOW - (now - hits[0])) + 1
    raise _too_many(
        retry_after,
        f"로그인 시도가 많아 일시적으로 차단되었습니다. {retry_after // 60 + 1}분 후 다시 시도해 주세요.",
    )


def record_failure(email: str) -> None:
    now = time.monotonic()
    with _lock:
        _fresh(f"email:{email}", EMAIL_WINDOW, now).append(now)


def clear_failures(email: str) -> None:
    with _lock:
        _hits.pop(f"email:{email}", None)


def reset() -> None:
    """테스트 전용."""
    global _last_sweep
    with _lock:
        _hits.clear()
        _last_sweep = 0.0
