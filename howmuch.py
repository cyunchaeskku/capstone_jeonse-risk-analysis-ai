import requests
import os
from dotenv import load_dotenv

load_dotenv()

SERVICE_KEY = os.getenv("DATA_GO_KR_API_KEY")
LAWD_CD = "41113"   # 수원시 권선구 탑동
DEAL_YMD = "202503"

base_url = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"
url = f"{base_url}?serviceKey={SERVICE_KEY}&LAWD_CD={LAWD_CD}&DEAL_YMD={DEAL_YMD}&numOfRows=1000&pageNo=1"

resp = requests.get(url)
print("Status:", resp.status_code)
print("Response:", resp.text[:500])

import xml.etree.ElementTree as ET
root = ET.fromstring(resp.text)

items = root.findall(".//item")
results = [i for i in items if "탑동" in (i.findtext("aptNm") or "")]

print(f"탑동 건수: {len(results)}")
for item in results:
    apt = item.findtext("aptNm")
    dong = item.findtext("umdNm")
    area = item.findtext("excluUseAr")
    deposit = item.findtext("deposit")
    monthly = item.findtext("monthlyRent")
    floor_ = item.findtext("floor")
    print(f"  [{dong}] {apt} | {area}㎡ | 보증금 {deposit}만 | 월세 {monthly}만 | {floor_}층")
