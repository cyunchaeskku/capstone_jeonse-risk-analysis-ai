import { Link } from 'react-router-dom';

const highlights = [
  {
    title: '계약 전 위험도 진단',
    description:
      '매물 정보와 계약 관련 문서를 넣으면 핵심 위험 신호를 우선순위로 정리합니다.',
  },
  {
    title: '법률 근거 기반 설명',
    description:
      '단순 점수만 보여주지 않고 관련 법령과 해석 포인트를 함께 제시합니다.',
  },
  {
    title: '후속 질문 대응',
    description:
      '사용자가 계약 단계에서 바로 묻는 질문에 grounded answer 형태로 응답합니다.',
  },
];

const metrics = [
  { value: '2 Pages', label: '메인과 분석 시작 화면' },
  { value: 'Global Chat', label: '모든 페이지에서 동일한 대화 유지' },
  { value: 'RAG + Rule', label: '설명과 판정 계층 분리' },
];

const steps = [
  {
    number: '01',
    title: '문서와 매물 정보 입력',
    detail: '계약서, 등기부등본, 주소 정보, 보증금 조건을 한 번에 수집합니다.',
  },
  {
    number: '02',
    title: '위험 신호 구조화',
    detail: '규칙 엔진이 선순위 권리, 보증금 리스크, 문서 불일치 여부를 정리합니다.',
  },
  {
    number: '03',
    title: '설명과 후속 액션 제공',
    detail: '법률 근거 설명과 함께 무엇을 추가 확인해야 하는지 제안합니다.',
  },
];

