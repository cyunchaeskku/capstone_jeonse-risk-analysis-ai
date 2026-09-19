# RDB/

법령 데이터 저장용 PostgreSQL 설정 및 마이그레이션 관리.

## 구성

| 파일/디렉터리 | 설명 |
|---------------|------|
| `docker-compose.yml` | PostgreSQL 컨테이너 설정 (선택 사항, 아래 참고) |
| `alembic.ini` | Alembic 설정 파일 |
| `alembic/` | 마이그레이션 스크립트 |

테이블 4개: `laws`, `law_articles`, `law_relations`, `precedents`  
SQLAlchemy 모델 정의: `backend/app/models/law.py`, `backend/app/models/precedent.py`

---

## Schema

실제 PostgreSQL `\d` 출력 기준 현재 schema는 아래와 같다.

```mermaid
erDiagram
    laws ||--o{ law_articles : has
    laws ||--o{ law_relations : parent
    laws ||--o{ law_relations : child

    laws {
        int id PK
        varchar(20) mst UK
        varchar(10) law_id
        varchar(200) name
        varchar(30) category
        date promulgation_date
        date enforcement_date
        timestamptz fetched_at
        timestamptz updated_at
    }

    law_articles {
        int id PK
        int law_id FK
        varchar(10) jo_code
        varchar(20) article_number
        varchar(200) title
        text full_text
        timestamptz created_at
    }

    law_relations {
        int id PK
        int parent_law_id FK
        int child_law_id FK
        varchar(20) relation_type
    }

    precedents {
        varchar(20) precedent_id PK
        text case_name
        varchar(50) case_number
        varchar(50) court
        date decision_date
        varchar(20) decision_type
        text source_url
        varchar(20) label
        text holding
        text summary
        text referenced_statutes
        text referenced_precedents
        text body
        text raw_text
        timestamptz fetched_at
        timestamptz updated_at
    }
```

`precedents`는 `laws`와 FK로 연결되지 않는다. 판례가 인용한 법령은 `referenced_statutes`에
`"주택임대차보호법 제3조 제1항, 제3조의2 제2항"` 같은 원문 문자열로 들어있어서, 조인이 필요하면
`laws.name`과 문자열 매칭으로 푼다.

### `laws`

