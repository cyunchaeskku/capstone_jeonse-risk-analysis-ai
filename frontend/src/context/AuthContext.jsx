import { createContext, useContext, useEffect, useMemo, useState } from 'react';

const AuthContext = createContext(null);
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const TOKEN_KEY = 'jeonse_auth_token';

const NETWORK_ERROR = '네트워크 연결을 확인해 주세요.';

// 상태 코드별 고정 문구. 404/405는 프론트만 먼저 배포된 경우.
const STATUS_MESSAGES = {
  404: '서비스를 일시적으로 사용할 수 없습니다.',
  405: '서비스를 일시적으로 사용할 수 없습니다.',
  429: '요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.',
};

// 백엔드가 한국어 detail을 주는 코드. 나머지는 "Not Found" 같은 원문이 노출된다.
const TRUSTED_DETAIL = [401, 409, 429];

// 422 detail[0].loc 마지막 값 = 필드명
const FIELD_MESSAGES = {
  email: '이메일 형식이 올바르지 않습니다.',
  password: '비밀번호는 8자 이상 128자 이하로 입력해 주세요.',
  name: '이름을 입력해 주세요.',
};

async function readError(response, fallback) {
  const data = await response.json().catch(() => null);
  if (TRUSTED_DETAIL.includes(response.status) && typeof data?.detail === 'string') {
    return data.detail;
  }
  if (response.status === 422) {
    return FIELD_MESSAGES[data?.detail?.[0]?.loc?.at(-1)] ?? '입력값을 다시 확인해 주세요.';
  }
  if (response.status >= 500) return '서버 오류입니다. 잠시 후 다시 시도해 주세요.';
  return STATUS_MESSAGES[response.status] ?? fallback;
}

async function postJson(path, body, fallback) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(NETWORK_ERROR);
  }
  if (!response.ok) throw new Error(await readError(response, fallback));
  return response.json();
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState(null);
  // 토큰 복원이 끝나기 전에 헤더가 "로그인"으로 깜빡이지 않게 한다.
  const [loading, setLoading] = useState(Boolean(localStorage.getItem(TOKEN_KEY)));

  useEffect(() => {
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        if (cancelled) return;
        if (response.ok) {
          setUser(await response.json());
        } else if (response.status === 401) {
          // 만료·폐기된 토큰은 남겨둘 이유가 없다.
          localStorage.removeItem(TOKEN_KEY);
          setToken(null);
          setUser(null);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  const value = useMemo(() => {
    async function login(email, password) {
      const data = await postJson('/auth/login', { email, password }, '로그인에 실패했습니다.');
      localStorage.setItem(TOKEN_KEY, data.token);
      setToken(data.token);
      setUser(data.user);
    }

    async function signup(email, password, name) {
      await postJson('/auth/signup', { email, password, name }, '회원가입에 실패했습니다.');
      try {
        await login(email, password);
      } catch {
        // 가입은 성공. 여기서 "로그인 실패"를 띄우면 재시도했다가 409를 보게 된다.
        const error = new Error('가입이 완료되었습니다. 로그인해 주세요.');
        error.signupCompleted = true;
        throw error;
      }
    }

    async function logout() {
      if (token) {
        await fetch(`${API_BASE}/auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        }).catch(() => {});
      }
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setUser(null);
    }

    return { user, token, loading, login, signup, logout };
  }, [user, token, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
