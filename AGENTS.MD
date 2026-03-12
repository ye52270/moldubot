# AGENTS.md

> 작업 시작 전 이 파일을 반드시 읽어라.
> 모든 규칙은 예외 없이 적용된다.
> 모든 코드는 500 line을 넘으면 경보가 발생하고, 리펙터링을 해야함.(MD파일은 예외)
> TDD 방식(Test 주도 방식) 개발 필요. 항상 test code를 같이 만들어야 함.
> print가 아닌 logging으로 관리. (공통 logging)
---

## 0. Product 목표 및 아키텍처 규칙 (AI Hub 공통 원칙)

### Product 목표
- 몰두봇은 메일 전용 봇이 아니라 **AI Hub**로 동작해야 한다.
- 질의가 메일/비메일/혼합 어디로 오더라도 **공통 파이프라인**으로 유연하게 처리해야 한다.
- 응답 형식보다 **사실성(검증 가능성), 근거, 실행 가능성**을 우선한다.
- 기능 확장 시 기존 기능 안정성을 해치지 않아야 하며, **side effect 최소화**를 기본 원칙으로 한다.
- 사용자 경험은 **두 가지 입력 의도**로 단순하게 유지한다:
  - 일반 채팅 입력(자유 질문/후속 질문 포함) → **freeform 응답**
  - `/` 명시 스킬 입력(예: `/메일요약`, `/코드분석`) → **구조화/포맷 응답**

### 아키텍처 규칙
- 도메인별 `if`/키워드 예외를 무한히 누적하지 마라. 공통 스키마/분류/정책으로 일반화하라.
- `"이번만"`, `"이 경우만"` 식의 단건 예외 패치를 금지한다. 동일 유형 질의에 재사용 가능한 일반 규칙(정책/계약/스키마)으로만 반영하라.
- 기본 라우팅은 **2모드 우선**으로 결정한다.
  - `freeform`: 일반 채팅. LLM 자연어 응답을 우선 보존하고, 후처리는 최소 정규화만 수행한다.
  - `skill`: `/` 명령. 구조화 계약(JSON/템플릿/섹션 렌더)을 허용하고 deterministic 정책을 적용한다.
- `freeform` 모드에서 정책/후처리는 의미 재작성 금지, 요약 불릿 강제 금지, 템플릿 강제 금지.
- `skill` 모드에서만 형식 계약(요약 템플릿/코드리뷰 포맷/테이블 등)을 강제한다.
- 후속 질문 컨텍스트는 thread memory + 선택 메일 컨텍스트를 우선 활용하며, 명시적 전역 탐색 의도가 없으면 불필요한 범위 전환을 하지 않는다.
- 의도 파서는 라우팅 힌트이며 단일 진실 소스가 아니다. 파서 실패/저신뢰 상황에서도 대화 맥락으로 안전하게 폴백해야 한다.
- 툴(Web/문서) 호출은 하드코딩 예외가 아니라 정책으로 판단한다.
  - 예: 최신성 필요, 사용자의 검증 요청, low-confidence, 외부 레퍼런스 명시 요청.
- 후처리는 의미를 재작성하지 말고, 중복 제거/노이즈 제거/표현 정규화 중심으로 제한한다.
- 현재메일은 기본 컨텍스트일 뿐 강제 컨텍스트가 아니다. 사용자 명시(메일 무관/일반 질문 등)가 있으면 즉시 전역 모드로 전환한다.
- 라우팅/후처리 변경 시 테스트는 **행동 계약(입력→출력)** 중심으로 작성하고 회귀 테스트를 반드시 통과시킨다.

### 임시 예외(2026-03-12)
- 이번 작업 범위에 한해, **외부검색(web search) 트리거는 명시 토큰 기반 정책**으로 운용한다.
- 적용 범위: `search/chat` 계열의 웹 출처 검증/조회 트리거 판단 로직.
- 원칙: 사용자 발화에 외부근거 요청 의도가 명시된 경우에만 web tool calling을 허용한다.

### 금지사항
- 특정 질의 1건 해결을 위한 하드코딩 예외를 공통 경로에 직접 주입하는 행위.
- 특정 버그/문의 1건을 통과시키기 위해 임시 분기(`if query == ...`, 단일 키워드 매칭 등)를 추가하는 행위.
- 근거 불충분 내용을 단정형 문장으로 확정해서 출력하는 행위.
- 템플릿을 맞추기 위해 의미를 왜곡하는 후처리 로직 추가.
- 일반 채팅(`freeform`) 응답에 구조화 템플릿/불릿/JSON을 강제로 덮어쓰는 행위.
- `/` 명령이 아닌 일반 질문에 스킬 전용 포맷 계약을 강제하는 행위.
- 테스트 없이 라우팅/정책/후처리 규칙 변경.

