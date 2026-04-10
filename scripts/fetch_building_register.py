"""Temporary helper for fetching building register information.

This script calls the Ministry of Land's Building HUB building register API
using the `DATA_GO_KR_API_KEY` value from `.env`.

This version uses hard-coded dong-level parameters for quick local testing.
"""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from urllib.parse import unquote

import requests
from dotenv import load_dotenv


BASE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

SIGUNGU_CD = "11650"
BJDONG_CD = "10800"
PLAT_GB_CD = "0"
START_DATE = None
END_DATE = None
NUM_OF_ROWS = 100
RESPONSE_FORMAT = "xml"
RAW_OUTPUT = False


def fetch_building_register(page_no: int) -> requests.Response:
    load_dotenv()
    api_key = os.getenv("DATA_GO_KR_API_KEY")
    if not api_key:
        raise SystemExit("DATA_GO_KR_API_KEY 가 .env 에 없음")
    api_key = unquote(api_key)

    params: dict[str, object] = {
        "serviceKey": api_key,
        "sigunguCd": SIGUNGU_CD,
        "bjdongCd": BJDONG_CD,
        "platGbCd": PLAT_GB_CD,
        "numOfRows": NUM_OF_ROWS,
        "pageNo": page_no,
    }
    if START_DATE:
        params["startDate"] = START_DATE
    if END_DATE:
        params["endDate"] = END_DATE
    if RESPONSE_FORMAT == "json":
        params["_type"] = "json"

    return requests.get(BASE_URL, params=params, timeout=30)


def print_xml_preview(text: str) -> None:
    root = ET.fromstring(text)
    header_code = root.findtext(".//header/resultCode")
    header_msg = root.findtext(".//header/resultMsg")
    total_count = root.findtext(".//body/totalCount")

    print(f"status: {header_code}")
    print(f"message: {header_msg}")
    print(f"totalCount: {total_count}")
    print("-" * 40)

    items = root.findall(".//item")
    if not items:
        print("no items")
        return

    for idx, item in enumerate(items, start=1):
        data = {child.tag: (child.text or "") for child in list(item)}
        print(f"[item {idx}]")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        print("-" * 40)


def print_json_preview(text: str) -> None:
    payload = json.loads(text)
    response = payload.get("response", {})
    header = response.get("header", {})
    body = response.get("body", {})

    print(f"status: {header.get('resultCode')}")
    print(f"message: {header.get('resultMsg')}")
    print(f"totalCount: {body.get('totalCount')}")
    print("-" * 40)

    items = body.get("items", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]

    if not items:
        print("no items")
        return

    for idx, item in enumerate(items, start=1):
        print(f"[item {idx}]")
        print(json.dumps(item, ensure_ascii=False, indent=2))
        print("-" * 40)


def parse_xml_response(text: str) -> tuple[str | None, str | None, int, list[dict[str, str]]]:
    root = ET.fromstring(text)
    header_code = root.findtext(".//header/resultCode")
    header_msg = root.findtext(".//header/resultMsg")
    total_count_text = root.findtext(".//body/totalCount") or "0"

    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        items.append({child.tag: (child.text or "") for child in list(item)})

    return header_code, header_msg, int(total_count_text), items


def main() -> int:
    page_no = 1
    all_items: list[dict[str, str]] = []
    total_count = None
    header_code = None
    header_msg = None

    while True:
        response = fetch_building_register(page_no)
        print(f"HTTP {response.status_code} page={page_no}")

        if RAW_OUTPUT:
            print(response.text)
            return 0

        try:
            if RESPONSE_FORMAT == "json":
                print_json_preview(response.text)
                return 0

            header_code, header_msg, page_total_count, items = parse_xml_response(response.text)
            if total_count is None:
                total_count = page_total_count

            all_items.extend(items)
            if len(all_items) >= page_total_count or not items:
                break
            page_no += 1
        except Exception as exc:  # temporary debug helper
            print("parse error:", exc, file=sys.stderr)
            print(response.text, file=sys.stderr)
            return 1

    print(f"status: {header_code}")
    print(f"message: {header_msg}")
    print(f"totalCount: {total_count}")
    print(f"fetchedCount: {len(all_items)}")
    print("-" * 40)

    if not all_items:
        print("no items")
        return 0

    for idx, item in enumerate(all_items, start=1):
        print(f"[item {idx}]")
        print(json.dumps(item, ensure_ascii=False, indent=2))
        print("-" * 40)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
