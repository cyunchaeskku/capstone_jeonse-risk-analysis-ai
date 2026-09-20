import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const inputCls =
  'rounded-lg border border-coral/20 bg-white px-3 py-2 text-sm text-ink placeholder:text-slate-400 focus:border-coral focus:outline-none';

function SignupPage() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    if (password !== passwordConfirm) {
      setError('비밀번호가 일치하지 않습니다.');
      return;
    }
    setSubmitting(true);
    try {
      await signup(email, password, name);
      navigate('/');
    } catch (err) {
      if (err.signupCompleted) {
        navigate('/login', { state: { notice: err.message } });
        return;
      }
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-md flex-col gap-6 px-6 pb-16 pt-10">
      <section className="rounded-2xl border border-coral/15 bg-white p-6 shadow-sm">
        <p className="text-xs font-semibold tracking-[0.12em] text-coral uppercase">회원가입</p>
        <h1 className="mt-2 text-xl font-semibold text-ink">계정 만들기</h1>
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
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="이름"
            maxLength={50}
            required
            className={inputCls}
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호 (8자 이상)"
            autoComplete="new-password"
            minLength={8}
            maxLength={128}
            required
            className={inputCls}
          />
          <input
            type="password"
            value={passwordConfirm}
            onChange={(e) => setPasswordConfirm(e.target.value)}
            placeholder="비밀번호 확인"
            autoComplete="new-password"
            required
            className={inputCls}
          />
          {error ? <p className="text-xs text-red-600">{error}</p> : null}
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-white transition hover:bg-[#0f523d] disabled:opacity-50"
          >
            {submitting ? '가입 중...' : '가입하기'}
          </button>
        </form>
        <p className="mt-4 text-xs text-slate-500">
          이미 계정이 있으신가요?{' '}
          <Link to="/login" className="underline hover:text-ink">
            로그인
          </Link>
        </p>
      </section>
    </main>
  );
}

export default SignupPage;
