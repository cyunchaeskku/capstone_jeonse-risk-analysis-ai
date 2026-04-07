import { useEffect, useRef, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const COLUMNS = {
  apt:  { buildingNm: '단지명',    headers: ['단지명',    '동', '전용면적(㎡)', '보증금(만원)', '월세(만원)', '층', '계약유형'] },
  offi: { buildingNm: '오피스텔명', headers: ['오피스텔명', '동', '전용면적(㎡)', '보증금(만원)', '월세(만원)', '층', '계약유형'] },
  rh:   { buildingNm: '건물명',    headers: ['건물명',    '동', '전용면적(㎡)', '보증금(만원)', '월세(만원)', '층', '계약유형'] },
  sh:   { buildingNm: '건물유형',   headers: ['건물유형',  '동', '연면적(㎡)',   '보증금(만원)', '월세(만원)', '계약유형'] },
};

const CURRENT_YMD = (() => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  return `${y}${m}`;
})();

function MapPage() {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markerRef = useRef(null);

  const [sido, setSido] = useState('');
  const [sigungu, setSigungu] = useState('');
  const [dong, setDong] = useState('');
  const [dealFrom, setDealFrom] = useState(CURRENT_YMD);
  const [dealTo, setDealTo] = useState(CURRENT_YMD);
  const [propertyType, setPropertyType] = useState('apt');

  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [rentData, setRentData] = useState(null);

  useEffect(() => {
    const clientId = import.meta.env.VITE_NAVER_MAPS_CLIENT_ID;
    const scriptId = 'naver-maps-script';

    function initMap() {
      mapInstanceRef.current = new window.naver.maps.Map(mapRef.current, {
        center: new window.naver.maps.LatLng(37.5666805, 126.9784147),
        zoom: 14,
      });
    }

    if (window.naver?.maps) { initMap(); return; }
    if (document.getElementById(scriptId)) {
      document.getElementById(scriptId).addEventListener('load', initMap);
      return;
    }

    const script = document.createElement('script');
    script.id = scriptId;
    script.src = `https://openapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${clientId}`;
    script.onload = initMap;
    document.head.appendChild(script);
  }, []);

  async function handleSearch() {
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
            const coords = new window.naver.maps.LatLng(geoData.result.y, geoData.result.x);
            mapInstanceRef.current.setCenter(coords);
            mapInstanceRef.current.setZoom(16);
            if (markerRef.current) markerRef.current.setMap(null);
            markerRef.current = new window.naver.maps.Marker({
              position: coords,
              map: mapInstanceRef.current,
            });
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

  function handleKeyDown(e) {
    if (e.key === 'Enter') handleSearch();
  }

  const inputCls =
    'rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-ink placeholder:text-slate-400 focus:border-coral focus:outline-none';

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 py-8">
      <h1 className="text-xl font-semibold text-ink">지도 검색</h1>

      <div className="flex flex-wrap gap-2">
        <input
          type="text"
          value={sido}
          onChange={(e) => setSido(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="시·도 (예: 서울특별시)"
          className={`${inputCls} w-32`}
        />
        <input
          type="text"
          value={sigungu}
          onChange={(e) => setSigungu(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="시·군·구 (예: 수원시 권선구)"
          className={`${inputCls} w-44`}
        />
        <input
          type="text"
          value={dong}
          onChange={(e) => setDong(e.target.value)}
          onKeyDown={handleKeyDown}
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
          onKeyDown={handleKeyDown}
          placeholder="시작 (예: 202501)"
          className={`${inputCls} w-32`}
        />
        <span className="self-center text-slate-400">~</span>
        <input
          type="text"
          value={dealTo}
          onChange={(e) => setDealTo(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="종료 (예: 202503)"
          className={`${inputCls} w-32`}
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
        >
          {loading ? '검색 중…' : '검색'}
        </button>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      <div ref={mapRef} className="h-[400px] w-full rounded-xl border border-slate-200 shadow-sm" />

      {rentData && rentData.total > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-slate-500">
            {sido} {sigungu} {dong} · {dealFrom} ~ {dealTo} · 총 {rentData.total}건
          </p>
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  {COLUMNS[propertyType].headers.map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rentData.items.map((item, i) => (
                  <tr key={i} className="hover:bg-slate-50">
                    <td className="px-3 py-2">{item.buildingNm}</td>
                    <td className="px-3 py-2">{item.umdNm}</td>
                    <td className="px-3 py-2">{item.excluUseAr}</td>
                    <td className="px-3 py-2">{item.deposit}</td>
                    <td className="px-3 py-2">{item.monthlyRent || '-'}</td>
                    {propertyType !== 'sh' && <td className="px-3 py-2">{item.floor}</td>}
                    <td className="px-3 py-2">{item.contractType || '-'}</td>
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

export default MapPage;
