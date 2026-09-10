---
name: sap-tcode-to-python
description: 티코드 분석서를 입력받아 RFC만으로 동일 동작하는 pyrfc 파이썬 모듈을 생성한다
---

## What I do

`sap-tcode-analyze`가 만든 분석서(`docs/analysis/<SYSTEM>_<TCODE>.md`)를 입력받아,
RFC/BAPI 호출만으로 티코드와 동일하게 동작하는 파이썬 모듈을 만든다.

핵심 계약: 이 모듈은 다른 곳에서 MCP로 다시 쓰인다. 그래서 모듈 구조는
"티코드에서 가능한 기능들 = tool 목록, 각 기능 호출 시 받는 인자 = tool inputSchema" 형태를 따른다.
즉 분석서 2장(기능 카탈로그) → `TOOLS` 레지스트리, 분석서 3장(기능별 호출 인자) → 각 함수의 typed 인자로 1:1 매핑한다.

## When to use me

- "이 분석서로 파이썬 만들어줘", "<TCODE> 자동화 코드 짜줘" 요청 시 (분석 스킬 다음 단계)
- 분석서 없이 호출되면 코드 생성 금지 → 먼저 `sap-tcode-analyze` 실행 요구 (분석서 경로 필수)

## Inputs

1. `analysis`: 분석서 경로 (예: `docs/analysis/DEV_VA01.md`) — 필수
2. `system`: 분석서와 동일한 시스템명 (예: `DEV`) — 다르면 중단하고 확인
3. `out`: 출력 파일 (기본 `sap_tcode_<tcode_lower>.py`, 예: `sap_tcode_va01.py`)

## Preconditions (반드시 확인)

- 분석서 2장(기능 카탈로그)·3장(기능별 호출 인자)·7장(RFC-only 재현 전략)이 비어 있으면 코드 생성 금지 → 분석 보완 요청
- 분석서에 없는 FM/테이블/필드/인자 사용 금지. 필요하면 MCP `adt_read_table`/`adt_read_cds` 또는 RFC `DDIF_FIELDINFO_GET`로 먼저 실존 확인
- `sap_systems.json` 미입력 시 평문 비밀번호 하드코딩 금지

## Generation workflow

### 1. 분석서 → 매핑표 작성 (코드보다 먼저, 응답에 표시)

| 기능ID | 분석서 기능명 | Python 함수 | RFC 호출 | 인자 출처(3장) |
|---|---|---|---|---|
| F01 | 단건 조회 | `f01_...(conn, ...)` | `BAPI_...` 또는 `RFC_READ_TABLE(...)` | 필수/선택 인자 나열 |
| F02 | 생성 | `f02_...` | `BAPI_...` + COMMIT | ... |

- BAPI가 있으면 BAPI 우선, 없으면 `RFC_READ_TABLE` + `rfc_read_full` 페이징
- 다이얼로그 전용(`CALL SCREEN` 중단 로직)은 "미지원"으로 명시하고 `NotImplementedError` + 사유 기재

### 2. 코드 템플릿 (강제 구조 — MCP 재사용 계약)

```python
"""<TCODE> (<TTEXT>) RFC-only 재현. 분석서: docs/analysis/<SYS>_<TCODE>.md
외부 MCP 래핑용: TOOLS[i] = {"id": <기능ID>, "name": <tool명>,
  "description": ..., "input_schema": {...}} 와 동명 함수를 import해 쓰세요.
"""
from sap_monthly_report import get_connection_by_name, rfc_read_table, rfc_read_full, table_fields

SYSTEM = "DEV"  # find_system key (분석서 시스템과 동일)
TCODE = "VA01"

# --- F01: <분석서 2장의 기능명> (원천: ...) ---
def f01_<slug>(conn, *, <3장의 필수/선택 인자 그대로 typed kwargs>) -> dict:
    """<기능 설명>. Args: <3장 인자표 복기>. Returns: {"rows"/"result": ..., "raw": ...}"""
    ...

# --- F02 ... (기능 수만큼 반복) ---

# MCP 재사용 계약: 기능ID → 함수 매핑 (분석서 2장 순서 유지)
TOOLS = [
    {"id": "F01", "name": "f01_<slug>", "description": "<기능명 + RFC 재현 방식>",
     "input_schema": {"type": "object",
        "properties": {"<인자명>": {"type": "string", "description": "<ABAP타입/길이/예시>"}},
        "required": [<필수 인자>]},
     "func": "f01_<slug>"},
]

def get_tool_defs():
    """외부 MCP 서버용: TOOLS에서 func 객체를 제외한 JSON 직렬화 가능 정의 반환."""
    return [{k: v for k, v in t.items() if k != "func"} for t in TOOLS]

def call_tool(name_or_id, conn_or_system=SYSTEM, **kwargs):
    """외부 MCP 핸들러용 단일 진입점: tool명/F01 → 함수 디스패치."""
    conn = conn_or_system if hasattr(conn_or_system, "call") else get_connection_by_name(conn_or_system)
    try:
        for t in TOOLS:
            if name_or_id in (t["id"], t["name"]):
                return globals()[t["func"]](conn, **kwargs)
        raise KeyError(f"unknown tool: {name_or_id}, available: {[t['id'] for t in TOOLS]}")
    finally:
        if not hasattr(conn_or_system, "call"):
            try: conn.close()
            except Exception: pass

if __name__ == "__main__":
    import sys, json
    # python sap_tcode_va01.py DEV F01 --params '{"<인자>": "..."}'
    ...
```

