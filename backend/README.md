# Backend

FastAPI 기반의 최소 백엔드가 `backend/app` 아래에 구현되어 있다.

## Run

```bash
export OPENAI_API_KEY=your_api_key
export OPENAI_MODEL=gpt-4.1-mini
uvicorn backend.app.main:app --reload
```

기본 엔드포인트:

- `GET /`
- `GET /health`
- `POST /analyses`
- `GET /analyses/{analysis_id}`
- `POST /qa`

## Notes

- 현재 구현은 초기 연결용 데모로, 결과 저장은 메모리 기반이다.
- 위험도 평가는 매우 단순한 규칙 예시만 포함한다.
- 법률 QA는 LangChain + OpenAI 기반의 비-RAG 챗봇으로 동작한다.
- 프론트 개발 서버 연동을 위해 기본 CORS가 `localhost:5173`에 열려 있다.
