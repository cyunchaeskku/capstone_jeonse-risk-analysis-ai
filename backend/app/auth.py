"""회원가입·로그인·로그아웃. 세션 토큰은 DB에 해시로만 저장한다."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import rate_limit
from .db import get_db
from .models import User, UserSession
from .schemas import LoginRequest, LoginResponse, SignupRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

# 파라미터는 라이브러리 기본값(m=64MiB, t=3, p=4)을 쓴다. RFC 9106의 저메모리 권장 설정이다.
_hasher = PasswordHasher()

# 이메일이 없을 때도 검증에 같은 시간이 걸리게 하려고 한 번 해시해 두고 쓴다.
# 이게 없으면 응답 시간 차이만으로 가입된 이메일인지 알아낼 수 있다.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing-equalization")

SESSION_TTL = timedelta(days=7)

# auto_error=False: 헤더가 없을 때 FastAPI 기본 403 대신 아래에서 401을 돌려주기 위해서다.
_bearer = HTTPBearer(auto_error=False)

_INVALID_CREDENTIALS = "이메일 또는 비밀번호가 올바르지 않습니다."


def _token_hash(token: str) -> str:
    """세션 토큰은 256bit 랜덤이라 무차별 대입이 불가능하므로 솔트 없는 SHA-256으로 충분하다."""
    return hashlib.sha256(token.encode()).hexdigest()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> UserSession:
    if credentials is None:
        raise _unauthorized("인증이 필요합니다.")

    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == _token_hash(credentials.credentials))
    )
    if session is None:
        raise _unauthorized("세션이 유효하지 않습니다.")
    if session.expires_at <= datetime.now(timezone.utc):
        db.delete(session)
        db.commit()
        raise _unauthorized("세션이 만료되었습니다.")
    return session


def get_current_user(session: UserSession = Depends(_current_session)) -> User:
    return session.user


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, request: Request, db: Session = Depends(get_db)) -> User:
    # 가입도 같은 비용(64MiB)의 해시를 돌린다. 여기를 빼면 공격이 이쪽으로 옮겨온다.
    rate_limit.enforce_ip(request)

    user = User(
        email=payload.email.strip().lower(),
        password_hash=_hasher.hash(payload.password),
        name=payload.name.strip(),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 가입된 이메일입니다.",
        )
    db.refresh(user)
    return user


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    email = payload.email.strip().lower()

    # 해시 전에 검사해야 무차별 대입과 메모리 고갈이 동시에 막힌다.
    rate_limit.enforce_ip(request)
    rate_limit.enforce_email(email)

    user = db.scalar(select(User).where(User.email == email))

    if user is None:
        # 계정이 있는지 알아내지 못하게, 없는 이메일이어도 같은 비용의 검증을 수행한다.
        try:
            _hasher.verify(_DUMMY_HASH, payload.password)
        except VerifyMismatchError:
            pass
        # 없는 이메일도 같이 누적해야 429 발생 시점으로 가입 여부가 드러나지 않는다.
        rate_limit.record_failure(email)
        raise _unauthorized(_INVALID_CREDENTIALS)

    try:
        _hasher.verify(user.password_hash, payload.password)
    except VerifyMismatchError:
        rate_limit.record_failure(email)
        raise _unauthorized(_INVALID_CREDENTIALS)

    rate_limit.clear_failures(email)

    # 해시 파라미터 권장값이 올라가면 로그인하는 김에 새 파라미터로 다시 저장한다.
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = _hasher.hash(payload.password)

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=now + SESSION_TTL,
        )
    )
    user.last_login_at = now
    db.commit()

    return LoginResponse(token=token, user=UserResponse.model_validate(user, from_attributes=True))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    session: UserSession = Depends(_current_session), db: Session = Depends(get_db)
) -> None:
    db.delete(session)
    db.commit()


@router.get("/me", response_model=UserResponse)
def read_me(user: User = Depends(get_current_user)) -> User:
    return user