### 질문/출력 운영 원칙 (전 질문 공통)
- 입력 해석 1순위: 사용자의 마지막 발화 + thread memory + 선택 메일 컨텍스트.
- 입력 해석 2순위: 의도 파서 결과(저신뢰/실패 시 맹신 금지).
- `freeform` 출력 원칙:
  - 자연스러운 문장 단락 중심으로 답변한다.
  - 사용자가 요청하지 않은 번호 목록/섹션/템플릿을 강제하지 않는다.
  - JSON 원문 노출은 금지한다(사용자가 JSON을 명시 요청한 경우 제외).
- `skill` 출력 원칙:
  - 스킬 계약에 정의된 포맷/섹션/필드를 엄격히 준수한다.
  - 계약 파싱 실패 시에도 스킬 목적에 맞는 안전한 대체 포맷으로 복구한다.
- 범위 해석 원칙:
  - 선택 메일이 있고 명시적 전역 의도가 없으면 current-mail 문맥을 우선한다.
  - `전체/검색/관련 메일` 등 전역 탐색 신호가 명시되면 global scope를 우선한다.

## 1. 작업 시작 전 필수 절차

세션 시작 시 아래를 먼저 확인한다.
- `AGENTS.MD` 최신 규칙 재확인(특히 예외성 패치 금지/일반화 우선).
- 이번 변경이 단건 예외인지 점검하고, 반드시 공통 정책/계약으로 설계할 것.
- 이번 변경이 `freeform`/`skill` 어느 모드에 속하는지 먼저 결정하고, 해당 모드의 책임 범위 안에서만 수정할 것.
- 키워드/문구 추가로 해결하려는 변경인지 점검하고, 가능하면 공통 라우팅 정책과 컨텍스트 해석 로직으로 해결할 것.

작업을 시작하기 전, **반드시 프로젝트 루트의 `task.md`를 열어** 아래 항목을 업데이트하라.

```markdown
## Plan
- [ ] 무엇을 할 것인지 단계별로 작성

## Action Log
- [시작 시각] 작업 시작: [작업 내용 요약]
- [완료 시각] 완료: [결과 요약]
- [발생 시각] 이슈: [문제 내용 및 해결 방법]
```

작업 완료 후에도 `task.md`의 Action Log를 반드시 업데이트하라.
**`task.md` 업데이트 없이 코드 수정을 시작하지 마라.**

---

## 2. Python 설계 원칙

### 함수
- 함수 하나는 **한 가지 일만** 한다. (단일 책임 원칙)
- 함수 길이는 **30줄 이내**를 목표로 한다. 초과 시 분리를 검토하라.
- 모든 함수에 **docstring을 필수로 작성**한다.

```python
# ✅ 올바른 예
def parse_email_date(raw_date: str) -> datetime:
    """
    이메일 헤더의 날짜 문자열을 datetime 객체로 변환한다.

    Args:
        raw_date: RFC 2822 형식의 날짜 문자열 (예: "Mon, 01 Jan 2026 09:00:00 +0900")

    Returns:
        변환된 datetime 객체 (timezone 포함)

    Raises:
        ValueError: 날짜 형식이 올바르지 않을 경우
    """
    ...


# ❌ 금지 - docstring 없음
def parse_email_date(raw_date: str) -> datetime:
    ...
```

### 타입 힌트
- 모든 함수의 인자와 반환값에 **타입 힌트를 필수로 작성**한다.
- `Any` 타입은 불가피한 경우에만 사용하고, 사용 시 주석으로 이유를 명시한다.

```python
# ✅ 올바른 예
def get_user(user_id: str) -> dict[str, str]:
    ...

# ❌ 금지
def get_user(user_id):
    ...
```

### 클래스
- 클래스에도 **docstring을 필수로 작성**한다.
- 클래스는 응집도가 높아야 한다. 관련 없는 메서드를 한 클래스에 몰지 마라.

```python
# ✅ 올바른 예
class EmailParser:
    """
    Microsoft Graph API 응답에서 이메일 데이터를 파싱하는 클래스.

    Attributes:
        timezone: 날짜 변환에 사용할 타임존 (기본값: Asia/Seoul)
    """
    ...
```

---

## 3. 하지 말아야 할 코드 규칙

