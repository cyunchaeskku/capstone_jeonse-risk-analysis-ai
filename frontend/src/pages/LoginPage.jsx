import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const inputCls =
  'rounded-lg border border-coral/20 bg-white px-3 py-2 text-sm text-ink placeholder:text-slate-400 focus:border-coral focus:outline-none';

function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-md flex-col gap-6 px-6 pb-16 pt-10">
      <section className="rounded-2xl border border-coral/15 bg-white p-6 shadow-sm">
        <p className="text-xs font-semibold tracking-[0.12em] text-coral uppercase">로그인</p>
        <h1 className="mt-2 text-xl font-semibold text-ink">다시 오셨군요</h1>
        <form className="mt-5 flex flex-col gap-3" onSubmit={handleSubmit}>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="이메일"
            autoComplete="email"
            required
            className={inputCls}
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호"
            autoComplete="current-password"
            required
            className={inputCls}
          />
          {error ? <p className="text-xs text-red-600">{error}</p> : null}
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-white transition hover:bg-[#0f523d] disabled:opacity-50"
          >
            {submitting ? '로그인 중...' : '로그인'}
          </button>
        </form>
        <p className="mt-4 text-xs text-slate-500">
          계정이 없으신가요?{' '}
          <Link to="/signup" className="underline hover:text-ink">
            회원가입
          </Link>
        </p>
      </section>
    </main>
  );
}

export default LoginPage;
