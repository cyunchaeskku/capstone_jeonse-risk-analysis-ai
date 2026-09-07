"""공시가격 오픈API(VWorld NED) 탐침 스크립트.

주소 → PNU(19자리)를 조립한 뒤 공동주택가격·개별주택가격·개별공시지가를 조회한다.

주의: 이 API들은 data.go.kr이 아니라 VWorld(공간정보 오픈플랫폼)의 인증키를 쓴다.
      https://www.vworld.kr 에서 발급받아 .env에 VWORLD_API_KEY로 넣는다.

    python scripts/probe_official_price.py --address "서울특별시 강남구 대치동 316" --year 2026
    python scripts/probe_official_price.py --pnu 1168010600103160000 --year 2026 --dong 2 --ho 607

주요 응답 필드
    공동주택가격  pblntfPc     공시가격(원)      prvuseAr 전용면적(㎡)
    개별주택가격  pblntfPc     공시가격(원)
    개별공시지가  pblntfPclnd  공시지가(원/㎡)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.main import _extract_bun_ji, _lookup_legal_code  # noqa: E402


# VWorld NED. 경로는 실제 호출로 확인됨(존재하는 서비스, 인증키만 필요).
ENDPOINTS = [
    ("공동주택가격", "https://api.vworld.kr/ned/data/getApartHousingPriceAttr"),
    ("개별주택가격", "https://api.vworld.kr/ned/data/getIndvdHousingPriceAttr"),
    ("개별공시지가", "https://api.vworld.kr/ned/data/getIndvdLandPriceAttr"),
]


def build_pnu(address: str) -> str | None:
    """법정동코드(10) + 대장구분(1) + 본번(4) + 부번(4) = PNU 19자리."""
    legal_code = _lookup_legal_code(address)
    if not legal_code or len(legal_code) < 10:
        return None
    bun, ji = _extract_bun_ji(address)
    if not bun:
        return None
    mountain = "2" if "산" in address.split()[-2:] else "1"
    return f"{legal_code[:10]}{mountain}{bun}{ji or '0000'}"


def describe(body: str) -> str:
    """응답 필드명을 그대로 보여준다. 매핑하려면 필드명을 알아야 한다."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return f"(파싱 불가) {body[:400]}"

    code = root.findtext(".//resultCode")
    if code:
        return f"resultCode={code} resultMsg={root.findtext('.//resultMsg')}"

    lines = [f"totalCount={root.findtext('.//totalCount')}"]
    for field in root.findall(".//field")[:3]:
        lines.append("  " + ", ".join(f"{c.tag}={c.text}" for c in list(field)))
    return "\n".join(lines) or re.sub(r"\s+", " ", body)[:400]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", help="지번 주소")
    parser.add_argument("--pnu", help="PNU 19자리를 직접 지정")
    parser.add_argument("--year", default="", help="기준연도 YYYY (생략 시 전체 연도가 섞여 나온다)")
    parser.add_argument("--dong", default="", help="동명 (공동주택 호실 특정용)")
    parser.add_argument("--ho", default="", help="호명 (공동주택 호실 특정용)")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    api_key = os.getenv("VWORLD_API_KEY")
    if not api_key:
        print("VWORLD_API_KEY가 없습니다. https://www.vworld.kr 에서 인증키를 발급받으세요.")
        return 1

    pnu = args.pnu
    if not pnu:
        if not args.address:
            print("--address 또는 --pnu 중 하나는 필요합니다.")
            return 1
        pnu = build_pnu(args.address)
        if not pnu:
            print(f"PNU를 조립하지 못했습니다: {args.address}")
            return 1

    print(f"PNU: {pnu}  (법정동 {pnu[:10]} / 대장 {pnu[10]} / 본번 {pnu[11:15]} / 부번 {pnu[15:]})")

    for label, url in ENDPOINTS:
        params = {
            "key": api_key,
            # domain은 필수다. 없으면 INCORRECT_KEY로 거부된다(인증키 발급 시 등록한 서비스URL).
            "domain": os.getenv("VWORLD_API_DOMAIN", "http://localhost:5173"),
            "pnu": pnu,
            "format": "xml",
            "numOfRows": "10",
            "pageNo": "1",
        }
        if args.year:
            params["stdrYear"] = args.year
        if args.dong:
            params["dongNm"] = args.dong
        if args.ho:
            params["hoNm"] = args.ho

        print(f"\n=== {label} ===")
        try:
            response = requests.get(url, params=params, timeout=20)
        except requests.RequestException as exc:
            print(f"  요청 실패: {exc}")
            continue

        print(f"  HTTP {response.status_code}")
        print(re.sub(r"^", "  ", describe(response.text), flags=re.M))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
