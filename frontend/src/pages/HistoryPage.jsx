import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { useAuth } from '../context/AuthContext';
import { GRADE_META, STATUS_META } from './AnalysisNewPage';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const KRW = new Intl.NumberFormat('ko-KR');

function formatDate(value) {
  return new Date(value).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function RecordDetail({ record }) {
  const result = record.result;
  const grade = GRADE_META[result.risk_grade] ?? GRADE_META.safe;

  return (
    <div className="border-t border-slate-100 px-6 py-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`rounded-full border px-3 py-1 text-sm font-medium ${grade.tone}`}>
          {grade.label}
        </span>
        <span className="text-sm text-slate-600">
          위험 점수 {result.risk_score} / {result.score_max}
        </span>
        <span className="text-sm text-slate-500">
          보증금 {KRW.format(record.request.deposit_krw)}원
        </span>
      </div>

      <ul className="mt-4 space-y-2">
        {result.checks.map((check) => {
          const status = STATUS_META[check.status] ?? STATUS_META.unknown;
          return (
            <li key={check.code} className="flex gap-3 text-sm">
              <span className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${status.tone}`}>
                {status.label}
              </span>
              <span className="text-slate-700">
                <strong className="font-medium text-slate-900">{check.title}</strong> — {check.reason}
              </span>
            </li>
          );
        })}
      </ul>

      {result.llm_explanation ? (
        <div className="mt-5 rounded-2xl bg-slate-50 px-5 py-4 text-sm leading-7 text-slate-700">
          <ReactMarkdown>{result.llm_explanation}</ReactMarkdown>
        </div>
      ) : null}
    </div>
  );
}

function HistoryPage() {
  const { token, loading: authLoading } = useAuth();
  const [items, setItems] = useState([]);
  const [state, setState] = useState('loading');
  const [openId, setOpenId] = useState(null);
  const [records, setRecords] = useState({});

  useEffect(() => {
    if (authLoading) return;
    if (!token) {
      setState('anonymous');
      return;
    }

    let cancelled = false;
    setState('loading');
    fetch(`${API_BASE}/analyses`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        if (cancelled) return;
        if (!response.ok) throw new Error();
        setItems(await response.json());
        setState('ready');
      })
      .catch(() => {
        if (!cancelled) setState('error');
      });

    return () => {
      cancelled = true;
    };
  }, [token, authLoading]);

  async function toggle(analysisId) {
    if (openId === analysisId) {
      setOpenId(null);
      return;
    }
    setOpenId(analysisId);
    if (records[analysisId]) return;

    const response = await fetch(`${API_BASE}/analyses/${analysisId}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => null);
    if (response?.ok) {
      const record = await response.json();
      setRecords((prev) => ({ ...prev, [analysisId]: record }));
    }
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-6 pb-20 pt-6 lg:px-10">
      <h1 className="text-3xl font-semibold tracking-[-0.03em] text-slate-900">분석 기록</h1>
      <p className="mt-3 text-slate-600">
        로그인한 계정으로 실행한 위험도 분석이 최근 순으로 쌓입니다.
      </p>

      {state === 'anonymous' ? (
        <p className="mt-10 rounded-2xl border border-white/80 bg-white/70 px-6 py-8 text-center text-slate-600 shadow-sm backdrop-blur">
          기록을 보려면{' '}
          <Link to="/login" className="font-medium text-coral">
            로그인
          </Link>
          이 필요합니다.
        </p>
      ) : null}

      {state === 'loading' ? <p className="mt-10 text-slate-500">불러오는 중…</p> : null}
      {state === 'error' ? (
        <p className="mt-10 text-slate-600">기록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</p>
      ) : null}

      {state === 'ready' && items.length === 0 ? (
        <p className="mt-10 rounded-2xl border border-white/80 bg-white/70 px-6 py-8 text-center text-slate-600 shadow-sm backdrop-blur">
          아직 분석 기록이 없습니다.{' '}
          <Link to="/analysis/new" className="font-medium text-coral">
            새 분석
          </Link>
          을 실행해 보세요.
        </p>
      ) : null}

      <ul className="mt-8 space-y-4">
        {items.map((item) => {
          const grade = GRADE_META[item.risk_grade] ?? GRADE_META.safe;
          const record = records[item.analysis_id];
          return (
            <li
              key={item.analysis_id}
              className="overflow-hidden rounded-3xl border border-white/80 bg-white/70 shadow-sm backdrop-blur"
            >
              <button
                type="button"
                onClick={() => toggle(item.analysis_id)}
                className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left transition hover:bg-white/60"
              >
                <div>
                  <p className="font-medium text-slate-900">{item.listing_name}</p>
                  <p className="mt-1 text-sm text-slate-500">
                    {formatDate(item.created_at)} · 보증금 {KRW.format(item.deposit_krw)}원
                  </p>
                </div>
                <span className={`shrink-0 rounded-full border px-3 py-1 text-sm font-medium ${grade.tone}`}>
                  {grade.label} {item.risk_score}점
                </span>
              </button>
              {openId === item.analysis_id && record ? <RecordDetail record={record} /> : null}
            </li>
          );
        })}
      </ul>
    </main>
  );
}

export default HistoryPage;