function HomePage() {
  return (
    <main>
      <section className="mx-auto grid w-full max-w-7xl gap-14 px-6 pb-16 pt-6 lg:grid-cols-[1.15fr_0.85fr] lg:px-10 lg:pb-24 lg:pt-12">
        <div className="max-w-3xl">
          <div className="inline-flex rounded-full border border-coral/20 bg-white/80 px-4 py-2 text-sm text-slate-600 shadow-sm backdrop-blur">
            전세계약 전, 위험 신호를 먼저 읽는 분석 도구
          </div>
          <h1 className="mt-6 text-5xl font-semibold leading-tight tracking-[-0.04em] text-slate-900 md:text-6xl">
            전세사기 위험을
            <span className="block text-coral">계약 전에 구조적으로 확인합니다.</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600">
            매물 정보, 계약 문서, 법률 근거를 한 화면 안에서 연결해 보여주는 전세 리스크 분석
            서비스입니다. 판정은 규칙 기반으로, 설명은 AI로 정리해 사용자가 판단 근거를 놓치지 않도록
            설계했습니다.
          </p>
          <div className="mt-10 flex flex-col gap-4 sm:flex-row">
            <Link
              to="/analysis/new"
              className="inline-flex items-center justify-center rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
            >
              새 분석 시작하기
            </Link>
            <a
              href="#flow"
              className="inline-flex items-center justify-center rounded-full border border-slate-300 bg-white px-6 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-400 hover:text-slate-900"
            >
              어떤 정보를 확인하나요
            </a>
          </div>
          <div className="mt-12 grid gap-4 sm:grid-cols-3">
            {metrics.map((item) => (
              <div
                key={item.label}
                className="rounded-3xl border border-white/70 bg-white/75 p-5 shadow-soft backdrop-blur"
              >
                <div className="text-xl font-semibold text-slate-900">{item.value}</div>
                <div className="mt-2 text-sm leading-6 text-slate-600">{item.label}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative">
          <div className="absolute -left-6 top-10 hidden h-24 w-24 rounded-full bg-coral/20 blur-2xl lg:block" />
          <div className="rounded-[2rem] border border-white/80 bg-white/85 p-6 shadow-soft backdrop-blur">
            <div className="rounded-[1.5rem] bg-sand p-6">
              <div className="flex items-center justify-between text-sm text-slate-500">
                <span>위험도 브리핑</span>
                <span>예시 화면</span>
              </div>
              <div className="mt-6 rounded-[1.5rem] bg-white p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm text-slate-500">종합 리스크</p>
                    <p className="mt-2 text-3xl font-semibold text-slate-900">주의 필요</p>
                  </div>
                  <div className="rounded-full bg-coral/10 px-4 py-2 text-sm font-semibold text-coral">
                    High Signal
                  </div>
                </div>
                <div className="mt-6 space-y-4">
                  <div className="rounded-2xl bg-coral/8 p-4">
                    <p className="text-sm font-medium text-slate-900">선순위 권리 확인 필요</p>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      등기부상 권리관계와 보증금 규모를 함께 검토해야 합니다.
                    </p>
                  </div>
                  <div className="rounded-2xl bg-sage/10 p-4">
                    <p className="text-sm font-medium text-slate-900">설명 가능한 근거 제공</p>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      관련 법령 조문과 계약 단계 체크포인트를 함께 제안합니다.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="border-y border-slate-200/80 bg-white/70">
        <div className="mx-auto grid w-full max-w-7xl gap-6 px-6 py-14 lg:grid-cols-3 lg:px-10">
          {highlights.map((item) => (
            <article key={item.title} className="rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm">
              <p className="text-sm font-semibold tracking-[0.18em] text-coral uppercase">Core Value</p>
              <h2 className="mt-4 text-2xl font-semibold tracking-[-0.03em] text-slate-900">{item.title}</h2>
              <p className="mt-4 text-base leading-7 text-slate-600">{item.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="flow" className="mx-auto w-full max-w-7xl px-6 py-16 lg:px-10 lg:py-24">
        <div className="max-w-2xl">
          <p className="text-sm font-semibold tracking-[0.18em] text-coral uppercase">Analysis Flow</p>
          <h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em] text-slate-900">
            사용자는 복잡한 법률 문서를 직접 해석하지 않아도 됩니다.
          </h2>
          <p className="mt-5 text-lg leading-8 text-slate-600">
            입력, 판정, 설명을 분리한 구조로 화면을 설계해 결과를 빠르게 이해할 수 있도록
            구성했습니다. 이후 문서 업로드, 분석 결과, 법률 QA 화면으로 자연스럽게 확장할 수 있습니다.
          </p>
        </div>
        <div className="mt-12 grid gap-6 lg:grid-cols-3">
          {steps.map((step) => (
            <article key={step.number} className="bg-grid rounded-[2rem] border border-slate-200 bg-[size:28px_28px] p-6">
              <div className="text-sm font-semibold tracking-[0.2em] text-slate-400">{step.number}</div>
              <h3 className="mt-8 text-2xl font-semibold tracking-[-0.03em] text-slate-900">{step.title}</h3>
              <p className="mt-4 text-base leading-7 text-slate-600">{step.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="px-6 pb-16 lg:px-10 lg:pb-24">
        <div className="mx-auto max-w-7xl rounded-[2.5rem] bg-ink px-8 py-10 text-white lg:px-12 lg:py-14">
          <div className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
            <div>
              <p className="text-sm font-semibold tracking-[0.18em] text-wheat uppercase">Next Step</p>
              <h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em]">
                입력 화면과 전역 챗봇을 함께 쓰는 흐름으로 바로 넘어갈 수 있습니다.
              </h2>
            </div>
            <div className="space-y-4 text-sm leading-7 text-slate-300">
              <p>
                메인 페이지에서 분석 시작 화면으로 이동해도 같은 탭 안에서는 대화 context가 그대로
                유지됩니다. 이후 실제 API와 연결하면 분석 결과와 QA도 자연스럽게 이어집니다.
              </p>
              <Link
                to="/analysis/new"
                className="inline-flex rounded-full bg-white px-6 py-3 font-semibold text-ink transition hover:bg-slate-100"
              >
                분석 시작 페이지 보기
              </Link>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

export default HomePage;
