# scripts/

법령 데이터 수집 관련 스크립트 모음.

## 파일 구조

| 파일 | 설명 |
|------|------|
| `ingest_laws.py` | 법령 데이터 수집 메인 스크립트 |
| `make_vectorDB_laws.py` | RDB 법령/조문 데이터를 FAISS 벡터DB로 변환 |
| `make_vectorDB_precedents.py` | RDB 판례를 섹션별로 청킹해 별도 FAISS 벡터DB로 변환 |
| `test_nrg_trade.py` | 상업·업무용 부동산 매매 실거래가 API 단일 월 조회 |
| `law_targets.yaml` | 수집 대상 법령 목록 (설정 파일) |
| `collect_precedent_summaries.py` | 키워드별 판례 후보 검색과 ID별 요약 JSONL 수집 |
| `precedent_targets.yaml` | 판례 후보 검색어와 분류 |
| `classify_precedent_relevance.py` | 판례 요약을 LLM에 읽혀 전세사기 관련성(`core`/`related`/`unrelated`) 분류 |
| `collect_precedent_texts.py` | 분류 결과에서 선별한 판례의 전문 수집 (기본 `core`) |
| `ingest_precedents.py` | 판례 전문 JSONL을 파싱해 `precedents` 테이블에 적재 |
| `redeploy_backend.sh` | 백엔드 이미지 빌드(Cloud Build) 후 Cloud Run 재배포 |
| `upload_secrets.py` | `.env`의 API 키를 Secret Manager에 등록 (값 출력 안 함) |

---

## ingest_laws.py

korean-law CLI를 통해 법령 전문을 가져와 PostgreSQL DB에 저장한다.

### 전제 조건

- Docker 컨테이너 실행 중 (`docker compose -f RDB/docker-compose.yml up -d`)
- Alembic 마이그레이션 적용 완료 (`alembic -c RDB/alembic.ini upgrade head`)
- `.venv` 활성화 상태

### 실행

```bash
# 전체 법령 수집 (law_targets.yaml 기준)
python scripts/ingest_laws.py

# 특정 법령만 수집
python scripts/ingest_laws.py --only "부동산등기법"

# DB 저장 없이 파싱 결과만 확인
python scripts/ingest_laws.py --only "부동산등기법" --dry-run
```

### 동작 흐름

1. `law_targets.yaml`에서 수집 대상 법령 이름 목록 로드
2. 각 법령마다:
   - `korean-law search_law --query "법령명"` → mst, 법령ID, 카테고리, 공포일 획득
   - `korean-law get_law_text --lawId <법령ID>` → 목차에서 조문 번호 목록 추출
   - `korean-law get_batch_articles --lawId <법령ID> --articles '[...]'` → 조문 본문 일괄 조회 (50개 단위 청크)

조회는 법령ID로 한다. 2026-09 기준 법제처 API가 `--mst` 조회에 에러 페이지를 반환한다 (mst는 DB에 계속 저장).
3. `laws` 테이블에 mst 기준 upsert, `law_articles` 테이블에 (law_id, jo_code) 기준 upsert

### 알려진 사항

- **시행일(enforcement_date)**: `search_law` 출력에 시행일 필드가 없어 현재 null로 저장됨. `get_law_text` 헤더에는 존재하므로 필요 시 보완 가능.
- **조문 수 차이**: 목차 조문 수와 실제 파싱 수가 1~2개 차이날 수 있음. 조문 번호 형식이 파서 패턴과 미세하게 다른 경우.
- **민법**: 조문 수가 많아 수집 시간이 오래 걸릴 수 있음.

---

## law_targets.yaml

수집 대상 법령 목록. 스크립트를 수정하지 않고 이 파일에만 항목을 추가/제거하면 된다.

```yaml
laws:
  - name: 부동산등기법
  - name: 주택임대차보호법
  - name: 민법
    scope_note: "임대차 편 (제618조~제654조)"  # 메모용, 실제 필터링 아님
```

`scope_note`는 사람이 읽기 위한 메모이며 수집 범위에 영향을 주지 않는다.

### 새 법령 추가 방법

`law_targets.yaml`에 항목을 추가하고 수집 스크립트를 실행하면 된다.

```yaml
laws:
  - name: 부동산등기법
  - name: 집합건물의 소유 및 관리에 관한 법률  # 추가 예시
```

이후:

```bash
python scripts/ingest_laws.py --only "집합건물의 소유 및 관리에 관한 법률"
```

법령 이름은 korean-law `search_law` 기준으로 정확하게 입력해야 한다. 약칭이 자동 변환되기도 하지만, 검색 결과 상위 항목이 원하는 법령인지 dry-run으로 먼저 확인하는 것을 권장한다.

---

## collect_precedent_summaries.py

`precedent_targets.yaml`의 검색어를 모두 페이지 끝까지 조회하고, 판례일련번호로 중복을 제거한 뒤 `summarize_precedent` 결과를 JSONL로 저장한다. 이미 출력 파일에 저장된 ID는 다시 조회하지 않는다.

```bash
# 전체 후보 검색 및 요약 수집
python scripts/collect_precedent_summaries.py

# 특정 검색어만 확인
python scripts/collect_precedent_summaries.py --only '임대차보증금'

# 외부 API 호출 없이 검색 결과 파서 확인
python scripts/collect_precedent_summaries.py --self-check
```

기본 출력 경로는 `data/precedent_summaries.jsonl`이다. 각 행에는 판례 메타데이터, 매칭된 검색어·분류, CLI 요약 원문이 들어간다.

---

## test_nrg_trade.py

