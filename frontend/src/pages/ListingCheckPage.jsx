import { useEffect, useMemo, useRef, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

function ListingCheckPage() {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markerRef = useRef(null);

  const [query, setQuery] = useState('');
  const [propertyType, setPropertyType] = useState('');
  const [searchLoading, setSearchLoading] = useState(false);

  const [placeCandidates, setPlaceCandidates] = useState([]);
  const [selectedPlace, setSelectedPlace] = useState(null);

  const [error, setError] = useState('');
  const [searchResult, setSearchResult] = useState(null);
  const [buildingCandidates, setBuildingCandidates] = useState([]);
  const [selectedBuilding, setSelectedBuilding] = useState(null);
  const [viewingDetails, setViewingDetails] = useState(null);
  const [rentItems, setRentItems] = useState([]);

  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);

  const inputCls =
    'rounded-lg border border-coral/20 bg-white px-3 py-2 text-sm text-ink placeholder:text-slate-400 focus:border-coral focus:outline-none';

  const selectedRentItem = rentItems.length > 0 ? rentItems[0] : null;
  const activeBuilding = selectedBuilding || searchResult?.building?.selected || null;
  const marketPriceKrw = Number(searchResult?.market_price?.price_krw || 0);
  const selectedDepositKrw = selectedRentItem ? parseManwon(selectedRentItem.deposit) * 10000 : 0;
  const ratioFromSelection = marketPriceKrw > 0 && selectedDepositKrw > 0 ? selectedDepositKrw / marketPriceKrw : null;

  const depositRatioCheck = useMemo(
    () => analysisResult?.checks?.find((check) => check.code === 'deposit_to_market_ratio') ?? null,
    [analysisResult],
  );

  useEffect(() => {
    const clientId = import.meta.env.VITE_NAVER_MAPS_CLIENT_ID;
    const scriptId = 'naver-maps-script';

    function initMap() {
      if (!window.naver?.maps || mapInstanceRef.current) return;
      mapInstanceRef.current = new window.naver.maps.Map(mapRef.current, {
        center: new window.naver.maps.LatLng(37.5666805, 126.9784147),
        zoom: 14,
      });
    }

    if (window.naver?.maps) {
      initMap();
      return;
    }
    if (document.getElementById(scriptId)) {
      const scriptEl = document.getElementById(scriptId);
      scriptEl.addEventListener('load', initMap);
      return () => scriptEl.removeEventListener('load', initMap);
    }

    const script = document.createElement('script');
    script.id = scriptId;
    script.src = `https://openapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${clientId}`;
    script.onload = initMap;
    document.head.appendChild(script);
  }, []);

  function moveMapTo(x, y) {
    if (!window.naver?.maps || !mapInstanceRef.current) return;
    const coords = new window.naver.maps.LatLng(Number(y), Number(x));
    mapInstanceRef.current.setCenter(coords);
    mapInstanceRef.current.setZoom(17);
    if (markerRef.current) markerRef.current.setMap(null);
    markerRef.current = new window.naver.maps.Marker({
      position: coords,
      map: mapInstanceRef.current,
    });
  }

  async function handleSearch() {
    if (!propertyType) {
      setError('건물 유형을 선택하세요.');
      return;
    }
    if (!query.trim()) {
      setError('주소 또는 건물명을 입력해주세요.');
      return;
    }

    setSearchLoading(true);
    setError('');
    setPlaceCandidates([]);
    setSelectedPlace(null);
    setAnalysisResult(null);
    setSearchResult(null);
    setBuildingCandidates([]);
    setSelectedBuilding(null);
    setViewingDetails(null);
    setRentItems([]);

    try {
      const response = await fetch(`${API_BASE}/places/search?query=${encodeURIComponent(query.trim())}`);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(payload.detail ?? '장소 검색에 실패했습니다.');
        return;
      }
      const data = await response.json();
      setPlaceCandidates(data.items || []);
      if (data.items?.length === 0) {
        setError('검색 결과가 없습니다.');
      }
    } catch {
      setError('서버에 연결할 수 없습니다.');
    } finally {
      setSearchLoading(false);
    }
  }

  async function handleSelectPlace(place) {
    setSelectedPlace(place);
    setSearchLoading(true);
    setError('');
    setSearchResult(null);
    setBuildingCandidates([]);
    setSelectedBuilding(null);
    setViewingDetails(null);
    setRentItems([]);

    try {
      const targetAddress = place.address || place.roadAddress;
      const params = new URLSearchParams({
        query: targetAddress,
        building_name: place.title,
        property_type: propertyType,
      });
      const response = await fetch(`${API_BASE}/listing-checks/search?${params}`);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(payload.detail ?? '매물 세부 정보를 가져오지 못했습니다.');
        return;
      }

      const data = await response.json();
      setSearchResult(data);
      setBuildingCandidates(data?.building?.candidates || []);
      if (data?.building?.selected) setSelectedBuilding(data.building.selected);
      setRentItems(data?.rent?.items || []);
      moveMapTo(data?.location?.x, data?.location?.y);
    } catch {
      setError('서버에 연결할 수 없습니다.');
    } finally {
      setSearchLoading(false);
    }
  }

  async function handleAnalyze() {
    if (!activeBuilding) {
      setError('건축물 후보를 먼저 선택해주세요.');
      return;
    }
    if (!selectedRentItem) {
      setError('해당 매물의 전세 거래 내역이 없습니다.');
      return;
    }
    const depositKrw = parseManwon(selectedRentItem.deposit) * 10000;
    if (depositKrw <= 0) {
      setError('전세 보증금 정보가 유효하지 않습니다.');
      return;
    }

    setAnalysisLoading(true);
    setError('');
    setAnalysisResult(null);
    try {
      const response = await fetch(`${API_BASE}/listing-checks/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          property_type: propertyType,
          listing_name: selectedRentItem.buildingNm || query.trim(),
          deposit_krw: depositKrw,
          market_price_krw: marketPriceKrw,
          selected_rent_item: selectedRentItem,
          selected_building: activeBuilding,
          extra_signals: {
            recent_transactions: rentItems,
          },
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(payload.detail ?? '점검 결과 생성에 실패했습니다.');
        return;
      }
      const data = await response.json();
      setAnalysisResult(data);
    } catch {
      setError('서버에 연결할 수 없습니다.');
    } finally {
      setAnalysisLoading(false);
    }
  }

  function selectBuilding(candidate) {
    setSelectedBuilding(candidate);
    setAnalysisResult(null);
  }

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-6 pb-16 pt-8 lg:px-10">
      <section className="rounded-2xl border border-coral/15 bg-white p-4 shadow-sm">
        <p className="text-xs font-semibold tracking-[0.12em] text-coral uppercase">매물 검색</p>
        <div className="mt-2 flex flex-col gap-2 md:flex-row">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="건물명으로 검색(예: 반포자이아파트)"
            className={`${inputCls} flex-1`}
          />
          <select value={propertyType} onChange={(e) => setPropertyType(e.target.value)} className={`${inputCls} md:w-44`}>
            <option value="" disabled>건물 유형</option>
            <option value="apt">아파트</option>
            <option value="offi">오피스텔</option>
            <option value="rh">연립/다세대</option>
            <option value="sh">단독/다가구</option>
          </select>
          <button
            onClick={handleSearch}
            disabled={searchLoading}
            className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-white transition hover:bg-[#0f523d] disabled:opacity-50"
          >
            {searchLoading ? '검색중...' : '매물 검색'}
          </button>
        </div>
        {searchResult ? (
          <p className="mt-2 text-xs text-slate-500">
            {searchResult.location?.address || '-'} · 최근 1년 거래 {searchResult.rent?.total || 0}건 · 시세(최근 거래가) {formatMoney(marketPriceKrw)}원
          </p>
        ) : null}
      </section>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {placeCandidates.length > 0 && !selectedPlace && (
        <section className="rounded-xl border border-coral/15 bg-white p-4 shadow-sm">
          <p className="mb-3 text-sm font-semibold text-ink">장소 검색 결과 (건물을 선택해주세요)</p>
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
            {placeCandidates.map((place, idx) => (
              <button
                key={`${place.mapx}-${idx}`}
                onClick={() => handleSelectPlace(place)}
                className="flex flex-col rounded-lg border border-coral/10 bg-white p-3 text-left transition hover:border-coral/30 hover:bg-coral/5"
              >
                <span className="text-sm font-medium text-ink">{place.title}</span>
                <span className="mt-1 text-xs text-slate-500">{place.address || place.roadAddress}</span>
                <span className="mt-1 text-[11px] text-slate-400">{place.category}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {selectedPlace && (
        <div className="flex items-center gap-2 rounded-lg bg-coral/10 px-4 py-2 text-sm text-coral">
          <span className="font-semibold">선택된 장소:</span>
          <span>{selectedPlace.title}</span>
          <button onClick={() => { setSelectedPlace(null); setPlaceCandidates([]); }} className="ml-auto text-xs underline">다시 검색</button>
        </div>
      )}

      <section className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-4">
          <div ref={mapRef} className="h-[360px] w-full rounded-xl border border-coral/15 shadow-sm lg:h-[430px]" />

          <article className="rounded-xl border border-coral/15 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-semibold text-ink">건축물대장 후보 (해당하는 건축물대장을 선택하세요)</p>
              <span className="text-xs text-slate-500">{buildingCandidates.length}건</span>
            </div>
            <div className="max-h-56 space-y-2 overflow-y-auto">
              {buildingCandidates.length === 0 ? (
                <p className="rounded-lg border border-dashed border-coral/20 bg-sand px-3 py-3 text-sm text-slate-500">검색 후 후보를 선택한다.</p>
              ) : null}
              {buildingCandidates.map((candidate, idx) => {
                const isSelected = activeBuilding?.mgmBldrgstPk === candidate.mgmBldrgstPk;
                const isViewing = viewingDetails === candidate;
                return (
                  <div
                    key={`${candidate.mgmBldrgstPk}-${idx}`}
                    className={`relative w-full rounded-lg border px-3 py-3 transition ${
                      isSelected ? 'border-coral bg-coral/30 shadow-sm' : 'border-coral/15 bg-white hover:bg-coral/5'
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => selectBuilding(candidate)}
                      className="w-full text-left pr-20"
                    >
                      <p className="text-sm font-medium text-ink">{candidate.building_name || '-'}</p>
                      <p className="mt-1 text-xs text-slate-500">{candidate.address || '-'}</p>
                      <p className="mt-1 text-[11px] text-slate-400">
                        {candidate.building_type || '-'} · {candidate.structure || '-'} · {candidate.floors ? `${candidate.floors}층` : '-'}
                      </p>
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); setViewingDetails(isViewing ? null : candidate); }}
                      className="absolute right-3 top-3 rounded bg-sand px-2 py-1 text-[10px] font-medium text-coral hover:bg-coral/10 border border-coral/10"
                    >
                      {isViewing ? '닫기' : '세부내용 보기'}
                    </button>
                    {isViewing && (
                      <div className="mt-3 border-t border-coral/10 pt-2 text-[11px] text-slate-600 grid grid-cols-2 gap-y-1">
                        <p><span className="text-slate-400">상세용도:</span> {candidate.detail_use || '-'}</p>
                        <p><span className="text-slate-400">지붕:</span> {candidate.roof || '-'}</p>
                        <p><span className="text-slate-400">세대/가구:</span> {candidate.households}/{candidate.family_count}</p>
                        <p><span className="text-slate-400">사용승인일:</span> {candidate.use_approval_date || '-'}</p>
                        <p><span className="text-slate-400">내진설계:</span> {candidate.resistant_quake === '1' ? '적용' : '미적용'}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </article>

          <article className="rounded-xl border border-coral/15 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-semibold text-ink">가장 최근 전세 거래 정보</p>
              <span className="text-[10px] text-slate-400 font-normal italic">자동 반영</span>
            </div>
            {rentItems.length > 0 ? (
              <div className="rounded-lg border border-coral/10 bg-sand/30 px-4 py-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-ink">{rentItems[0].buildingNm}</span>
                  <span className="text-xs text-slate-500">{renderDealDate(rentItems[0])}</span>
                </div>
                <div className="mt-2 flex gap-4 text-xs">
                  <p><span className="text-slate-500">보증금:</span> <span className="font-semibold text-coral">{rentItems[0].deposit}</span> 만원</p>
                  <p><span className="text-slate-500">전용면적:</span> {rentItems[0].excluUseAr}㎡</p>
                  <p><span className="text-slate-500">층수:</span> {rentItems[0].floor}층</p>
                </div>
              </div>
            ) : (
              <p className="rounded-lg border border-dashed border-coral/20 bg-sand px-3 py-3 text-sm text-slate-500">
                조회된 전세 거래 내역이 없습니다.
              </p>
            )}
          </article>
        </div>

        <aside className="h-fit rounded-xl border border-coral/15 bg-white p-4 shadow-sm lg:sticky lg:top-24">
          <p className="text-sm font-semibold text-ink">점검 결과</p>
          <p className="mt-1 text-xs text-slate-500">건물 정보와 최근 전세가를 분석합니다.</p>

          <div className="mt-4 space-y-2 rounded-lg bg-sand p-3 text-xs text-slate-700">
            <SummaryRow label="건물명" value={activeBuilding?.building_name || '-'} />
            <SummaryRow label="시세(매매)" value={marketPriceKrw > 0 ? `${formatMoney(marketPriceKrw)}원` : '정보없음'} />
            <SummaryRow label="최근 전세" value={selectedRentItem ? `${formatMoney(selectedDepositKrw)}원` : '-'} />
            <SummaryRow label="전세가율" value={ratioFromSelection !== null ? `${(ratioFromSelection * 100).toFixed(1)}%` : '-'} />
          </div>

          <div className="group relative mt-4">
            <button
              onClick={handleAnalyze}
              disabled={!activeBuilding || rentItems.length === 0 || analysisLoading}
              className="w-full rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#0f523d] disabled:opacity-50"
            >
              {analysisLoading ? '점검 중...' : 'AI 점검 실행'}
            </button>
            {!activeBuilding && (
              <div className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-slate-800 px-2 py-1 text-[11px] text-white opacity-0 transition group-hover:opacity-100 shadow-lg">
                건축물대장 후보를 하나 선택하세요
              </div>
            )}
          </div>

          {analysisResult ? (
            <div className="mt-4 space-y-3">
              <div className="rounded-lg border border-coral/15 bg-coral/5 px-3 py-2">
                <p className="text-xs text-slate-500">종합 결과</p>
                <p className={`mt-1 text-sm font-semibold ${statusTextClass(analysisResult.summary?.overall_status)}`}>
                  {statusLabel(analysisResult.summary?.overall_status)}
                </p>
              </div>

              <div className="space-y-2">
                {(analysisResult.checks || []).map((check) => (
                  <div key={check.code} className="rounded-lg border border-coral/10 px-3 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-ink">{check.title}</p>
                      <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${statusBadgeClass(check.status)}`}>
                        {statusLabel(check.status)}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-slate-600">{check.reason}</p>
                    {check.code === 'deposit_to_market_ratio' && typeof depositRatioCheck?.evidence?.ratio === 'number' ? (
                      <p className="mt-1 text-[11px] text-slate-500">판정 전세가율: {(depositRatioCheck.evidence.ratio * 100).toFixed(1)}%</p>
                    ) : null}
                  </div>
                ))}
              </div>

              <div className="rounded-lg border border-coral/15 bg-sand px-3 py-3">
                <p className="text-xs font-semibold text-ink">LLM 설명</p>
                <p className="mt-2 whitespace-pre-line text-sm leading-6 text-slate-700">{analysisResult.llm_explanation || '-'}</p>
              </div>
            </div>
          ) : null}
        </aside>
      </section>
    </main>
  );
}

function parseManwon(value) {
  if (value === null || value === undefined) return 0;
  const text = String(value).replaceAll(',', '').trim();
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatMoney(value) {
  return new Intl.NumberFormat('ko-KR').format(value || 0);
}

function renderDealDate(item) {
  const y = String(item?.dealYear || '').trim();
  const m = String(item?.dealMonth || '').trim().padStart(2, '0');
  const d = String(item?.dealDay || '').trim().padStart(2, '0');
  if (!y || !m || !d) return '-';
  return `${y}-${m}-${d}`;
}

function SummaryRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium text-ink">{value}</span>
    </div>
  );
}

function statusLabel(status) {
  if (status === 'pass') return '양호';
  if (status === 'warn') return '주의';
  if (status === 'fail') return '위험';
  return '확인불가';
}

function statusTextClass(status) {
  if (status === 'pass') return 'text-emerald-600';
  if (status === 'warn') return 'text-amber-600';
  if (status === 'fail') return 'text-red-600';
  return 'text-slate-600';
}

function statusBadgeClass(status) {
  if (status === 'pass') return 'bg-emerald-50 text-emerald-600';
  if (status === 'warn') return 'bg-amber-50 text-amber-700';
  if (status === 'fail') return 'bg-red-50 text-red-700';
  return 'bg-slate-100 text-slate-700';
}

export default ListingCheckPage;
