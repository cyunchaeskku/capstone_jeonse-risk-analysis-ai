# AI 기반 전세사기 위험도 분석 및 법률 지식 지원 시스템

![system architecture diagram](img/architecture_diagram.png)

### 기술 스택

| 구분            | 기술                         | 용도                        |
| ------------- | -------------------------- | ------------------------- |
| **Frontend**  | React                      | UI 구현                    |
|               | Tailwind CSS               | 스타일                       |
| **Backend**   | FastAPI (Python)           | API 서버                    |
|               | REST API                   | 공공 데이터 연동 (law.go.kr 등)   |
| **RDB**       | PostgreSQL                 | 분석 이력 저장                  |
| **Vector DB** | FAISS                      | 법률 문서 벡터 인덱스 저장 및 유사도 검색  |
| **AI / LLM**  | GPT-5 mini (OpenAI API)    | Rule 결과 자연어 설명, RAG 답변 생성 |
|               | text-embedding-3-small     | 법률 문서 벡터 임베딩              |
| **RAG**       | LangChain                  | RAG 파이프라인 구성              |
| **문서 파싱**     | PyMuPDF                    | PDF 텍스트 추출                |
|               | Upstage Document Parse API | 고정밀 문서 파싱                 |
| **인프라**       | Docker                     | 컨테이너 관리                   |

