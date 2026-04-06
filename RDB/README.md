# RDB/

법령 데이터 저장용 PostgreSQL 설정 및 마이그레이션 관리.

## 구성

| 파일/디렉터리 | 설명 |
|---------------|------|
| `docker-compose.yml` | PostgreSQL 컨테이너 설정 |
| `alembic.ini` | Alembic 설정 파일 |
| `alembic/` | 마이그레이션 스크립트 |

테이블 3개: `laws`, `law_articles`, `law_relations`  
SQLAlchemy 모델 정의: `backend/app/models/law.py`

---

## Docker 실행

```bash
# 컨테이너 시작
docker compose -f RDB/docker-compose.yml up -d

# 컨테이너 상태 확인
docker compose -f RDB/docker-compose.yml ps

# 컨테이너 중지
docker compose -f RDB/docker-compose.yml down
```

## 마이그레이션

```bash
# 마이그레이션 적용
alembic -c RDB/alembic.ini upgrade head

# 현재 상태 확인
alembic -c RDB/alembic.ini current

# 새 마이그레이션 생성 (모델 변경 후)
alembic -c RDB/alembic.ini revision --autogenerate -m "설명"
```

## DB 접속 및 조회

```bash
# psql 접속
docker exec -it jeonse_postgres psql -U postgres -d jeonse_db

# 테이블 목록
\dt

# 데이터 확인 예시
SELECT name, mst FROM laws;
SELECT COUNT(*) FROM law_articles GROUP BY law_id;
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