### 중복 코드 금지
- **같은 로직이 2곳 이상에 있으면** 반드시 공통 함수/모듈로 추출하라.
- 복사-붙여넣기로 만든 코드를 작성하지 마라.
- 비슷한 함수가 이미 있다면, 새로 만들기 전에 **기존 코드를 먼저 검색**하라.

```python
# ❌ 금지 - 중복 로직
def format_email_date(date):
    return date.strftime("%Y-%m-%d")

def format_calendar_date(date):
    return date.strftime("%Y-%m-%d")  # 동일한 로직 중복

# ✅ 올바른 예 - 공통 함수로 추출
def format_date(date: datetime) -> str:
    """날짜를 YYYY-MM-DD 형식의 문자열로 변환한다."""
    return date.strftime("%Y-%m-%d")
```

### 불필요한 코드 생성 금지
- 요청하지 않은 기능을 **임의로 추가하지 마라.**
- 당장 사용하지 않는 함수, 클래스, 변수를 **미리 만들어 두지 마라.** (YAGNI 원칙)
- TODO 주석으로 미래 기능을 암시하는 뼈대만 만들어 두지 마라.

```python
# ❌ 금지 - 요청하지 않은 기능 선제 추가
class EmailService:
    def send_email(self): ...       # 요청한 기능
    def schedule_email(self): ...  # 요청 안 했음 - 금지
    def recall_email(self): ...    # 요청 안 했음 - 금지

# ❌ 금지 - 사용하지 않는 뼈대
def future_feature():
    # TODO: 나중에 구현
    pass
```

### print() 금지
- 디버깅 목적 포함 **`print()` 사용을 전면 금지**한다.
- 반드시 `logging` 모듈을 사용하라.

```python
# ✅ 올바른 예
import logging
logger = logging.getLogger(__name__)
logger.info("이메일 파싱 완료: %s건", count)
logger.error("Graph API 호출 실패: %s", error)

# ❌ 금지
print("이메일 파싱 완료:", count)
```

### 매직 넘버/문자열 금지
- 의미를 알 수 없는 숫자나 문자열을 **코드에 직접 쓰지 마라.**
- 상수로 정의하고 이름을 붙여라.

```python
# ❌ 금지
if len(results) > 50:
    ...

# ✅ 올바른 예
MAX_SEARCH_RESULTS = 50
if len(results) > MAX_SEARCH_RESULTS:
    ...
```

### 광범위한 예외 처리 금지
- `except Exception` 또는 `except:` 단독으로 모든 예외를 잡지 마라.
- 예외를 잡으면 **반드시 로그를 남기고** 적절히 처리하라.

```python
# ❌ 금지
try:
    result = call_api()
except:
    pass

# ✅ 올바른 예
try:
    result = call_api()
except GraphAPIError as e:
    logger.error("Graph API 호출 실패: %s", e)
    raise
```

---

## 4. 파일 및 모듈 구조 규칙

- 파일 하나는 **하나의 역할**만 담당한다.
- 파일당 **500줄 초과 시 분리**를 검토하라.
- 모듈 간 **순환 참조(circular import)를 만들지 마라.**
- 새 파일을 만들기 전에 **기존 파일에 넣을 수 없는지 먼저 검토**하라.

---

## 5. 커밋 메시지 규칙

```
feat:     새 기능 추가
fix:      버그 수정
refactor: 기능 변경 없는 코드 개선
docs:     문서 수정
test:     테스트 추가/수정
chore:    설정, 패키지 등 기타 변경

예시:
feat(email): 첨부파일 목록 조회 함수 추가
fix(parser): 날짜 파싱 시 timezone 누락 버그 수정
refactor(utils): 중복 날짜 포맷 함수 공통 모듈로 통합
```

---

## 6. task.md 형식 참고

프로젝트 루트의 `task.md`는 아래 형식을 유지한다.

```markdown
# Task

## 현재 작업
[작업 제목]

## Plan
- [ ] 1단계: ...
- [ ] 2단계: ...
- [ ] 3단계: ...

## Action Log
- [HH:MM] 작업 시작: ...
- [HH:MM] 완료: ...
- [HH:MM] 이슈 발생: ... → 해결 방법: ...

## 완료된 작업
- [날짜] ...
```

## 7. 스캔 및 읽기 금지 파일/디렉터리

아래 파일과 디렉터리는 **절대 읽거나 분석하지 마라.**
이진 파일이거나 자동 생성된 캐시로, 소스 코드가 아니다.

