import { useEffect, useRef, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const COLUMNS = {
  apt:  { buildingNm: '단지명',    headers: ['단지명',    '동', '전용면적(㎡)', '보증금(만원)', '월세(만원)', '층', '계약유형', '전월세구분'] },
  offi: { buildingNm: '오피스텔명', headers: ['오피스텔명', '동', '전용면적(㎡)', '보증금(만원)', '월세(만원)', '층', '계약유형', '전월세구분'] },
  rh:   { buildingNm: '건물명',    headers: ['건물명',    '동', '전용면적(㎡)', '보증금(만원)', '월세(만원)', '층', '계약유형', '전월세구분'] },
  sh:   { buildingNm: '건물유형',   headers: ['건물유형',  '동', '연면적(㎡)',   '보증금(만원)', '월세(만원)', '계약유형', '전월세구분'] },
};

const CURRENT_YMD = (() => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  return `${y}${m}`;
})();

const BUILDING_GUIDE_ITEMS = [
  {
    title: '사용승인일',
    warning: '너무 오래된 건물은 안전, 유지보수, 권리관계 확인이 더 중요하다.',
    note: '신축/준신축은 상대적으로 정보가 명확한 편이지만, 그 자체로 안전을 보장하지는 않는다.',
  },
  {
    title: '건축물 용도',
    warning: '주거용이 아닌 건물은 임대차 구조와 실제 사용 형태를 반드시 확인해야 한다.',
    note: '오피스텔, 근린생활시설, 다가구, 다세대는 계약 방식과 위험 포인트가 다르다.',
  },
  {
    title: '구조와 층수',
    warning: '층수 대비 세대 수가 많거나 구조가 복잡하면 관리 상태를 더 꼼꼼히 봐야 한다.',
    note: '지하층이 있으면 침수, 환기, 누수 이슈도 같이 확인하는 편이 좋다.',
  },
  {
    title: '세대수 / 가구수',
    warning: '세대 수가 많으면 선순위 보증금, 다수 임차인, 관리 부실 가능성을 함께 본다.',
    note: '가구수와 세대수 차이도 확인하면 실제 거주 형태를 가늠하는 데 도움이 된다.',
  },
  {
    title: '주소 일치',
    warning: '검색 주소와 건축물대장 주소가 다르면, 같은 필지인지부터 다시 확인해야 한다.',
    note: '이 화면에서는 후보를 직접 클릭해서 실제 건물과 문서를 맞춘다.',
  },
  {
    title: '건축물 구분',
    warning: '다가구, 다세대, 연립, 오피스텔은 권리관계와 계약 리스크가 다르다.',
    note: '계약 전등기부등본, 선순위 보증금, 실제 점유 구조와 같이 봐야 한다.',
  },
];

