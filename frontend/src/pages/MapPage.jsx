import { useEffect, useRef, useState } from 'react';

function MapPage() {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markerRef = useRef(null);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const clientId = import.meta.env.VITE_NAVER_MAPS_CLIENT_ID;
    const scriptId = 'naver-maps-script';

    function initMap() {
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
      document.getElementById(scriptId).addEventListener('load', initMap);
      return;
    }

    const script = document.createElement('script');
    script.id = scriptId;
    script.src = `https://openapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${clientId}`; // ncpClientId -> ncpKeyId로 변경됨
    script.onload = initMap;
    document.head.appendChild(script);
  }, []);

  async function handleSearch() {
    if (!query.trim()) return;
    setError('');
    if (!window.naver?.maps) {
      setError('지도가 아직 로딩 중입니다. 잠시 후 다시 시도하세요.');
      return;
    }

    const res = await fetch(`http://localhost:8000/geocode?query=${encodeURIComponent(query)}`);
    if (!res.ok) {
      setError('주소 검색 중 오류가 발생했습니다.');
      return;
    }
    const data = await res.json();
    if (!data.result) {
      setError('검색 결과가 없습니다.');
      return;
    }
    const coords = new window.naver.maps.LatLng(data.result.y, data.result.x);
    mapInstanceRef.current.setCenter(coords);
    mapInstanceRef.current.setZoom(16);

    if (markerRef.current) markerRef.current.setMap(null);
    markerRef.current = new window.naver.maps.Marker({
      position: coords,
      map: mapInstanceRef.current,
    });
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') handleSearch();
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-6 py-8">
      <h1 className="text-xl font-semibold text-ink">지도 검색</h1>
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="주소를 입력하세요 (예: 서울특별시 강남구 테헤란로)"
          className="flex-1 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-ink placeholder:text-slate-400 focus:border-coral focus:outline-none"
        />
        <button
          onClick={handleSearch}
          className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
        >
          검색
        </button>
      </div>
      {error && <p className="text-sm text-red-500">{error}</p>}
      <div ref={mapRef} className="h-[520px] w-full rounded-xl border border-slate-200 shadow-sm" />
    </div>
  );
}

export default MapPage;