### 금지 디렉터리
- `**/chroma_db/` — ChromaDB 벡터 저장소 (바이너리)
- `**/.chromadb/` — ChromaDB 내부 메타데이터
- `**/__pycache__/` — Python 바이트코드 캐시
- `**/.cache/` — 일반 캐시 디렉터리
- `**/logs/` — 로그 파일 디렉터리
- `**/tmp/`, `**/temp/` — 임시 파일

### 금지 파일 패턴
- `**/*.db`, `**/*.sqlite`, `**/*.sqlite3` — 데이터베이스 파일
- `**/*.pyc`, `**/*.pyo`, `**/*.pyd` — 컴파일된 Python 파일
- `**/*.bin`, `**/*.parquet` — 바이너리 데이터 파일
- `**/.env`, `**/.env.*` — 환경변수 파일 (보안)

### 이유
이 파일들을 스캔하면 토큰을 낭비하고, 바이너리 파싱 오류가 발생하며,
민감한 데이터가 노출될 수 있다. 소스 코드 분석과 무관하다.

---

## 8. Codex 스킬 운용 규칙

> Codex가 코드를 작성/수정/리팩터링할 때 아래 스킬을 자동으로 적용해야 한다.
> `$` 명시 없이 요청하더라도, 작업 유형에 해당하는 스킬을 반드시 참조하라.

### 8-1. 작업 유형별 필수 스킬

| 작업 유형 | 참조 스킬 | 적용 조건 |
|---|---|---|
| 신규 기능 설계 / 프레임워크 선택 | `Framework Selection` | 새 모듈/기능 추가 시 항상 |
| SubAgent 구조 변경 / 오케스트레이션 | `Deep Agents Orchestration` | SubAgent 신규/수정/삭제 시 |
| LangChain 기본 패턴 (create_agent, tool) | `Langchain Fundamentals` | LangChain 관련 코드 작성 시 |
| LangGraph StateGraph 변경 | `Langgraph Fundamentals` | StateGraph 노드/엣지 변경 시 |
| Human-in-the-Loop / 승인 흐름 | `Langgraph Human In The Loop` | HITL 패턴 구현 시 |
| 상태 영속성 / 대화 기억 | `Langgraph Persistence` | 세션 상태 저장/복구 구현 시 |
| RAG / 벡터 검색 / ChromaDB | `Langchain Rag` | ChromaDB 쿼리/인덱싱 작업 시 |
| 미들웨어 / 커스텀 훅 | `Langchain Middleware` | 미들웨어 추가/변경 시 |
| 패키지 의존성 추가 | `Langchain Dependencies` | requirements.txt 변경 시 |
| 보안 검토 | `security-best-practices` | 외부 API 호출, 인증 코드 작성 시 |
| 코드 문서화 | `doc` | 새 모듈/클래스 문서화 시 |
| OpenAI API 패턴 | `openai-docs` | GPT-4o API 호출 코드 작성 시 |

### 8-2. 스킬 자동 적용 원칙

- Codex는 사용자가 `$스킬명`을 명시하지 않아도 위 표의 조건에 해당하면 해당 스킬을 **자동으로 로드**하여 최신 패턴을 적용한다.
- 코드 작성 전 관련 스킬이 있는지 위 표를 먼저 확인한다.
- **복수 조건**에 해당하는 경우 관련 스킬을 모두 참조한다.
  - 예: SubAgent 안에 LangGraph StateGraph가 있는 경우 → `Deep Agents Orchestration` + `Langgraph Fundamentals` 동시 참조.

### 8-3. 스킬 기반 코드 리뷰 의무

- 코드 수정 완료 후, 변경된 영역과 관련된 스킬 기준으로 자체 검토를 수행한다.
- 스킬 패턴과 다른 방식으로 구현한 경우 반드시 그 이유를 주석 또는 task.md에 명시한다.
- 다음 항목은 스킬 검토 없이 변경할 수 없다:
  - SubAgent 역할 분리 구조 (Worker / Critic / Reviser / Finalizer)
  - LangGraph StateGraph 노드/엣지 정의
  - ChromaDB 벡터 검색 인터페이스
  - FastAPI 라우터 구조

### 8-4. MolduBot 전용 스킬 (`moldubot-conventions`)

프로젝트 루트 `.codex/skills/moldubot-conventions/SKILL.md` 또는
`~/.codex/skills/moldubot-conventions/SKILL.md` 에 MolduBot 전용 규칙이 정의되어 있다.
해당 스킬이 존재하면 **모든 작업에 우선 적용**한다.

> 스킬이 없으면 이 AGENTS.md의 섹션 0~7 규칙을 기본값으로 사용한다.