필수 규칙:
- 함수명·인자명은 분석서 2·3장과 1:1 대응 (임의 개명 금지, slug만 snake_case 변환)
- 인자 타입: ABAP DATS(YYYYMMDD)/DEC/CHAR는 str 그대로 + 주석에 형식·길이·예시 명시
- 커넥션: `get_connection_by_name(SYSTEM)`만 사용 (직접 `Connection(...)` 금지, 잠김 방지 상태기록 재사용)
- `RFC_READ_TABLE`는 `rfc_read_table`/`rfc_read_full` 래퍼 사용 (OPTIONS 72자 분할은 래퍼가 처리)
- 쓰기 BAPI 뒤에는 `BAPI_TRANSACTION_COMMIT(WAIT="X")`, 실패 시 `BAPI_TRANSACTION_ROLLBACK`
- `RETURN` 테이블(BAPIRET2) 전건 검사 → 에러면 예외 + 원문 메시지 포함
- SELECT 필드는 분석서 4장의 핵심 필드만 (SELECT * 금지)

### 3. 외부 MCP 래핑 예시 (산출물 주석 또는 응답에 포함)

```python
# 다른 MCP 서버에서 재사용 시 (예: FastMCP)
# from sap_tcode_va01 import TOOLS, call_tool
# for t in TOOLS: mcp.add_tool(globals()[t["func"]], name=t["name"], description=t["description"])
```

### 4. 검증 (코드 작성 후 반드시 수행)

1. `python -m py_compile <out>` 문법 체크
2. 사용한 전 테이블/필드 실존 확인 (`table_fields` 또는 MCP `adt_read_table`)
3. FM 존재 확인: `RFC_READ_TABLE(conn, "TFDIR", ["FUNCNAME"], where="FUNCNAME = '<FM>'")`
4. 읽기 함수 1건 스모크 테스트 (`ROWCOUNT=5`). 쓰기는 기본 dry-run, 실제 기표는 `--commit` 플래그 때만
5. `get_tool_defs()` JSON 직렬화 가능 확인 + `call_tool` 디스패치 1건 테스트
6. 실패 항목은 코드에 `NotImplementedError("다이얼로그 전용: ...")` + 분석서 9장(미확인)에 추가

## Output

- `<out>.py` 파일 1개 (TOOLS + get_tool_defs + call_tool 포함) + 사용법 (`python <out>.py <SYSTEM> <F01|함수명> --params '{...}'`)
- 응답 마지막에: 기능ID→함수→인자 대응표 / 구현 범위 / 미지원 항목 / 필요 권한(`S_TABU_NAM`, `S_RFC`, `AUTHORITY-CHECK` 대상) / 테스트 결과

## Rules (엄수)

- GUI 자동화(SAP GUI Scripting, 화면 좌표 클릭) 절대 금지 — RFC/BAPI only
- 추측 FM/BAPI/인자 생성 금지. 분석서 근거 없는 호출 금지
- 비밀번호 평문 포함 금지 (`sap_systems.json` + `${ENV}` 사용)
- 비밀번호 오류 반복 재시도 금지 (`get_connection_by_name`의 auth_failed 차단 존중)
- 200줄 초과 시 함수별 분할 + `sap_monthly_report` 재사용으로 중복 제거
