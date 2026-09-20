#!/usr/bin/env bash
# Cloud SQL 작업 세션: Auth Proxy(localhost:5433) 실행. Ctrl+C로 종료.
# 프록시가 떠 있는 동안 다른 터미널에서 ingest_*.py, make_vectorDB_*.py, alembic을 실행한다.
#
# 인스턴스는 백엔드 런타임(로그인·세션)이 쓰므로 상시 가동이다. 이 스크립트는 켜고 끄지 않는다.
#
# 실행: bash scripts/db_session.sh
set -euo pipefail

PROJECT=project-1bbc94dc-a155-4b6b-8a5
INSTANCE=jeonse-risk-analysi
CONNECTION="$PROJECT:asia-northeast3:$INSTANCE"
PORT=5433  # 로컬 PostgreSQL(5432)과 겹치지 않게

STATE=$(gcloud sql instances describe "$INSTANCE" --project="$PROJECT" --format="value(state)")
if [ "$STATE" != "RUNNABLE" ]; then
  echo "인스턴스가 실행 중이 아니다 (상태: $STATE)." >&2
  echo "gcloud sql instances patch $INSTANCE --project=$PROJECT --activation-policy=ALWAYS" >&2
  exit 1
fi

# --gcloud-auth: application-default 자격 증명 대신 gcloud 로그인 계정으로 인증
echo "프록시 실행: localhost:$PORT (종료하려면 Ctrl+C)"
cloud-sql-proxy --gcloud-auth --port "$PORT" "$CONNECTION"
