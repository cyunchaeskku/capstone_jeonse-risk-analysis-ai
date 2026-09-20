#!/usr/bin/env bash
# 백엔드를 Cloud Build로 빌드해 Cloud Run에 재배포한다.
# FAISS 인덱스는 GCS 버킷에서 받는다 (cloudbuild.yaml). 인덱스를 새로 만들었으면 upload_vectordb.sh 먼저.
# 환경 변수·Secret·리소스 설정은 기존 서비스 설정이 유지된다.
#
# 실행: bash scripts/redeploy_backend.sh           # 태그 = 커밋 해시
#       bash scripts/redeploy_backend.sh demo-day  # 태그 직접 지정
set -euo pipefail

PROJECT=project-1bbc94dc-a155-4b6b-8a5
REGION=asia-northeast3
SERVICE=jeonse-backend
BUCKET=project-1bbc94dc-a155-4b6b-8a5-vectordb

cd "$(dirname "$0")/.."

# 로컬에서 인덱스를 새로 만들고 업로드를 잊으면 옛 인덱스로 배포된다. manifest로 비교해 막는다.
for name in laws_faiss precedents_faiss; do
  local_manifest="vectorDB/$name/manifest.json"
  [[ -f "$local_manifest" ]] || continue
  if ! gcloud storage cat "gs://$BUCKET/$name/manifest.json" | cmp -s - "$local_manifest"; then
    echo "오류: 로컬 $name 인덱스가 GCS와 다르다. bash scripts/upload_vectordb.sh 먼저 실행." >&2
    exit 1
  fi
done

# 기본 태그는 커밋 해시. 커밋 안 된 변경이 있으면 -dirty를 붙여 구분한다.
if [[ $# -ge 1 ]]; then
  TAG=$1
else
  TAG=$(git rev-parse --short HEAD)
  [[ -z "$(git status --porcelain)" ]] || TAG="$TAG-dirty-$(date +%m%d%H%M)"
fi
IMAGE="$REGION-docker.pkg.dev/$PROJECT/jeonse/backend:$TAG"

echo "이미지: $IMAGE"
gcloud builds submit --project="$PROJECT" --region="$REGION" --config=cloudbuild.yaml \
  --substitutions="_IMAGE=$IMAGE,_BUCKET=$BUCKET" .
gcloud run deploy "$SERVICE" --project="$PROJECT" --region="$REGION" --image="$IMAGE"
