#!/usr/bin/env bash
# 로컬 FAISS 인덱스를 GCS 버킷에 올린다. 버킷이 인덱스의 원본이다.
# make_vectorDB_*.py 실행 후 돌리고, 그 다음 redeploy_backend.sh로 재배포한다.
# 버킷은 객체 버전 관리를 켜 두어 덮어쓴 이전 인덱스도 복원할 수 있다.
#
# 실행: bash scripts/upload_vectordb.sh
set -euo pipefail

BUCKET=gs://project-1bbc94dc-a155-4b6b-8a5-vectordb

cd "$(dirname "$0")/.."

# documents.jsonl은 --append가 기존 인덱스를 읽을 때 필요해 폴더째 올린다.
for name in laws_faiss precedents_faiss; do
  dir="vectorDB/$name"
  [[ -f "$dir/manifest.json" ]] || { echo "오류: $dir/manifest.json 없음" >&2; exit 1; }
  echo "== $name"
  gcloud storage rsync "$dir" "$BUCKET/$name"
done
