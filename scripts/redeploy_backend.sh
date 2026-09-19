#!/usr/bin/env bash
# 백엔드를 Cloud Build로 빌드해 Cloud Run에 재배포한다.
# 환경 변수·Secret·리소스 설정은 기존 서비스 설정이 유지된다.
#
# 실행: bash scripts/redeploy_backend.sh           # 태그 = 커밋 해시
#       bash scripts/redeploy_backend.sh demo-day  # 태그 직접 지정
set -euo pipefail

PROJECT=project-1bbc94dc-a155-4b6b-8a5
REGION=asia-northeast3
SERVICE=jeonse-backend

cd "$(dirname "$0")/.."

# vectorDB/는 gitignore 대상이라 로컬 인덱스가 그대로 이미지에 들어간다.
for f in vectorDB/laws_faiss/index.faiss vectorDB/laws_faiss/index.pkl \
         vectorDB/precedents_faiss/index.faiss vectorDB/precedents_faiss/index.pkl; do
  [[ -f "$f" ]] || { echo "오류: $f 없음. make_vectorDB_*.py로 먼저 인덱스를 만든다." >&2; exit 1; }
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
gcloud builds submit --project="$PROJECT" --region="$REGION" --tag "$IMAGE" .
gcloud run deploy "$SERVICE" --project="$PROJECT" --region="$REGION" --image="$IMAGE"
