# scripts/

법령 데이터 수집 관련 스크립트 모음.

## 파일 구조

| 파일 | 설명 |
|------|------|
| `ingest_laws.py` | 법령 데이터 수집 메인 스크립트 |
| `make_vectorDB.py` | RDB 법령/조문 데이터를 FAISS 벡터DB로 변환 |
| `law_targets.yaml` | 수집 대상 법령 목록 (설정 파일) |

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
   - `korean-law get_law_text --mst <mst>` → 목차에서 조문 번호 목록 추출
   - `korean-law get_batch_articles --mst <mst> --articles '[...]'` → 조문 본문 일괄 조회 (50개 단위 청크)
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

## make_vectorDB.py

PostgreSQL(`laws`, `law_articles`) 데이터를 불러와 조문 단위 문서를 만들고, OpenAI 임베딩 + **LangChain FAISS** 인덱스를 생성한다.

### 전제 조건

- PostgreSQL 컨테이너 실행 중 (`docker compose -f RDB/docker-compose.yml up -d`)
- 법령 데이터 수집 완료 (`python scripts/ingest_laws.py`)
- `.env` 또는 환경 변수에 `OPENAI_API_KEY` 설정

### 실행

```bash
# 실제 인덱스 생성
python scripts/make_vectorDB.py

# 통계만 확인 (임베딩/저장 생략)
python scripts/make_vectorDB.py --dry-run

# 개발용 샘플 빌드
python scripts/make_vectorDB.py --limit 200 --batch-size 50
```

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
