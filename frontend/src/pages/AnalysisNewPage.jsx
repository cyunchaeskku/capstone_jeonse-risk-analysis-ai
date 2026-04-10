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
                <button className="inline-flex min-w-36 items-center justify-center rounded-full border border-coral/25 bg-coral/10 px-5 py-3 text-sm font-semibold text-ink transition hover:border-coral/40 hover:bg-coral/15">
                  파일 선택
                </button>
              </div>
              <div className="mt-5 rounded-[1.5rem] border border-dashed border-coral/25 bg-sand px-5 py-8 text-sm text-slate-500">
                드래그 앤 드롭 영역. 실제 업로드 연결 전까지는 레이아웃과 상태 표시 자리만 제공합니다.
              </div>
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