```bash
# 구로구 최근 12개월에서 고척동 76-32 매매 거래 확인
.venv/bin/python scripts/test_nrg_trade.py --lawd-cd 11530 --month 202608 --months 12 --dong 고척동 --jibun 76-32
```

---

## make_vectorDB_laws.py

PostgreSQL(`laws`, `law_articles`) 데이터를 불러와 조문 단위 문서를 만들고, OpenAI 임베딩 + **LangChain FAISS** 인덱스를 생성한다.

판례는 `make_vectorDB_precedents.py`가 별도 인덱스로 만든다.

### 전제 조건

- PostgreSQL 컨테이너 실행 중 (`docker compose -f RDB/docker-compose.yml up -d`)
- 법령 데이터 수집 완료 (`python scripts/ingest_laws.py`)
- `.env` 또는 환경 변수에 `OPENAI_API_KEY` 설정

### 실행

```bash
# 실제 인덱스 생성
python scripts/make_vectorDB_laws.py

# 통계만 확인 (임베딩/저장 생략)
python scripts/make_vectorDB_laws.py --dry-run

# 개발용 샘플 빌드
python scripts/make_vectorDB_laws.py --limit 200 --batch-size 50

# 기존 인덱스에 새 법령만 추가 (--dry-run과 같이 쓰면 추가될 조문 수만 확인)
python scripts/make_vectorDB_laws.py --append
```

`--append`는 `doc_id`(`law:{laws.id}:jo:{조문}`)가 기존 인덱스에 없는 조문만 임베딩해 붙인다. 새 법령을 `law_targets.yaml`에 추가하고 `ingest_laws.py --only`로 수집한 뒤 쓰는 용도다.

- 이미 인덱스에 있는 조문은 본문이 바뀌어도 다시 임베딩하지 않는다.
- DB에서 지운 법령·조문도 인덱스에 남는다.
- 기존 인덱스의 임베딩 모델(`manifest.json`)이 `--embedding-model`과 다르면 중단한다.

법 개정을 반영하거나 법령을 빼야 할 때는 `--append` 없이 전체 재빌드한다.

### 출력

기본 출력 경로: `vectorDB/laws_faiss/`

- `index.faiss`
- `index.pkl` (LangChain docstore)
- `documents.jsonl`
- `id_map.json`
- `manifest.json`

### 메타데이터 핵심 필드

- `law_name`: 법령명
- `law_mst`: 법령 식별자
- `article_number`: 조문 번호 (`제N조`)
- `jo_code`: 조문 코드
- `citation_label`: 인용 문자열 (`{law_name} {article_number}`)

---

## make_vectorDB_precedents.py

PostgreSQL `precedents` 테이블을 불러와 섹션별로 청킹하고, 법령과 **별도** FAISS 인덱스를 만든다.

인덱스를 나눈 이유는 한 인덱스에 섞으면 유사도 상위 결과가 법령이나 판례 한쪽으로 쏠리기 때문이다. 따로 두면 "법령 N건 + 판례 M건"처럼 몫을 고정해 검색할 수 있다.

### 전제 조건

- `python scripts/ingest_precedents.py` 실행 완료 (`precedents` 테이블에 데이터 존재)
- `.env`에 `OPENAI_API_KEY` 설정

### 청킹 규칙

| 섹션 | 컬럼 | 처리 |
|------|------|------|
| 판시사항 | `holding` | 자르지 않음 (1청크) |
| 판결요지 | `summary` | 자르지 않음 (1청크) — 하나의 법리 판단이라 중간에서 끊으면 전제나 결론만 남는다 |
| 전문 | `body` | 1,000자 / overlap 150자 |
| 참조조문·참조판례 | — | 임베딩하지 않음. 필요하면 `precedent_id`로 DB 조회 |

한글은 약 1.55자당 1토큰이라 1,000자는 약 645토큰이다. 현재 `core` 212건 → **1,301청크**.

### 실행

```bash
# 실제 인덱스 생성 (기본 label=core)
python scripts/make_vectorDB_precedents.py

# 청크 수·길이 통계만 확인
python scripts/make_vectorDB_precedents.py --dry-run

# related까지 포함, 청크 크기 조정
python scripts/make_vectorDB_precedents.py --label core --label related --chunk-size 800
```

재임베딩 비용은 전체 다시 돌려도 약 7센트(`text-embedding-3-large` 기준)라 청크 파라미터는 자유롭게 바꿔도 된다.

임베딩 모델은 법령 인덱스·판례 인덱스·챗봇(`VECTOR_DB_EMBEDDING_MODEL`)이 **모두 같아야 한다.** 하나만 바꾸면 질의 벡터 차원이 인덱스와 맞지 않아, 빌드 때가 아니라 챗봇에 질문이 들어올 때 에러가 난다.

### 출력

기본 출력 경로: `vectorDB/precedents_faiss/` (파일 구성은 법령 인덱스와 동일)

### 메타데이터 핵심 필드

- `source_type`: 항상 `precedent`
- `precedent_id`: `precedents` 테이블 PK — 청크에서 원본 판례를 되찾는 경로
- `citation_label`: 인용 문자열 (`대법원 2022다255126`)
- `case_name` / `court` / `decision_date` / `decision_type` / `source_url`
- `section`: `판시사항` / `판결요지` / `전문`
- `chunk_index`, `chunk_count`: 전문 내 위치
- `doc_id`: `prec:{precedent_id}:{holding|summary|body}:{index}`

`body` 전문·`referenced_statutes`·`label`은 길거나 바뀔 수 있어 메타데이터에 넣지 않는다. FAISS가 메타데이터를 통째로 pickle에 담기 때문에 인덱스만 커진다. 필요하면 `precedent_id`로 DB를 조회한다.
