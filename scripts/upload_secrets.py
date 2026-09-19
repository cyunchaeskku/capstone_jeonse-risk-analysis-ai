# .env의 API 키를 Secret Manager에 등록한다. 값은 출력하지 않는다.
# 실행: python scripts/upload_secrets.py (키를 바꾸면 다시 실행 → 새 버전 추가)
import subprocess
from pathlib import Path

from dotenv import dotenv_values

env = dotenv_values(Path(__file__).resolve().parent.parent / ".env")  # 따옴표를 벗겨서 읽는다
names = [
    "OPENAI_API_KEY", "DATA_GO_KR_API_KEY",
    "NAVER_MAPS_CLIENT_ID", "NAVER_MAPS_CLIENT_SECRET",
    "NAVER_SEARCH_CLIENT_ID", "NAVER_SEARCH_CLIENT_SECRET",
    "VWORLD_API_KEY",
]
for n in names:
    v = (env.get(n) or "").strip()
    if not v:
        print(f"{n}: .env에 없음 → 건너뜀")
        continue
    exists = subprocess.run(["gcloud", "secrets", "describe", n], capture_output=True).returncode == 0
    cmd = (["gcloud", "secrets", "versions", "add", n, "--data-file=-"] if exists
           else ["gcloud", "secrets", "create", n, "--replication-policy=automatic", "--data-file=-"])
    r = subprocess.run(cmd, input=v.encode(), capture_output=True)
    print(f"{n}: {'OK' if r.returncode == 0 else 'FAIL ' + r.stderr.decode()[-200:]}")
