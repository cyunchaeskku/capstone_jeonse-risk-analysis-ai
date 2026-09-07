"""상업·업무용 부동산 매매 실거래가 API 조회용 스크립트."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv


BASE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lawd-cd", default="11530", help="시군구 법정동 코드 앞 5자리")
    parser.add_argument("--month", default=date.today().strftime("%Y%m"), help="계약년월 YYYYMM")
    parser.add_argument("--months", type=int, default=1, help="--month부터 과거로 조회할 개월 수")
    parser.add_argument("--dong", help="필터할 법정동명")
    parser.add_argument("--jibun", help="필터할 지번")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("DATA_GO_KR_API_KEY")
    if not api_key:
        raise SystemExit("DATA_GO_KR_API_KEY 가 .env 에 없음")

    year, month = int(args.month[:4]), int(args.month[4:])
    months = []
    for _ in range(args.months):
        months.append(f"{year}{month:02d}")
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)

    matches = []
    for deal_month in reversed(months):
        try:
            response = requests.get(
                BASE_URL,
                params={"serviceKey": unquote(api_key), "LAWD_CD": args.lawd_cd, "DEAL_YMD": deal_month, "numOfRows": 1000, "pageNo": 1},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise SystemExit(f"API 요청 실패: {type(exc).__name__}") from exc

        root = ET.fromstring(response.text)
        print(f"{deal_month}: HTTP {response.status_code}, totalCount={root.findtext('.//totalCount') or '0'}")
        for item in root.findall(".//item"):
            data = {child.tag: child.text or "" for child in item}
            if (args.dong and data.get("umdNm") != args.dong) or (args.jibun and data.get("jibun") != args.jibun):
                continue
            matches.append(data)

    print(f"matchingCount: {len(matches)}")
    for index, item in enumerate(matches, start=1):
        print(f"\n[item {index}]")
        print(json.dumps(item, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
