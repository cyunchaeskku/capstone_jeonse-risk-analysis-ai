#!/usr/bin/env bash
# Cloud SQL 작업 세션: 인스턴스 시작 → Auth Proxy(localhost:5433) 실행 → Ctrl+C 시 인스턴스 중지.
# 프록시가 떠 있는 동안 다른 터미널에서 ingest_*.py, make_vectorDB_*.py, alembic을 실행한다.
#
# 실행: bash scripts/db_session.sh
set -euo pipefail

PROJECT=project-1bbc94dc-a155-4b6b-8a5
INSTANCE=jeonse-risk-analysi
CONNECTION="$PROJECT:asia-northeast3:$INSTANCE"
PORT=5433  # 로컬 PostgreSQL(5432)과 겹치지 않게

stop_instance() {
  echo
  echo "인스턴스 중지 중..."
  gcloud sql instances patch "$INSTANCE" --project="$PROJECT" --activation-policy=NEVER --quiet
  echo "중지 완료"
}

echo "인스턴스 시작 중... (1~2분)"
gcloud sql instances patch "$INSTANCE" --project="$PROJECT" --activation-policy=ALWAYS --quiet
trap stop_instance EXIT

# --gcloud-auth: application-default 자격 증명 대신 gcloud 로그인 계정으로 인증
echo "프록시 실행: localhost:$PORT (종료하려면 Ctrl+C)"
cloud-sql-proxy --gcloud-auth --port "$PORT" "$CONNECTION"
