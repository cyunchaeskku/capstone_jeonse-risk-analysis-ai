import { useRef, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const uploadSections = [
  {
    title: '계약서 초안 또는 사본',
    description: '특약, 계약 당사자 정보, 보증금과 잔금 일정을 확인하기 위한 문서 영역입니다.',
  },
  {
    title: '등기부등본',
    description: '소유권과 선순위 권리관계를 우선 검토하기 위한 핵심 문서입니다.',
  },
  {
    title: '추가 확인 자료',
    description: '건축물대장, 중개사 설명자료, 임대인 신분 확인 자료 등을 추가할 수 있습니다.',
  },
];

const checklist = [
  '주소와 계약서 기재 주소가 일치하는지 확인',
  '보증금, 계약금, 잔금 일정이 명확한지 확인',
  '등기부상 소유자와 계약 당사자가 동일한지 확인',
];

function AnalysisNewPage() {
  const registryInputRef = useRef(null);
  const [registryFileName, setRegistryFileName] = useState('');
  const [registryParseResult, setRegistryParseResult] = useState(null);
  const [registryUploadStatus, setRegistryUploadStatus] = useState('idle');
  const [registryError, setRegistryError] = useState('');

  const isRegistryUploading = registryUploadStatus === 'uploading';

  async function handleRegistryFileChange(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    setRegistryFileName(file.name);
    setRegistryParseResult(null);
    setRegistryError('');

    if (file.type && file.type !== 'application/pdf') {
      setRegistryUploadStatus('idle');
      setRegistryError('PDF 파일만 업로드할 수 있습니다.');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    setRegistryUploadStatus('uploading');

    try {
      const response = await fetch(`${API_BASE}/registry/inspect`, {
        method: 'POST',
        body: formData,
      });
      const payload = await response.json().catch(() => ({}));

      if (!response.ok) {
        const message =
          typeof payload.detail === 'string'
            ? payload.detail
            : payload.detail?.message ?? `업로드 실패 (${response.status})`;
        throw new Error(message);
      }

      setRegistryParseResult(payload);
      setRegistryUploadStatus(payload.status ?? 'needs_review');
    } catch (error) {
      setRegistryUploadStatus('idle');
      setRegistryError(error instanceof Error ? error.message : '등기부등본 파싱에 실패했습니다.');
    } finally {
      event.target.value = '';
    }
  }

  function formatKrw(value) {
    if (value === null || value === undefined) return '-';
    return `${Number(value).toLocaleString('ko-KR')}원`;
  }

  function renderUploadAction(section) {
    if (section.title !== '등기부등본') {
      return (
        <button
          type="button"
          className="inline-flex min-w-36 items-center justify-center rounded-full border border-coral/25 bg-coral/10 px-5 py-3 text-sm font-semibold text-ink transition hover:border-coral/40 hover:bg-coral/15"
        >
          준비 중
        </button>
      );
    }

    return (
      <>
        <input
          ref={registryInputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          onChange={handleRegistryFileChange}
        />
        <button
          type="button"
          onClick={() => registryInputRef.current?.click()}
          disabled={isRegistryUploading}
          className="inline-flex min-w-36 items-center justify-center rounded-full border border-coral/25 bg-coral/10 px-5 py-3 text-sm font-semibold text-ink transition hover:border-coral/40 hover:bg-coral/15 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isRegistryUploading ? '분석 중' : 'PDF 선택'}
        </button>
      </>
    );
  }

  function renderUploadState(section) {
    if (section.title !== '등기부등본') {
      return (
        <div className="mt-5 rounded-[1.5rem] border border-dashed border-coral/25 bg-sand px-5 py-8 text-sm text-slate-500">
          이후 단계에서 연결할 문서 영역입니다.
        </div>
      );
    }

    return (
      <div className="mt-5 rounded-[1.5rem] border border-dashed border-coral/25 bg-sand px-5 py-6">
        <div className="flex flex-col gap-2 text-sm text-slate-600">
          <span>{registryFileName || '등기사항증명서 PDF를 선택하세요.'}</span>
          {isRegistryUploading && <span className="font-medium text-ink">업로드 후 채권최고액 추출 중</span>}
          {registryError && <span className="font-medium text-red-600">{registryError}</span>}
        </div>

        {registryParseResult && (
          <div className="mt-5 rounded-2xl border border-sage/20 bg-white p-5">
            <p className="text-xs font-semibold tracking-[0.16em] text-sage uppercase">Parsed Result</p>
            <div className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-ink">
              {formatKrw(registryParseResult.max_claim_amount_krw)}
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-600">{registryParseResult.message}</p>
            {registryParseResult.max_claim_amounts?.length > 0 && (
              <div className="mt-4 space-y-2">
                {registryParseResult.max_claim_amounts.map((item, index) => (
                  <div
                    key={`${item.amount_krw}-${index}`}
                    className="flex flex-col gap-1 rounded-xl bg-sand px-4 py-3 text-sm text-slate-700 md:flex-row md:items-center md:justify-between"
                  >
                    <span>{item.raw_text}</span>
                    <span className="font-semibold text-ink">{formatKrw(item.amount_krw)}</span>
                  </div>
                ))}
              </div>
            )}
            {registryParseResult.inspection?.findings?.length > 0 && (
              <div className="mt-5 border-t border-sage/10 pt-5">
                <p className="text-sm font-semibold text-ink">특이사항</p>
                <div className="mt-3 space-y-3">
                  {registryParseResult.inspection.findings.map((finding, index) => (
                    <div key={`${finding.title}-${index}`} className="rounded-xl bg-sand px-4 py-3">
                      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                        <p className="font-semibold text-ink">{finding.title}</p>
                        <span className="w-fit rounded-full bg-white px-3 py-1 text-xs font-semibold text-sage">
                          {finding.severity}
                        </span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate-700">{finding.explanation}</p>
                      {finding.recommended_action && (
                        <p className="mt-2 text-sm font-medium leading-6 text-ink">{finding.recommended_action}</p>
                      )}
                      {finding.evidence && (
                        <p className="mt-2 text-xs leading-5 text-slate-500">근거: {finding.evidence}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <main className="mx-auto w-full max-w-7xl px-6 pb-20 pt-6 lg:px-10 lg:pb-24 lg:pt-10">
      <section className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
        <div>
          <div className="inline-flex rounded-full border border-sage/20 bg-white/80 px-4 py-2 text-sm text-slate-600 shadow-sm">
            새 분석 시작
          </div>
          <h1 className="mt-6 text-5xl font-semibold tracking-[-0.04em] text-slate-900">
            문서를 먼저 올리고
            <span className="block text-sage">위험 검토 흐름을 준비합니다.</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600">
            이 화면은 실제 업로드 경험을 염두에 둔 시작 페이지입니다. 현재 단계에서는 UI만 먼저
            구성하고, 이후 백엔드 연결 시 업로드 상태와 분석 요청 생성으로 확장합니다.
          </p>
        </div>

        <aside className="rounded-[2rem] border border-white/80 bg-white/85 p-6 shadow-soft">
          <p className="text-sm font-semibold tracking-[0.18em] text-coral uppercase">Quick Checklist</p>
          <div className="mt-5 space-y-3">
            {checklist.map((item) => (
              <div key={item} className="rounded-2xl bg-sand p-4 text-sm leading-6 text-slate-700">
                {item}
              </div>
            ))}
          </div>
        </aside>
      </section>

      <section className="mt-12 grid gap-8 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          {uploadSections.map((section) => (
            <article key={section.title} className="rounded-[2rem] border border-coral/15 bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
                <div className="max-w-xl">
                  <p className="text-sm font-semibold tracking-[0.18em] text-coral uppercase">Upload Zone</p>
                  <h2 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-slate-900">
                    {section.title}
                  </h2>
                  <p className="mt-3 text-base leading-7 text-slate-600">{section.description}</p>
                </div>
                {renderUploadAction(section)}
              </div>
              {renderUploadState(section)}
            </article>
          ))}
        </div>

        <aside className="h-fit rounded-[2rem] border border-coral/15 bg-white p-6 shadow-sm">
          <p className="text-sm font-semibold tracking-[0.18em] text-coral uppercase">Draft Inputs</p>
          <div className="mt-5 space-y-4">
            <div>
              <label className="text-sm font-medium text-slate-700">매물 주소</label>
              <div className="mt-2 rounded-2xl border border-coral/15 bg-sand px-4 py-3 text-sm text-slate-400">
                서울시 강남구 예시로 00
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700">보증금</label>
              <div className="mt-2 rounded-2xl border border-coral/15 bg-sand px-4 py-3 text-sm text-slate-400">
                000,000,000원
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700">계약 예정일</label>
              <div className="mt-2 rounded-2xl border border-coral/15 bg-sand px-4 py-3 text-sm text-slate-400">
                YYYY.MM.DD
              </div>
            </div>
          </div>
          <button className="mt-8 w-full rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#0f523d]">
            분석 준비 시작
          </button>
        </aside>
      </section>
    </main>
  );
}

export default AnalysisNewPage;