법령 메타데이터를 저장한다.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | `integer` | PK | 내부 PK |
| `mst` | `varchar(20)` | NOT NULL, UNIQUE | 외부 법령 식별자(수집/업서트 기준 키) |
| `law_id` | `varchar(10)` | NULL | 법제처/외부 시스템 법령 ID |
| `name` | `varchar(200)` | NOT NULL | 법령명 |
| `category` | `varchar(30)` | NULL | 법령 종류(법률/시행령/규칙 등) |
| `promulgation_date` | `date` | NULL | 공포일 |
| `enforcement_date` | `date` | NULL | 시행일 |
| `fetched_at` | `timestamptz` | NOT NULL, default `now()` | 최초 수집 시각 |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` | 마지막 갱신 시각 |

### `law_articles`

개별 법령의 조문 본문을 저장한다.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | `integer` | PK | 내부 PK |
| `law_id` | `integer` | NOT NULL, FK → `laws.id` | 소속 법령 ID |
| `jo_code` | `varchar(10)` | NULL | 조문 식별 코드(유니크 키 구성 요소) |
| `article_number` | `varchar(20)` | NULL | 표시용 조문 번호 문자열 |
| `title` | `varchar(200)` | NULL | 조문 제목/표제 |
| `full_text` | `text` | NOT NULL | 조문 본문 전문 |
| `created_at` | `timestamptz` | NOT NULL, default `now()` | 레코드 생성 시각 |

추가 제약:

| 제약명 | 내용 |
|--------|------|
| `law_articles_law_id_jo_code_key` | UNIQUE (`law_id`, `jo_code`) |

### `law_relations`

법령 간 상하위 또는 위임 관계를 저장한다.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | `integer` | PK | 내부 PK |
| `parent_law_id` | `integer` | NOT NULL, FK → `laws.id` | 상위/근거 법령 ID |
| `child_law_id` | `integer` | NOT NULL, FK → `laws.id` | 하위/종속 법령 ID |
| `relation_type` | `varchar(20)` | NULL | 관계 유형(시행령/시행규칙/위임 등) |

추가 제약:

| 제약명 | 내용 |
|--------|------|
| `law_relations_parent_law_id_child_law_id_key` | UNIQUE (`parent_law_id`, `child_law_id`) |

### `precedents`

판례 한 건이 한 행. 법령과 달리 판례는 조문 같은 고정 단위가 없는 긴 글이라 쪼개지 않고 통째로 넣는다.
임베딩용 청크는 이 테이블에 저장하지 않고 `make_vectorDB_precedents.py`가 인덱싱 시점에 만든다 —
청크 크기는 튜닝 대상이라 마이그레이션이 아니라 스크립트 재실행으로 바꾸는 게 맞고, 청크 텍스트는
`vectorDB/precedents_faiss/documents.jsonl`에 남는다. 판시사항·판결요지는 자르지 않고 각각 1청크,
전문만 1,000자/overlap 150자로 자른다 (212건 → 1,301청크).

`holding`~`body`는 법제처 API가 섹션으로 나눠 주는 값을 파싱해 넣은 것이다. 파싱 과정에서 `<br/>`은
줄바꿈으로 바꾸고 나머지 태그는 지운다. 원본은 `raw_text`에 그대로 남아 있어 언제든 다시 파싱할 수 있다.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `precedent_id` | `varchar(20)` | PK | 법제처 판례일련번호. 수집 JSONL과 FAISS 메타데이터를 잇는 키 |
| `case_name` | `text` | NOT NULL | 사건명. 최근 대법원 판례는 대괄호 안에 쟁점 요약이 붙어 길다 |
| `case_number` | `varchar(50)` | NULL | 사건번호(`2022다255126`). 인용 표기에 쓴다 |
| `court` | `varchar(50)` | NULL | 선고 법원 |
| `decision_date` | `date` | NULL | 선고일 |
| `decision_type` | `varchar(20)` | NULL | 판결/결정 등 |
| `source_url` | `text` | NULL | 법제처 원문 링크(상대 경로) |
| `label` | `varchar(20)` | NULL | 전세사기 관련성 분류 결과. 아래 설명 참고 |
| `holding` | `text` | NULL | 판시사항. 쟁점을 한 문단으로 압축한 부분 |
| `summary` | `text` | NULL | 판결요지. 법리 핵심. 없는 판례도 있다 |
| `referenced_statutes` | `text` | NULL | 참조조문. `laws` 테이블과 이어지는 유일한 연결고리 |
| `referenced_precedents` | `text` | NULL | 참조판례 |
| `body` | `text` | NULL | 전문. 분량의 약 73%를 차지한다 |
| `raw_text` | `text` | NOT NULL | `get_precedent_text` 응답 원본. 섹션 파싱이 틀렸을 때의 안전망 |
| `fetched_at` | `timestamptz` | NOT NULL, default `now()` | 최초 적재 시각 |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` | 마지막 갱신 시각 |

#### `label` 값의 의미

`scripts/classify_precedent_relevance.py`가 판례 요약을 LLM(gpt-4.1-mini)에 읽혀 매긴 값이다.
사람이 검수한 라벨이 아니라 **선별용 분류 결과**이므로, 경계선에 있는 판례는 틀릴 수 있다.

| 값 | 의미 | 예 |
|----|------|-----|
| `core` | 주택 임대차 보증금이 직접 쟁점 | 보증금 반환, 대항력·우선변제권·확정일자, 임차권등기, 전세보증금 편취 사기, 경매 배당에서 임차인의 지위 |
| `related` | 임대차가 직접 쟁점은 아니지만 전세 위험 판단에 쓰이는 법리 | 근저당권과 채권최고액, 사해행위취소, 배당순위, 조세채권 우선순위, 사기죄의 기망·고의 판단 |
| `unrelated` | 그 외 | 이 테이블에 적재하지 않는다 |

현재 적재된 것은 `core` 212건뿐이다. `related` 1,201건은 임대차 사건이 아닌 비율이 높아
(사해행위취소 317건, 근저당권 244건) 인덱싱 시 엉뚱한 법리가 근거로 잡힐 위험이 있어 보류했다.
필요하면 `python scripts/collect_precedent_texts.py --label related`로 전문을 받아 추가한다.

