# Backend

FastAPI 기반의 최소 백엔드가 `backend/app` 아래에 구현되어 있다.

## Run

환경변수는 리포 루트의 `.env`에서 읽는다 (`backend/app/settings.py`, pydantic-settings).
`.env`는 gitignore 대상이므로 각자 만들어야 한다.

```bash
# .env (리포 루트)
OPENAI_API_KEY=your_api_key
DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/jeonse_db"
```

`DATABASE_URL`은 **필수**다. 기본값이 없어서 미설정 시 기동 즉시 `ValidationError`로 실패한다 —
자격증명을 소스코드에 두지 않기 위함이다. `OPENAI_MODEL`, `VECTOR_DB_PATH`는 기본값이 있어 생략 가능하다.

```bash
uvicorn backend.app.main:app --reload
```

기본 엔드포인트:

- `GET /`
- `GET /health`
- `POST /analyses`
- `POST /registry/parse`
- `POST /registry/inspect`
- `GET /analyses/{analysis_id}`
- `GET /jeonse-data`
- `GET /building-register`
- `GET /listing-checks/search`
- `POST /listing-checks/analyze`
- `POST /qa`

## PostgreSQL (법령 데이터 저장용)

### 스키마 정의 위치

| 목적 | 파일 |
|------|------|
| SQLAlchemy 모델 (컬럼 구조) | `backend/app/models/law.py` |
| DB 엔진/세션 설정 | `backend/app/db.py` |
| Alembic 마이그레이션 DDL | `RDB/alembic/versions/b714fd4ea8de_create_law_tables.py` |

테이블 3개: `laws`, `law_relations`, `law_articles`

### Docker 실행

```bash
# 컨테이너 시작
docker compose -f RDB/docker-compose.yml up -d

# 컨테이너 상태 확인
docker compose -f RDB/docker-compose.yml ps

# 컨테이너 중지
docker compose -f RDB/docker-compose.yml down
```

### DB 접속 및 조회

```bash
# psql 접속 (컨테이너 실행 중일 때)
docker exec -it jeonse_postgres psql -U postgres -d jeonse_db

# 테이블 목록
\dt

# 테이블별 컬럼 구조
\d laws
\d law_articles
\d law_relations

# 데이터 조회 예시
SELECT * FROM laws;
SELECT * FROM law_articles WHERE law_id = 1;

# 나가기
\q
```

### 마이그레이션

```bash
# 새 마이그레이션 생성 (모델 변경 후)
alembic -c RDB/alembic.ini revision --autogenerate -m "설명"

# 마이그레이션 적용
alembic -c RDB/alembic.ini upgrade head

# 현재 상태 확인
alembic -c RDB/alembic.ini current
```

## Notes

- 현재 구현은 초기 연결용 데모로, 결과 저장은 메모리 기반이다.
- 위험도 평가는 매우 단순한 규칙 예시만 포함한다.
- 부동산 등기사항증명서 PDF 파서는 현재 `채권최고액` 추출용 기초 구현이다.
- `POST /registry/inspect`는 등기 텍스트를 OpenAI 모델에 전달해 표제부/갑구/을구 특이사항을 구조화한다.
- 법률 QA는 LangGraph로 질문을 분기하고, 단순 질문은 바로 답변하며 법령 질문만 FAISS 벡터 검색을 거친다.
- 벡터 검색용 인덱스는 `vectorDB/laws_faiss`를 기본 경로로 사용한다.
- 프론트 개발 서버 연동을 위해 기본 CORS가 `localhost:5173`에 열려 있다.