function parseMonthlyRent(value) {
  if (value === null || value === undefined) return 0;
  const normalized = String(value).replaceAll(',', '').trim();
  if (!normalized) return 0;
  const parsed = Number(normalized);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function getLeaseType(monthlyRent) {
  return parseMonthlyRent(monthlyRent) > 0 ? '월세' : '전세';
}

function renderMonthlyRent(monthlyRent) {
  if (monthlyRent === null || monthlyRent === undefined) return '-';
  const normalized = String(monthlyRent).trim();
  return normalized ? normalized : '-';
}

function MapPage() {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markerRef = useRef(null);
  const mapClickListenerRef = useRef(null);

  const [buildingQuery, setBuildingQuery] = useState('');
  const [selectedAddress, setSelectedAddress] = useState('');
  const [buildingInfo, setBuildingInfo] = useState(null);
  const [buildingCandidates, setBuildingCandidates] = useState([]);
  const [selectedBuilding, setSelectedBuilding] = useState(null);
  const [buildingLoading, setBuildingLoading] = useState(false);
  const [sido, setSido] = useState('');
  const [sigungu, setSigungu] = useState('');
  const [dong, setDong] = useState('');
  const [dealFrom, setDealFrom] = useState(CURRENT_YMD);
  const [dealTo, setDealTo] = useState(CURRENT_YMD);
  const [propertyType, setPropertyType] = useState('apt');

  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [rentData, setRentData] = useState(null);

  async function loadBuildingInfo(lat, lng, { autoSelect = false } = {}) {
    setBuildingLoading(true);
    setBuildingInfo(null);
    setBuildingCandidates([]);
    setSelectedBuilding(null);
    setError('');

    try {
      const response = await fetch(`${API_BASE}/building-register?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(payload.detail ?? '건축물대장 정보를 불러오지 못했습니다.');
        return;
      }

      const data = await response.json();
      setBuildingInfo(data);
      setBuildingCandidates(data.candidates ?? []);
      if (autoSelect && data.selected) {
        setSelectedBuilding(data.selected);
      }
      setSelectedAddress(data.location?.road_address || data.location?.jibun_address || '');
    } catch {
      setError('서버에 연결할 수 없습니다.');
    } finally {
      setBuildingLoading(false);
    }
  }

  function moveMapToCoords(lat, lng, addressText = '') {
    if (!window.naver?.maps || !mapInstanceRef.current) return;

    const coords = new window.naver.maps.LatLng(lat, lng);
    mapInstanceRef.current.setCenter(coords);
    mapInstanceRef.current.setZoom(17);
    if (markerRef.current) markerRef.current.setMap(null);
    markerRef.current = new window.naver.maps.Marker({
      position: coords,
      map: mapInstanceRef.current,
    });
    if (addressText) setSelectedAddress(addressText);
  }

  useEffect(() => {
    const clientId = import.meta.env.VITE_NAVER_MAPS_CLIENT_ID;
    const scriptId = 'naver-maps-script';
    let cleanupListener = null;

    function initMap() {
      mapInstanceRef.current = new window.naver.maps.Map(mapRef.current, {
        center: new window.naver.maps.LatLng(37.5666805, 126.9784147),
        zoom: 14,
      });

      if (mapClickListenerRef.current) {
        window.naver.maps.Event.removeListener(mapClickListenerRef.current);
      }
      mapClickListenerRef.current = window.naver.maps.Event.addListener(
        mapInstanceRef.current,
        'click',
        (event) => {
          const coord = event.coord;
          if (!coord) return;
          moveMapToCoords(coord.y, coord.x);
          loadBuildingInfo(coord.y, coord.x, { autoSelect: true });
        },
      );
      cleanupListener = () => {
        if (mapClickListenerRef.current && window.naver?.maps) {
          window.naver.maps.Event.removeListener(mapClickListenerRef.current);
          mapClickListenerRef.current = null;
        }
      };
    }

    if (window.naver?.maps) {
      initMap();
      return () => cleanupListener?.();
    }
    if (document.getElementById(scriptId)) {
      const scriptEl = document.getElementById(scriptId);
      scriptEl.addEventListener('load', initMap);
      return () => {
        scriptEl.removeEventListener('load', initMap);
        cleanupListener?.();
      };
    }

    const script = document.createElement('script');
    script.id = scriptId;
    script.src = `https://openapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${clientId}`;
    script.onload = initMap;
    document.head.appendChild(script);
    return () => {
      cleanupListener?.();
    };
  }, []);

  async function handleBuildingSearch() {
    const query = buildingQuery.trim();
    if (!query) {
      setError('건물 주소를 입력해주세요.');
      return;
    }

    setError('');
    setBuildingLoading(true);
    setBuildingInfo(null);

    try {
      const geoRes = await fetch(`${API_BASE}/geocode?query=${encodeURIComponent(query)}`);
      if (!geoRes.ok) {
        setError('주소를 찾지 못했습니다.');
        return;
      }

      const geoData = await geoRes.json();
      if (!geoData.result) {
        setError('주소를 찾지 못했습니다.');
        return;
      }

      moveMapToCoords(geoData.result.y, geoData.result.x, geoData.result.address);
      await loadBuildingInfo(geoData.result.y, geoData.result.x, { autoSelect: false });
    } catch {
      setError('서버에 연결할 수 없습니다.');
    } finally {
      setBuildingLoading(false);
    }
  }

  async function handleRentSearch() {
    if (!sido.trim() || !sigungu.trim() || !dealFrom.trim() || !dealTo.trim()) {
      setError('시·도, 시·군·구, 기간을 입력해주세요.');
      return;
    }
    if (dealFrom > dealTo) {
      setError('시작 년월이 종료 년월보다 클 수 없습니다.');
      return;
    }
    setError('');
    setLoading(true);
    setRentData(null);

    try {
      // 지오코딩 (지도 마커)
      if (window.naver?.maps) {
        const geocodeQuery = `${sido} ${sigungu} ${dong}`;
        const geoRes = await fetch(`${API_BASE}/geocode?query=${encodeURIComponent(geocodeQuery)}`);
        if (geoRes.ok) {
          const geoData = await geoRes.json();
          if (geoData.result) {
            moveMapToCoords(geoData.result.y, geoData.result.x, geoData.result.address);
          }
        }
      }

      // 전월세 실거래가 조회
      const params = new URLSearchParams({ sido, sigungu, dong, deal_from: dealFrom, deal_to: dealTo, property_type: propertyType });
      const rentRes = await fetch(`${API_BASE}/jeonse-data?${params}`);
      if (!rentRes.ok) {
        const err = await rentRes.json().catch(() => ({}));
        setError(err.detail ?? '전월세 데이터 조회 중 오류가 발생했습니다.');
        return;
      }
      const data = await rentRes.json();
      setRentData(data);
      if (data.total === 0) setError('해당 동의 전월세 거래 내역이 없습니다.');
    } catch {
      setError('서버에 연결할 수 없습니다.');
    } finally {
      setLoading(false);
    }
  }

  function handleBuildingKeyDown(e) {
    if (e.key === 'Enter') handleBuildingSearch();
  }

  function handleRentKeyDown(e) {
    if (e.key === 'Enter') handleRentSearch();
  }

  function handleCandidateSelect(candidate) {
    setSelectedBuilding(candidate);
    setSelectedAddress(candidate.address || '');
  }

  const activeBuilding = selectedBuilding || (buildingInfo?.matched_count === 1 ? buildingInfo.selected : null);

  const inputCls =
    'rounded-lg border border-coral/20 bg-white px-3 py-2 text-sm text-ink placeholder:text-slate-400 focus:border-coral focus:outline-none';

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-8">
      <h1 className="text-xl font-semibold text-ink">지도 검색</h1>

      <section className="flex flex-col gap-3 rounded-2xl border border-coral/15 bg-white p-4 shadow-sm">
        <div>
          <p className="text-sm font-medium text-ink">건물 선택</p>
          <p className="text-xs text-slate-500">주소를 검색하거나 지도를 클릭하면 우측에 건축물대장 정보를 보여준다.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            value={buildingQuery}
            onChange={(e) => setBuildingQuery(e.target.value)}
            onKeyDown={handleBuildingKeyDown}
            placeholder="예: 서울특별시 서초구 서초동 1758"
            className={`${inputCls} min-w-[280px] flex-1`}
          />
          <button
            onClick={handleBuildingSearch}
            disabled={buildingLoading}
            className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-white transition hover:bg-[#0f523d] disabled:opacity-50"
          >
            {buildingLoading ? '불러오는 중…' : '건물 찾기'}
          </button>
        </div>
      </section>

      <div className="flex flex-wrap gap-2">
        <input
          type="text"
          value={sido}
          onChange={(e) => setSido(e.target.value)}
          onKeyDown={handleRentKeyDown}
          placeholder="시·도 (예: 서울특별시)"
          className={`${inputCls} w-32`}
        />
        <input
          type="text"
          value={sigungu}
          onChange={(e) => setSigungu(e.target.value)}
          onKeyDown={handleRentKeyDown}
          placeholder="시·군·구 (예: 수원시 권선구)"
          className={`${inputCls} w-44`}
        />
        <input
          type="text"
          value={dong}
          onChange={(e) => setDong(e.target.value)}
          onKeyDown={handleRentKeyDown}
          placeholder="동 (선택)"
          className={`${inputCls} w-28`}
        />
        <select
          value={propertyType}
          onChange={(e) => setPropertyType(e.target.value)}
          className={`${inputCls} w-32`}
        >
          <option value="apt">아파트</option>
          <option value="offi">오피스텔</option>
          <option value="rh">연립/다세대</option>
          <option value="sh">단독/다가구</option>
        </select>
        <input
          type="text"
          value={dealFrom}
          onChange={(e) => setDealFrom(e.target.value)}
          onKeyDown={handleRentKeyDown}
          placeholder="시작 (예: 202501)"
          className={`${inputCls} w-32`}
        />
        <span className="self-center text-slate-400">~</span>
        <input
          type="text"
          value={dealTo}
          onChange={(e) => setDealTo(e.target.value)}
          onKeyDown={handleRentKeyDown}
          placeholder="종료 (예: 202503)"
          className={`${inputCls} w-32`}
        />
        <button
          onClick={handleRentSearch}
          disabled={loading}
          className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-white transition hover:bg-[#0f523d] disabled:opacity-50"
        >
          {loading ? '검색 중…' : '검색'}
        </button>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      <div className="flex flex-col gap-4 lg:flex-row">
        <div ref={mapRef} className="h-[420px] w-full flex-1 rounded-xl border border-coral/15 shadow-sm lg:h-[560px]" />

        <aside className="w-full rounded-xl border border-coral/15 bg-white p-4 shadow-sm lg:w-[360px]">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-ink">건축물대장 정보</p>
              <p className="text-xs text-slate-500">지도에서 선택한 건물의 핵심 정보</p>
            </div>
          </div>

          <details className="mb-4 rounded-xl border border-ink/10 bg-sand/60 px-3 py-2">
            <summary className="cursor-pointer text-sm font-semibold text-ink">건축물대장 체크 가이드</summary>
            <div className="mt-3 space-y-3">
              <p className="text-xs text-slate-600">
                아래 항목은 전세사기 예방 관점에서 우선 확인할 포인트다. 하나만 보고 판단하지 말고, 등기부등본과 실제 현장 상태를 같이 확인해야 한다.
              </p>
              <div className="space-y-3">
                {BUILDING_GUIDE_ITEMS.map((item) => (
                  <div key={item.title} className="rounded-lg border border-coral/10 bg-white px-3 py-2">
                    <p className="text-sm font-medium text-ink">{item.title}</p>
                    <p className="mt-1 text-xs text-red-600">{item.warning}</p>
                    <p className="mt-1 text-xs text-slate-500">{item.note}</p>
                  </div>
                ))}
              </div>
            </div>
          </details>

          {!buildingInfo && !buildingLoading && (
            <div className="rounded-lg border border-dashed border-coral/20 bg-sand px-3 py-4 text-sm text-slate-500">
              주소 검색 후 후보를 고르고, 지도 클릭으로도 같은 흐름을 사용할 수 있다.
            </div>
          )}

          {buildingLoading && (
            <div className="rounded-lg border border-coral/15 bg-sand px-3 py-4 text-sm text-slate-500">
              건축물대장 조회 중…
            </div>
          )}

          {buildingInfo && buildingCandidates.length > 0 && (
            <div className="space-y-3">
              <div className="rounded-lg border border-coral/10 bg-sand px-3 py-2 text-xs text-slate-600">
                후보 {buildingCandidates.length}건
                {buildingInfo.matched_count > buildingCandidates.length ? ` · 전체 ${buildingInfo.matched_count}건` : ''}
              </div>

              <div className="max-h-72 overflow-y-auto rounded-xl border border-coral/15">
                {buildingCandidates.map((candidate, index) => {
                  const isSelected =
                    activeBuilding &&
                    activeBuilding.address === candidate.address &&
                    activeBuilding.building_name === candidate.building_name;

                  return (
                    <button
                      key={`${candidate.legal_code}-${candidate.address}-${index}`}
                      type="button"
                      onClick={() => handleCandidateSelect(candidate)}
                      className={`block w-full border-b border-coral/10 px-3 py-3 text-left transition last:border-b-0 hover:bg-coral/5 ${
                        isSelected ? 'bg-coral/10' : 'bg-white'
                      }`}
                    >
                      <p className="text-sm font-medium text-ink">{candidate.building_name || '-'}</p>
                      <p className="mt-1 text-xs text-slate-500">{candidate.address || '-'}</p>
                      <p className="mt-1 text-[11px] text-slate-400">
                        {candidate.building_type || '-'} · {candidate.structure || '-'} · {candidate.floors ? `${candidate.floors}층` : '-'}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {activeBuilding && (
            <div className="space-y-3">
              <div className="rounded-xl bg-coral/5 p-4">
                <p className="text-sm font-semibold text-ink">{activeBuilding.building_name || '-'}</p>
                <p className="mt-1 text-xs text-slate-500">{activeBuilding.address || selectedAddress || '-'}</p>
              </div>

              <div className="grid grid-cols-1 gap-2 text-sm">
                <InfoRow label="용도" value={activeBuilding.building_type || '-'} />
                <InfoRow label="구조" value={activeBuilding.structure || '-'} />
                <InfoRow label="층수" value={activeBuilding.floors ? `${activeBuilding.floors}층` : '-'} />
                <InfoRow label="지하층" value={activeBuilding.basements ? `${activeBuilding.basements}층` : '-'} />
                <InfoRow label="사용승인일" value={formatDate(activeBuilding.use_approval_date)} />
                <InfoRow label="건축물 구분" value={activeBuilding.regstr_kind || '-'} />
              </div>

              {buildingInfo.matched_count > 1 && (
                <div className="rounded-lg border border-coral/10 bg-sand px-3 py-2 text-xs text-slate-600">
                  후보 중 하나를 클릭하면 상세 정보가 바뀐다.
                </div>
              )}

              <details className="rounded-lg border border-coral/15 px-3 py-2">
                <summary className="cursor-pointer text-sm font-medium text-ink">원문 필드 보기</summary>
                <div className="mt-3 space-y-2 text-xs text-slate-600">
                  <InfoRow label="주소" value={activeBuilding.address || '-'} compact />
                  <InfoRow label="지번주소" value={activeBuilding.lot_address || '-'} compact />
                  <InfoRow label="법정동코드" value={activeBuilding.legal_code || '-'} compact />
                  <InfoRow label="시군구코드" value={activeBuilding.sigungu_code || '-'} compact />
                  <InfoRow label="세대수" value={activeBuilding.households || '-'} compact />
                  <InfoRow label="준공일" value={formatDate(activeBuilding.completion_date)} compact />
                  <InfoRow label="허가일" value={formatDate(activeBuilding.permission_date)} compact />
                </div>
              </details>
            </div>
          )}

          {buildingInfo && !activeBuilding && buildingCandidates.length === 0 && (
            <div className="rounded-lg border border-dashed border-coral/20 bg-sand px-3 py-4 text-sm text-slate-500">
              후보가 없다. 주소를 다시 검색하거나 지도를 클릭해라.
            </div>
          )}
        </aside>
      </div>

      {rentData && rentData.total > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-slate-500">
            {sido} {sigungu} {dong} · {dealFrom} ~ {dealTo} · 총 {rentData.total}건
          </p>
          <div className="overflow-x-auto rounded-xl border border-coral/15">
            <table className="w-full text-sm">
              <thead className="bg-sand text-xs text-slate-500">
                <tr>
                  {COLUMNS[propertyType].headers.map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-coral/10">
                {rentData.items.map((item, i) => (
                  <tr key={i} className="hover:bg-coral/5">
                    <td className="px-3 py-2">{item.buildingNm}</td>
                    <td className="px-3 py-2">{item.umdNm}</td>
                    <td className="px-3 py-2">{item.excluUseAr}</td>
                    <td className="px-3 py-2">{item.deposit}</td>
                    <td className="px-3 py-2">{renderMonthlyRent(item.monthlyRent)}</td>
                    {propertyType !== 'sh' && <td className="px-3 py-2">{item.floor}</td>}
                    <td className="px-3 py-2">{item.contractType || '-'}</td>
                    <td className="px-3 py-2">{getLeaseType(item.monthlyRent)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function formatDate(value) {
  if (!value) return '-';
  const normalized = String(value).trim();
  if (normalized.length !== 8) return normalized;
  return `${normalized.slice(0, 4)}-${normalized.slice(4, 6)}-${normalized.slice(6, 8)}`;
}

function InfoRow({ label, value, compact = false }) {
  return (
    <div className={`flex items-start justify-between gap-3 ${compact ? 'text-xs' : 'text-sm'}`}>
      <span className="shrink-0 text-slate-500">{label}</span>
      <span className="text-right font-medium text-ink">{value}</span>
    </div>
  );
}

export default MapPage;
