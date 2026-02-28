# AGENTS.md

> 작업 시작 전 이 파일을 반드시 읽어라.
> 모든 규칙은 예외 없이 적용된다.
> 모든 코드는 500 line을 넘으면 경보가 발생하고, 리펙터링을 해야함.예외없음
> LLM과의 모든 입출력은 JSON포맷을 사용한다
> TDD 방식(Test 주도 방식) 개발 필요. 항상 test code를 같이 만들어야 함.
> print가 아닌 logging으로 관리. (공통 logging)
---

## 1. 작업 시작 전 필수 절차

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
- 복사-붙여넣기로 만든 코드는 작성하지 마라.
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