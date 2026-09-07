import { useMemo, useRef, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// docs/전세사기위험도판별핵심로직.md §3 규칙 카탈로그를 그대로 단계로 옮긴 것.
// source: B = 등기부 PDF 업로드, C = 사용자 수기 입력.
// R9(보증보험)는 공식 API가 없어 이 흐름에서 제외한다.
const STEPS = [
  {
    id: 'R1',
    source: 'C',
    title: '전세가율',
    code: 'deposit_to_market_ratio',
    criterion: '보증금 / 시세 > 80% → 위험',
  },
  {
    id: 'R2',
    source: 'B',
    title: '근저당 비율',
    code: 'mortgage_ratio',
    criterion: '채권최고액 / 시세 > 60% → 위험, (채권최고액 + 보증금) / 시세 > 80% → 위험',
  },
  {
    id: 'R3',
    source: 'C',
    title: '소유자 일치',
    code: 'owner_mismatch',
    criterion: '계약서상 임대인 ≠ 등기부 소유자 → 위험 (공동소유는 전원 포함)',
  },
  {
    id: 'R4',
    source: 'B',
    title: '권리침해 등기',
    code: 'rights_encumbrance',
    criterion: '압류·가압류·가처분·가등기·경매·신탁이 미말소면 즉시 고위험',
  },
  {
    id: 'R5',
    source: 'C',
    title: '건축물 용도',
    code: 'residential_use',
    criterion: '주용도에 주거 관련 용도가 없으면 위험',
  },
  {
    id: 'R6',
    source: 'C',
    title: '위반건축물',
    code: 'illegal_building',
    criterion: '건축물대장 위반건축물 표시 → 위험 (보증보험 거절 사유)',
  },
  {
    id: 'R7',
    source: 'C',
    title: '중복 계약 집중도',
    code: 'duplicate_contract',
    criterion: '동일 건물 최근 12개월 순수 전세 5건 이상 → 주의',
  },
  {
    id: 'R8',
    source: 'C',
    title: '선순위 보증금',
    code: 'senior_deposit',
    criterion: '일반건물 전용. (선순위 보증금 + 채권최고액 + 보증금) / 시세 > 80% → 위험',
  },
];

const SOURCE_LABEL = {
  B: '등기부 PDF 업로드',
  C: '직접 입력',
};

// 원래는 공공 API(출처 A)에서 채워야 하는 값이라 임시 기본값을 둔다.
const INITIAL_FORM = {
  listingName: '',
  depositKrw: '',
  contractOwnerName: '',
  buildingType: '공동주택',
  detailUse: '다세대주택',
  illegalBuildingStatus: 'unclear',
  recentJeonseCount: '2',
  seniorDepositKrw: '0',
};

const PROPERTY_TYPES = [
  { value: 'apt', label: '아파트' },
  { value: 'offi', label: '오피스텔' },
  { value: 'rh', label: '연립/다세대' },
  { value: 'sh', label: '단독/다가구' },
];

// 시세를 어디서 얻었는지 화면에 그대로 드러낸다. 추정치를 실거래가처럼 보이게 하면 안 된다.
const PRICE_SOURCE_LABEL = {
  'actual-trade-transaction': '매매 실거래가',
  'official-price-x140': '공시가격 × 140%',
  unavailable: '확인 불가',
};

const VIOLATION_META = {
  present: { label: '위반건축물 표시 있음', tone: 'text-red-700' },
  absent: { label: '위반건축물 표시 없음', tone: 'text-emerald-700' },
  unclear: { label: '판독 불가 — 직접 확인 필요', tone: 'text-slate-700' },
};

const GRADE_META = {
  safe: { label: '안전', tone: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
  caution: { label: '주의', tone: 'text-amber-700 bg-amber-50 border-amber-200' },
  risk: { label: '위험', tone: 'text-orange-700 bg-orange-50 border-orange-200' },
  high_risk: { label: '고위험', tone: 'text-red-700 bg-red-50 border-red-200' },
};

const STATUS_META = {
  pass: { label: '통과', tone: 'bg-emerald-50 text-emerald-700' },
  warn: { label: '주의', tone: 'bg-amber-50 text-amber-700' },
  fail: { label: '위험', tone: 'bg-red-50 text-red-700' },
  unknown: { label: '판단 불가', tone: 'bg-slate-100 text-slate-600' },
};

const REGISTRY_TYPE_LABEL = {
  aggregate_building: '집합건물 (아파트·빌라·오피스텔)',
  general_building: '일반건물 (단독·다가구)',
  land: '토지',
  unknown: '확인 불가',
};

function toKrw(value) {
  const parsed = Number(String(value).replace(/[^0-9]/g, ''));
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatKrw(value) {
  if (value === null || value === undefined) return '-';
  return `${Number(value).toLocaleString('ko-KR')}원`;
}

function sumActiveMortgages(inspection) {
  const mortgages = inspection?.rights_section?.mortgages ?? [];
  // is_cancelled가 null이면 말소 여부 불확실 → 보수적으로 유효로 간주한다.
  return mortgages
    .filter((item) => item?.is_cancelled !== true)
    .reduce((acc, item) => acc + toKrw(item?.amount_krw ?? 0), 0);
}

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-2 block text-xs leading-5 text-slate-500">{hint}</span>}
    </label>
  );
}

const inputClass =
  'mt-2 w-full rounded-2xl border border-coral/20 bg-white px-4 py-3 text-base text-slate-900 outline-none transition focus:border-sage/60';

function AnalysisNewPage() {
  const [stepIndex, setStepIndex] = useState(0);
  const [form, setForm] = useState(INITIAL_FORM);
  const [registry, setRegistry] = useState(null);
  const [registryFileName, setRegistryFileName] = useState('');
  const [registryStatus, setRegistryStatus] = useState('idle');
  const [registryError, setRegistryError] = useState('');
  const [result, setResult] = useState(null);
  const [submitState, setSubmitState] = useState('idle');
  const [submitError, setSubmitError] = useState('');
  const fileInputRef = useRef(null);

  // R1 매물 특정 — ① 주소 검색 → ② 건물 확정 → ③ 세대 선택 순으로만 열린다.
  const [propertyType, setPropertyType] = useState('rh');
  const [placeQuery, setPlaceQuery] = useState('');
  const [places, setPlaces] = useState([]);
  const [selectedPlace, setSelectedPlace] = useState(null);
  const [lookup, setLookup] = useState(null);
  const [unitDong, setUnitDong] = useState('');
  const [unitKey, setUnitKey] = useState('');
  const [lookupState, setLookupState] = useState('idle');
  const [lookupError, setLookupError] = useState('');

  // R6 건축물대장 — 위반건축물 표시는 공공 API에 없어 대장 원본을 판독해야 한다.
  const [ledger, setLedger] = useState(null);
  const [ledgerFileName, setLedgerFileName] = useState('');
  const [ledgerStatus, setLedgerStatus] = useState('idle');
  const [ledgerError, setLedgerError] = useState('');
  const ledgerInputRef = useRef(null);

  const step = STEPS[stepIndex];
  const isLastStep = stepIndex === STEPS.length - 1;

  const inspection = registry?.inspection ?? null;
  const registryType = inspection?.property_section?.registry_type ?? 'unknown';
  const registryOwnerName = inspection?.ownership_section?.current_owner?.name ?? '';
  const criticalTerms = inspection?.ownership_section?.critical_terms ?? [];
  const mortgageTotalKrw = useMemo(() => sumActiveMortgages(inspection), [inspection]);

  function update(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  // R5·R7은 R1에서 이미 받아온 건축물대장·실거래가로 채워진다. 다시 묻지 않는다.
  const selectedBuilding = lookup?.building?.selected ?? null;
  const autoJeonseCount = (lookup?.rent?.items ?? []).filter(
    (item) => toKrw(item?.monthlyRent) === 0,
  ).length;

  // 다른 건물의 대장을 올렸는지 지번으로 대조한다. 비전 모델이 주소를 지어내는 경우도 있어
  // 판독값을 그대로 믿지 않고 R1 조회 결과와 맞춰 본다.
  const ledgerLotAddress = ledger?.inspection?.lot_address ?? '';
  const ledgerAddressMismatch = Boolean(
    ledgerLotAddress && lookup?.query && !ledgerLotAddress.replace(/\s/g, '').includes(
      (lookup.query.match(/\d+(-\d+)?$/) ?? [''])[0],
    ),
  );

  const units = lookup?.official_price?.units ?? [];
  const dongList = useMemo(() => [...new Set(units.map((unit) => unit.dong))], [units]);
  const selectedUnit = units.find((unit) => `${unit.dong}/${unit.ho}` === unitKey) ?? null;

  // 시세 사다리: ① 매매 실거래가 → ② 공시가격 × 140% → ③ 확인 불가.
  // 실거래가가 잡히면 세대를 고를 필요가 없다.
  const tradePriceKrw = toKrw(lookup?.market_price?.price_krw ?? 0);
  const hasTradePrice = tradePriceKrw > 0 && lookup?.market_price?.source === 'actual-trade-transaction';
  const marketPriceKrw = hasTradePrice ? tradePriceKrw : (selectedUnit?.estimated_price_krw ?? 0);
  const priceSource = hasTradePrice
    ? 'actual-trade-transaction'
    : (selectedUnit ? 'official-price-x140' : 'unavailable');

  function resetLookup() {
    setLookup(null);
    setUnitDong('');
    setUnitKey('');
    setLookupError('');
    update('listingName', '');
  }

  async function searchPlaces() {
    if (!placeQuery.trim()) return;
    setLookupState('searching');
    setPlaces([]);
    setSelectedPlace(null);
    resetLookup();
    try {
      const response = await fetch(`${API_BASE}/addresses/resolve?query=${encodeURIComponent(placeQuery.trim())}`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail ?? '주소를 해석하지 못했습니다.');
      const items = payload.items ?? [];
      setPlaces(items);
      if (!items.length) {
        setLookupError('찾지 못했습니다. 시·도부터 포함한 지번 주소로 넣어 보세요. (예: 경기도 수원시 권선구 탑동 814-2)');
      } else if (items.length === 1) {
        // 지번·도로명은 후보가 하나뿐이라 고르게 할 이유가 없다.
        // await하지 않으면 아래 finally가 로딩 표시를 먼저 꺼버린다.
        await selectPlace(items[0]);
      }
    } catch (error) {
      setLookupError(error instanceof Error ? error.message : '장소 검색에 실패했습니다.');
    } finally {
      setLookupState('idle');
    }
  }

  async function selectPlace(place) {
    setSelectedPlace(place);
    setLookupState('loading');
    resetLookup();
    try {
      const params = new URLSearchParams({
        query: place.address || place.roadAddress,
        building_name: place.title,
        property_type: propertyType,
      });
      const response = await fetch(`${API_BASE}/listing-checks/search?${params}`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail ?? '건물 정보를 가져오지 못했습니다.');
      setLookup(payload);
      const found = payload.official_price?.units ?? [];
      // 세대가 하나뿐이면 고를 게 없다.
      if (found.length === 1) {
        setUnitDong(found[0].dong);
        setUnitKey(`${found[0].dong}/${found[0].ho}`);
      }
      const building = payload.building?.selected ?? null;
      update('listingName', building?.building_name || place.title);
      if (building?.building_type) update('buildingType', building.building_type);
      if (building?.detail_use) update('detailUse', building.detail_use);
      const jeonseCount = (payload.rent?.items ?? []).filter(
        (item) => toKrw(item?.monthlyRent) === 0,
      ).length;
      update('recentJeonseCount', String(jeonseCount));
    } catch (error) {
      setLookupError(error instanceof Error ? error.message : '건물 정보를 가져오지 못했습니다.');
    } finally {
      setLookupState('idle');
    }
  }

  async function handleRegistryUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    setRegistryFileName(file.name);
    setRegistryError('');
    setRegistry(null);

    if (file.type && file.type !== 'application/pdf') {
      setRegistryStatus('idle');
      setRegistryError('PDF 파일만 업로드할 수 있습니다.');
      event.target.value = '';
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    setRegistryStatus('uploading');

    try {
      const response = await fetch(`${API_BASE}/registry/inspect`, { method: 'POST', body: formData });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message =
          typeof payload.detail === 'string'
            ? payload.detail
            : (payload.detail?.message ?? `업로드 실패 (${response.status})`);
        throw new Error(message);
      }
      setRegistry(payload);
      setRegistryStatus('done');
    } catch (error) {
      setRegistryStatus('idle');
      setRegistryError(error instanceof Error ? error.message : '등기부등본 분석에 실패했습니다.');
    } finally {
      event.target.value = '';
    }
  }

  async function handleLedgerUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    setLedgerFileName(file.name);
    setLedgerError('');
    setLedger(null);

    if (file.type && file.type !== 'application/pdf') {
      setLedgerStatus('idle');
      setLedgerError('PDF 파일만 업로드할 수 있습니다.');
      event.target.value = '';
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    setLedgerStatus('uploading');

    try {
      const response = await fetch(`${API_BASE}/building-register/inspect`, { method: 'POST', body: formData });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message =
          typeof payload.detail === 'string' ? payload.detail : `업로드 실패 (${response.status})`;
        throw new Error(message);
      }
      setLedger(payload);
      setLedgerStatus('done');
      update('illegalBuildingStatus', payload.inspection?.violation_status ?? 'unclear');
    } catch (error) {
      setLedgerStatus('idle');
      setLedgerError(error instanceof Error ? error.message : '건축물대장 판독에 실패했습니다.');
    } finally {
      event.target.value = '';
    }
  }

  function canProceed() {
    if (step.id === 'R1') {
      // 시세는 0이어도 넘어간다. 확인 불가는 unknown으로 정직하게 판정되는 게 맞다.
      return Boolean(lookup) && toKrw(form.depositKrw) > 0;
    }
    return true;
  }

  async function submit() {
    setSubmitState('loading');
    setSubmitError('');
    try {
      const response = await fetch(`${API_BASE}/risk/assess`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          listing_name: form.listingName.trim(),
          deposit_krw: toKrw(form.depositKrw),
          market_price_krw: marketPriceKrw,
          registry_type: registryType === 'land' ? 'unknown' : registryType,
          mortgage_total_krw: mortgageTotalKrw,
          registry_owner_name: registryOwnerName,
          contract_owner_name: form.contractOwnerName.trim(),
          critical_terms: criticalTerms,
          building_type: form.buildingType.trim(),
          detail_use: form.detailUse.trim(),
          illegal_building_status: form.illegalBuildingStatus,
          recent_jeonse_count: Number(form.recentJeonseCount) || 0,
          senior_deposit_krw: toKrw(form.seniorDepositKrw),
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message =
          typeof payload.detail === 'string' ? payload.detail : `분석 실패 (${response.status})`;
        throw new Error(message);
      }
      setResult(payload);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '위험도 분석에 실패했습니다.');
    } finally {
      setSubmitState('idle');
    }
  }

  function restart() {
    setStepIndex(0);
    setForm(INITIAL_FORM);
    setRegistry(null);
    setRegistryFileName('');
    setRegistryStatus('idle');
    setRegistryError('');
    setResult(null);
    setSubmitError('');
    setPlaceQuery('');
    setPlaces([]);
    setSelectedPlace(null);
    setLookup(null);
    setUnitDong('');
    setUnitKey('');
    setLookupError('');
    setLedger(null);
    setLedgerFileName('');
    setLedgerStatus('idle');
    setLedgerError('');
  }

  if (result) {
    return <ResultView result={result} onRestart={restart} />;
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-6 pb-20 pt-6 lg:px-10 lg:pb-24 lg:pt-10">
      <ol className="flex flex-wrap gap-2">
        {STEPS.map((item, index) => (
          <li
            key={item.id}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              index === stepIndex
                ? 'bg-ink text-white'
                : index < stepIndex
                  ? 'bg-sage/20 text-ink'
                  : 'bg-sand text-slate-400'
            }`}
          >
            {item.id}
          </li>
        ))}
      </ol>

      <section className="mt-6 rounded-[2rem] border border-coral/15 bg-white p-6 shadow-sm lg:p-8">
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded-full bg-coral/10 px-3 py-1 text-xs font-semibold text-coral">
            {step.id} · {SOURCE_LABEL[step.source]}
          </span>
          <span className="text-xs text-slate-400">
            {stepIndex + 1} / {STEPS.length}
          </span>
        </div>
        <h1 className="mt-4 text-3xl font-semibold tracking-[-0.03em] text-slate-900">{step.title}</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">{step.criterion}</p>

        <div className="mt-8 space-y-6">
          {step.id === 'R1' && (
            <>
              <Field
                label="① 주소 검색"
                hint="지번·도로명은 바로 확정되고, 건물명은 후보 목록에서 고릅니다."
              >
                <div className="mt-2 flex gap-2">
                  <select
                    className={`${inputClass} mt-0 w-40 shrink-0`}
                    value={propertyType}
                    onChange={(event) => {
                      setPropertyType(event.target.value);
                      resetLookup();
                    }}
                  >
                    {PROPERTY_TYPES.map((type) => (
                      <option key={type.value} value={type.value}>{type.label}</option>
                    ))}
                  </select>
                  <input
                    className={`${inputClass} mt-0`}
                    value={placeQuery}
                    onChange={(event) => setPlaceQuery(event.target.value)}
                    onKeyDown={(event) => event.key === 'Enter' && searchPlaces()}
                    placeholder="예) 경기도 수원시 권선구 탑동 814-2"
                  />
                  <button
                    type="button"
                    onClick={searchPlaces}
                    disabled={lookupState !== 'idle'}
                    className="mt-0 shrink-0 rounded-2xl bg-slate-900 px-5 py-3 text-sm font-medium text-white disabled:opacity-40"
                  >
                    {lookupState === 'searching' ? '검색 중' : '검색'}
                  </button>
                </div>
              </Field>

              {places.length > 0 && (
                <ul className="space-y-2">
                  {places.map((place) => {
                    const active = selectedPlace?.title === place.title && selectedPlace?.address === place.address;
                    return (
                      <li key={`${place.title}-${place.address}`}>
                        <button
                          type="button"
                          onClick={() => selectPlace(place)}
                          className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                            active ? 'border-sage bg-sage/10' : 'border-coral/20 bg-white hover:border-sage/50'
                          }`}
                        >
                          <span className="block text-sm font-medium text-slate-900">{place.title}</span>
                          <span className="mt-1 block text-xs text-slate-500">
                            {place.address || place.roadAddress}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}

              {lookupError && (
                <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">{lookupError}</p>
              )}

              {lookupState === 'loading' && (
                <p className="text-sm text-slate-500">건물·공시가격을 조회하는 중입니다…</p>
              )}

              {lookup && (
                <div className="rounded-2xl border border-coral/20 bg-white p-4">
                  <span className="text-xs font-medium uppercase tracking-wide text-slate-400">② 건물 확정</span>
                  <p className="mt-2 text-base font-semibold text-slate-900">
                    {lookup.building?.selected?.building_name || form.listingName || '건축물대장 정보 없음'}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {lookup.building?.selected?.lot_address || lookup.query}
                  </p>
                  {lookup.official_price?.pnu && (
                    <p className="mt-1 text-xs text-slate-400">PNU {lookup.official_price.pnu}</p>
                  )}
                </div>
              )}

              {lookup && units.length > 0 && !hasTradePrice && (
                <Field
                  label="③ 세대 선택"
                  hint="공시가격은 세대마다 다릅니다. 파크뷰는 같은 건물에서도 27% 차이가 납니다."
                >
                  <div className="mt-2 flex gap-2">
                    {dongList.length > 1 && (
                      <select
                        className={`${inputClass} mt-0 w-32 shrink-0`}
                        value={unitDong}
                        onChange={(event) => {
                          setUnitDong(event.target.value);
                          setUnitKey('');
                        }}
                      >
                        <option value="" disabled>동</option>
                        {dongList.map((dong) => (
                          <option key={dong} value={dong}>{dong}동</option>
                        ))}
                      </select>
                    )}
                    <select
                      className={`${inputClass} mt-0`}
                      value={unitKey}
                      onChange={(event) => setUnitKey(event.target.value)}
                    >
                      <option value="" disabled>호수를 선택하세요</option>
                      {units
                        .filter((unit) => dongList.length <= 1 || unit.dong === unitDong)
                        .map((unit) => (
                          <option key={`${unit.dong}/${unit.ho}`} value={`${unit.dong}/${unit.ho}`}>
                            {unit.ho}호 · {unit.floor}층 · {unit.area_m2}㎡
                          </option>
                        ))}
                    </select>
                  </div>
                </Field>
              )}

              {lookup && units.length === 0 && !hasTradePrice && (
                <p className="rounded-2xl bg-slate-100 px-4 py-3 text-sm leading-6 text-slate-600">
                  이 건물은 매매 실거래가도, 공시가격도 없습니다. 고시원·사무소처럼 주택이 아닌 건물은
                  공시가격 부여 대상이 아닙니다. 시세를 확인할 수 없어 전세가율·근저당 비율은
                  <strong className="font-semibold"> 판단 불가</strong>로 처리되고, R8(선순위 보증금)로 평가합니다.
                </p>
              )}

              {lookup?.official_price?.truncated && !selectedUnit && (
                <p className="rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
                  세대가 너무 많아 목록이 잘렸습니다. 동을 먼저 고르면 정확히 좁혀집니다.
                </p>
              )}

              {lookup && (
                <div className="rounded-2xl border border-coral/20 bg-cream/40 p-4">
                  <span className="text-sm text-slate-600">주택 시세</span>
                  <p className="mt-1 text-2xl font-semibold tracking-[-0.02em] text-slate-900">
                    {marketPriceKrw > 0 ? formatKrw(marketPriceKrw) : '확인 불가'}
                  </p>
                  <p className="mt-2 text-xs text-slate-500">
                    근거 · {PRICE_SOURCE_LABEL[priceSource]}
                    {selectedUnit && priceSource === 'official-price-x140' &&
                      ` (${selectedUnit.stdr_year}년 ${formatKrw(selectedUnit.official_price_krw)})`}
                  </p>
                </div>
              )}

              <Field label="내 보증금 (원)" hint="계약 전이라 어디에도 기록이 없는 값이라 직접 입력받습니다.">
                <input
                  className={inputClass}
                  inputMode="numeric"
                  value={form.depositKrw}
                  onChange={(event) => update('depositKrw', event.target.value)}
                  placeholder="44000000"
                />
              </Field>
            </>
          )}

          {step.id === 'R2' && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                className="sr-only"
                onChange={handleRegistryUpload}
              />
              <div className="rounded-[1.5rem] border border-dashed border-coral/25 bg-sand px-5 py-8 text-center">
                <p className="text-sm text-slate-600">
                  {registryFileName || '등기사항전부증명서 PDF를 업로드하세요.'}
                </p>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={registryStatus === 'uploading'}
                  className="mt-4 rounded-full border border-coral/25 bg-white px-5 py-3 text-sm font-semibold text-ink transition hover:border-coral/40 disabled:opacity-60"
                >
                  {registryStatus === 'uploading' ? '분석 중…' : 'PDF 선택'}
                </button>
                <p className="mt-3 text-xs leading-5 text-slate-500">
                  이 한 번의 업로드로 R2 채권최고액, R3 소유자명, R4 권리침해 등기를 함께 추출합니다.
                </p>
                {registryError && <p className="mt-3 text-sm font-medium text-red-600">{registryError}</p>}
              </div>

              {inspection && (
                <dl className="space-y-2 rounded-2xl border border-sage/20 bg-white p-5 text-sm">
                  <div className="flex justify-between gap-4">
                    <dt className="text-slate-500">등기 유형</dt>
                    <dd className="font-semibold text-ink">
                      {REGISTRY_TYPE_LABEL[registryType] ?? registryType}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-slate-500">유효 채권최고액 합계</dt>
                    <dd className="font-semibold text-ink">{formatKrw(mortgageTotalKrw)}</dd>
                  </div>
                  {registryType === 'general_building' && (
                    <p className="pt-2 text-xs leading-5 text-amber-700">
                      일반건물은 건물 전체가 하나의 등기라 호실 시세가 없습니다. 근저당 비율(R2)은
                      판단 불가로 처리되고, 대신 R8 선순위 보증금으로 평가합니다.
                    </p>
                  )}
                </dl>
              )}
            </>
          )}

          {step.id === 'R3' && (
            <>
              <div className="rounded-2xl bg-sand px-5 py-4 text-sm">
                <span className="text-slate-500">등기부상 소유자</span>
                <p className="mt-1 text-lg font-semibold text-ink">
                  {registryOwnerName || '등기부 미제출 — 판단 불가'}
                </p>
              </div>
              <Field label="계약서상 임대인명" hint="공동소유라면 계약 당사자 전원을 쉼표로 구분해 입력하세요.">
                <input
                  className={inputClass}
                  value={form.contractOwnerName}
                  onChange={(event) => update('contractOwnerName', event.target.value)}
                  placeholder="예) 홍길동, 김영희"
                />
              </Field>
            </>
          )}

          {step.id === 'R4' && (
            <div className="rounded-2xl border border-sage/20 bg-white p-5">
              {!inspection && <p className="text-sm text-slate-500">등기부가 제출되지 않아 판단할 수 없습니다.</p>}
              {inspection && criticalTerms.length === 0 && (
                <p className="text-sm text-emerald-700">
                  말소되지 않은 압류·가압류·가처분·가등기·경매·신탁 등기가 발견되지 않았습니다.
                </p>
              )}
              {criticalTerms.map((term, index) => (
                <div key={`${term.term}-${index}`} className="mb-3 rounded-xl bg-sand px-4 py-3 last:mb-0">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-semibold text-ink">{term.term}</p>
                    <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600">
                      {term.is_cancelled === true ? '말소됨' : '유효'}
                    </span>
                  </div>
                  {term.warning && <p className="mt-2 text-sm leading-6 text-slate-700">{term.warning}</p>}
                  {term.evidence && <p className="mt-2 text-xs leading-5 text-slate-500">근거: {term.evidence}</p>}
                </div>
              ))}
            </div>
          )}

          {step.id === 'R5' && (
            <>
              {selectedBuilding ? (
                <div className="rounded-2xl border border-coral/20 bg-cream/40 p-4">
                  <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
                    건축물대장 자동 조회
                  </span>
                  <p className="mt-2 text-sm text-slate-600">주용도</p>
                  <p className="text-lg font-semibold text-slate-900">{form.buildingType || '-'}</p>
                  <p className="mt-3 text-sm text-slate-600">기타용도</p>
                  <p className="text-lg font-semibold text-slate-900">{form.detailUse || '-'}</p>
                  <p className="mt-3 text-xs text-slate-500">
                    R1에서 조회한 {selectedBuilding.building_name} 건축물대장에서 가져온 값입니다.
                  </p>
                </div>
              ) : (
                <>
                  <Field label="건축물 주용도" hint="건축물대장이 조회되지 않아 직접 입력합니다.">
                    <input
                      className={inputClass}
                      value={form.buildingType}
                      onChange={(event) => update('buildingType', event.target.value)}
                      placeholder="예) 공동주택"
                    />
                  </Field>
                  <Field label="기타용도 (상세)">
                    <input
                      className={inputClass}
                      value={form.detailUse}
                      onChange={(event) => update('detailUse', event.target.value)}
                      placeholder="예) 다세대주택 / 제2종근린생활시설(고시원)"
                    />
                  </Field>
                </>
              )}
            </>
          )}

          {step.id === 'R6' && (
            <>
              <input
                ref={ledgerInputRef}
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={handleLedgerUpload}
              />
              <div className="rounded-2xl border border-dashed border-coral/40 bg-white p-6 text-center">
                <p className="text-sm leading-6 text-slate-600">
                  위반건축물 표시는 건축물대장 공공 API에 없어 대장 원본을 봐야 합니다.
                  <br />
                  정부24에서 발급한 건축물대장 PDF를 올리면 AI가 판독합니다.
                </p>
                <button
                  type="button"
                  onClick={() => ledgerInputRef.current?.click()}
                  disabled={ledgerStatus === 'uploading'}
                  className="mt-4 rounded-2xl bg-slate-900 px-6 py-3 text-sm font-medium text-white disabled:opacity-40"
                >
                  {ledgerStatus === 'uploading' ? '판독 중…' : '건축물대장 PDF 업로드'}
                </button>
                {ledgerFileName && (
                  <p className="mt-3 text-xs text-slate-500">{ledgerFileName}</p>
                )}
              </div>

              {ledgerError && (
                <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">{ledgerError}</p>
              )}

              {ledger?.inspection && (
                <div className="rounded-2xl border border-coral/20 bg-cream/40 p-4">
                  <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
                    AI 판독 결과
                  </span>
                  <p
                    className={`mt-2 text-xl font-semibold ${
                      VIOLATION_META[ledger.inspection.violation_status].tone
                    }`}
                  >
                    {VIOLATION_META[ledger.inspection.violation_status].label}
                  </p>
                  {ledger.inspection.violation_note && (
                    <p className="mt-2 text-sm text-slate-700">{ledger.inspection.violation_note}</p>
                  )}
                  <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                    <dt className="text-slate-500">명칭</dt>
                    <dd className="text-slate-900">{ledger.inspection.building_name ?? '-'}</dd>
                    <dt className="text-slate-500">대지위치</dt>
                    <dd className="text-slate-900">{ledger.inspection.lot_address ?? '-'}</dd>
                    <dt className="text-slate-500">주용도</dt>
                    <dd className="text-slate-900">{ledger.inspection.main_use ?? '-'}</dd>
                    <dt className="text-slate-500">세대수</dt>
                    <dd className="text-slate-900">{ledger.inspection.households ?? '-'}</dd>
                  </dl>
                  {ledgerAddressMismatch && (
                    <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                      업로드한 대장의 지번이 R1에서 조회한 건물과 다릅니다. 다른 건물의 대장은 아닌지
                      확인하세요.
                    </p>
                  )}
                  {(ledger.inspection.floors?.length ?? 0) > 0 && (
                    <div className="mt-4 overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead className="text-slate-500">
                          <tr>
                            <th className="py-1 pr-3 font-medium">층</th>
                            <th className="py-1 pr-3 font-medium">용도</th>
                            <th className="py-1 font-medium">면적</th>
                          </tr>
                        </thead>
                        <tbody className="text-slate-800">
                          {ledger.inspection.floors.map((floor, index) => (
                            <tr key={`${floor.floor}-${index}`} className="border-t border-coral/10">
                              <td className="py-1 pr-3 whitespace-nowrap">{floor.floor}</td>
                              <td className="py-1 pr-3">{floor.use}</td>
                              <td className="py-1 whitespace-nowrap">
                                {floor.area_m2 ? `${floor.area_m2}㎡` : '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              <Field
                label="판독 결과 확인"
                hint="AI 판독이 틀렸다고 판단되면 직접 고칠 수 있습니다. 대장을 확인하지 않았다면 '확인 못 함'으로 두세요. 통과 처리되지 않고 판단 불가로 남습니다."
              >
                <select
                  className={inputClass}
                  value={form.illegalBuildingStatus}
                  onChange={(event) => update('illegalBuildingStatus', event.target.value)}
                >
                  <option value="unclear">확인 못 함 (판단 불가)</option>
                  <option value="absent">위반건축물 표시 없음</option>
                  <option value="present">위반건축물 표시 있음</option>
                </select>
              </Field>
            </>
          )}

          {step.id === 'R7' && (
            <>
              {lookup ? (
                <div className="rounded-2xl border border-coral/20 bg-cream/40 p-4">
                  <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
                    실거래가 자동 집계
                  </span>
                  <p className="mt-2 text-sm text-slate-600">최근 12개월 순수 전세 거래</p>
                  <p className="text-2xl font-semibold tracking-[-0.02em] text-slate-900">
                    {autoJeonseCount}건
                  </p>
                  <p className="mt-2 text-xs text-slate-500">
                    전월세 {lookup.rent?.total ?? 0}건 중 월세 0원인 순수 전세만 센 값입니다.
                    {selectedBuilding?.households
                      ? ` 이 건물은 ${selectedBuilding.households}세대입니다.`
                      : ''}
                  </p>
                </div>
              ) : (
                <Field
                  label="동일 건물 최근 12개월 순수 전세 거래 건수"
                  hint="실거래가가 조회되지 않아 직접 입력합니다."
                >
                  <input
                    className={inputClass}
                    inputMode="numeric"
                    value={form.recentJeonseCount}
                    onChange={(event) => update('recentJeonseCount', event.target.value)}
                  />
                </Field>
              )}
            </>
          )}

          {step.id === 'R8' && (
            <>
              {registryType !== 'general_building' && (
                <p className="rounded-2xl bg-sand px-5 py-4 text-sm leading-6 text-slate-600">
                  등기 유형이 {REGISTRY_TYPE_LABEL[registryType] ?? registryType}이라 선순위 보증금 문제가
                  발생하지 않습니다. 이 항목은 통과 처리됩니다.
                </p>
              )}
              <Field
                label="나보다 앞선 임차인들의 보증금 합계 (원)"
                hint="전입세대 열람원과 확정일자 부여현황으로 확인합니다. API가 없어 직접 입력해야 합니다."
              >
                <input
                  className={inputClass}
                  inputMode="numeric"
                  value={form.seniorDepositKrw}
                  onChange={(event) => update('seniorDepositKrw', event.target.value)}
                />
              </Field>
            </>
          )}
        </div>

        {submitError && <p className="mt-6 text-sm font-medium text-red-600">{submitError}</p>}

        <div className="mt-10 flex items-center justify-between gap-4">
          <button
            type="button"
            onClick={() => setStepIndex((index) => Math.max(0, index - 1))}
            disabled={stepIndex === 0}
            className="rounded-full border border-coral/20 px-5 py-3 text-sm font-semibold text-slate-600 transition hover:border-coral/40 disabled:opacity-40"
          >
            이전
          </button>
          <button
            type="button"
            onClick={() => (isLastStep ? submit() : setStepIndex((index) => index + 1))}
            disabled={!canProceed() || submitState === 'loading'}
            className="rounded-full bg-ink px-8 py-3 text-sm font-semibold text-white transition hover:bg-[#0f523d] disabled:opacity-40"
          >
            {isLastStep ? (submitState === 'loading' ? '분석 중…' : '분석 실행') : '다음'}
          </button>
        </div>
      </section>
    </main>
  );
}

function ResultView({ result, onRestart }) {
  const unknownChecks = result.checks.filter((check) => check.status === 'unknown');
  // 데이터가 없어 규칙이 돌지 못한 것을 낮은 점수로 위장하지 않는다.
  const insufficient = result.summary?.overall_status === 'unknown';
  const grade = insufficient
    ? { label: '데이터 부족', tone: 'text-slate-700 bg-slate-100 border-slate-300' }
    : (GRADE_META[result.risk_grade] ?? GRADE_META.safe);

  return (
    <main className="mx-auto w-full max-w-3xl px-6 pb-20 pt-6 lg:px-10 lg:pb-24 lg:pt-10">
      <section className={`rounded-[2rem] border p-8 ${grade.tone}`}>
        <p className="text-sm font-semibold tracking-[0.18em] uppercase">Risk Assessment</p>
        <div className="mt-4 flex items-end gap-4">
          <span className="text-6xl font-semibold tracking-[-0.04em]">{result.risk_score}</span>
          <span className="pb-2 text-2xl font-semibold">{grade.label}</span>
        </div>
        {unknownChecks.length > 0 && (
          <p className="mt-4 text-sm leading-6">
            {unknownChecks.length}개 항목을 데이터 부족으로 판정하지 못했습니다. 이 점수는 남은 항목만
            반영한 값이므로 실제 위험은 더 높을 수 있습니다.
          </p>
        )}
        {result.override_reasons?.length > 0 && (
          <ul className="mt-6 space-y-2 border-t border-current/20 pt-5 text-sm leading-6">
            {result.override_reasons.map((reason) => (
              <li key={reason}>• {reason}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-8 space-y-3">
        {result.checks.map((check) => {
          const status = STATUS_META[check.status] ?? STATUS_META.unknown;
          return (
            <article key={check.code} className="rounded-2xl border border-coral/15 bg-white p-5">
              <div className="flex items-start justify-between gap-4">
                <h2 className="font-semibold text-slate-900">{check.title}</h2>
                <span className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${status.tone}`}>
                  {status.label}
                </span>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-600">{check.reason}</p>
            </article>
          );
        })}
      </section>

      {result.llm_explanation && (
        <section className="mt-8 rounded-[2rem] border border-sage/20 bg-white p-6">
          <p className="text-sm font-semibold tracking-[0.18em] text-sage uppercase">설명</p>
          <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-slate-700">{result.llm_explanation}</p>
        </section>
      )}

      <button
        type="button"
        onClick={onRestart}
        className="mt-8 w-full rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#0f523d]"
      >
        새 분석 시작
      </button>
    </main>
  );
}

export default AnalysisNewPage;