### 관계 요약

- `laws` 1 : N `law_articles`
- `laws` 1 : N `law_relations` (`parent_law_id`)
- `laws` 1 : N `law_relations` (`child_law_id`)
- `precedents`는 독립 테이블 (FK 없음, `referenced_statutes` 문자열로만 `laws`와 이어진다)

## 실행 방법

네이티브와 도커 중 **하나만** 쓴다. 둘 다 켜면 5432 포트가 충돌한다.  
어느 쪽이든 접속 URL은 `postgresql+psycopg://postgres:postgres@localhost:5432/jeonse_db`로 동일하다.

### 방법 A: 네이티브 (macOS, Homebrew) — 현재 기본

**로그인 시 자동 기동하지 않는다.** 백엔드나 DB를 쓰는 스크립트를 돌리기 전에 직접 켜야 한다.

```bash
brew services run postgresql@16     # 기동 (자동 기동 등록 없이)
brew services stop postgresql@16    # 중지
brew services list                  # 상태 확인
```

`start`가 아니라 `run`을 쓴다 — `brew services start`는 LaunchAgent를 등록해서 로그인 시
자동 기동이 다시 켜진다.

`postgresql@16`은 keg-only라 PATH 등록이 필요하다 (Intel Mac은 `/usr/local/opt`):

```bash
echo 'export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"' >> ~/.zshrc
```

최초 1회 롤·DB 생성 (Homebrew 기본 슈퍼유저는 macOS 계정명이라 `postgres` 롤을 따로 만든다):

```bash
createuser -s postgres
psql -d postgres -c "ALTER ROLE postgres WITH PASSWORD 'postgres';"
createdb -O postgres jeonse_db
```

### 방법 B: 도커

```bash
docker compose -f RDB/docker-compose.yml up -d
docker compose -f RDB/docker-compose.yml ps
docker compose -f RDB/docker-compose.yml down
```

## 마이그레이션

리포 루트에서 실행한다. `PYTHONPATH=.`가 필요하다 — `alembic/env.py`가 `backend.app.db`를 임포트하는데
`alembic.ini`에 `prepend_sys_path` 설정이 없다.

```bash
# 마이그레이션 적용
PYTHONPATH=. alembic -c RDB/alembic.ini upgrade head

# 현재 상태 확인
PYTHONPATH=. alembic -c RDB/alembic.ini current

# 새 마이그레이션 생성 (모델 변경 후)
PYTHONPATH=. alembic -c RDB/alembic.ini revision --autogenerate -m "설명"
```

## DB 접속 및 조회

```bash
# 네이티브
psql -U postgres -d jeonse_db

# 도커
docker exec -it jeonse_postgres psql -U postgres -d jeonse_db

# 테이블 목록
\dt

# 데이터 확인 예시
SELECT name, mst FROM laws;
SELECT COUNT(*) FROM law_articles GROUP BY law_id;
```

## 백업 / 복원

```bash
pg_dump -U postgres -d jeonse_db -Fc > jeonse_db.dump
pg_restore -U postgres -d jeonse_db --no-owner jeonse_db.dump
```

---

## 법령 데이터 수집

이 DB에 법령 데이터를 수집·적재하는 코드는 **`scripts/`** 에 있다.  
자세한 내용은 [`scripts/README.md`](../scripts/README.md) 참고.

```bash
# 전체 법령 수집
python scripts/ingest_laws.py

# 특정 법령만
python scripts/ingest_laws.py --only "부동산등기법"
```

## 판례 데이터 수집

법령과 달리 판례는 이름으로 지정할 수 없어 키워드 검색 → LLM 선별 → 원문 수집 순서를 거친다.
앞의 세 단계 산출물은 `data/*.jsonl`이고 gitignore 대상이다.

```bash
python scripts/collect_precedent_summaries.py    # 검색 + 요약  → data/precedent_summaries.jsonl
python scripts/classify_precedent_relevance.py   # 관련성 분류  → data/precedent_relevance.jsonl
python scripts/collect_precedent_texts.py        # core 전문    → data/precedent_texts.jsonl
python scripts/ingest_precedents.py              # 적재         → precedents 테이블
```

`ingest_precedents.py`는 `precedent_id` 기준 업서트라 여러 번 돌려도 중복되지 않는다.
