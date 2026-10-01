---
name: sap-bc-usage
description: 배포된 sap_tcode_*.py 공용 사용법. tcode별 기능 목록과 CLI/MCP 호출법을 안내한다
---

## What I do

이 레포에 배포된 `sap_tcode_*.py` 11종(32 tools)의 공용 사용법 스킬이다.
"어떤 기능이 있고 기능별로 어떻게 쓰는지"를 한 곳에서 답한다.
기능별 상세 스펙의 원천은 `registry.json`(자동 생성)과 각 모듈의 `TOOLS`이며,
본 문서는 사람이 읽는 요약 + 호출 패턴만 담는다.

- 기능 목록 원천: `.opencode/skills/sap-bc-usage/registry.json`
  (갱신: `python tools/build_registry.py`)
- 분석서 원천: `docs/analysis/<SYS>_<TCODE>.md`

## When to use me

- "SU01로 사용자 만들어줘", "SM37 잡 목록 보여줘" 등 현업 사용 요청 시
- "뭐뭐 쓸 수 있어?", "F07b 어떻게 호출해?" 등 기능·인자 문의 시
- 새 PC/다른 시스템에서 재사용법을 물을 때
- 새 `sap_tcode_*.py` 추가 후 사용법 등록 시 (아래 Registration 참조)

## Prerequisites (공통 1회만)

1. `Copy-Item sap_systems.example.json sap_systems.json` 후 ashost/sysnr/client/user 입력.
   비밀번호는 평문 금지, 환경변수 참조만: `"passwd": "${SAP_PW_A4H}"` + `$env:SAP_PW_A4H='...'`
2. 시스템 결정 3순위: 명시 인자(system/conn) > `$SAP_SYSTEM`/`$SAP_DEFAULT_SYSTEM` > 모듈 `SYSTEM` 상수(현재 전부 `A4H`).
3. 쓰기는 기본 dry-run. `commit=True`(SU01/SU10) 또는 `execute=True`(SM37 F03) 명시 시에만 실제 반영.

## Common call patterns (전 모듈 동일)

```powershell
# CLI: python <모듈> <SYSTEM> <F01|함수명> --params '{...}'
python sap_tcode_su01.py A4H F01 --params '{"username": "DEVELOPER"}'
python sap_tcode_sm37.py A4H F01 --params '{"max_rows": 10}'
python sap_tcode_se16n.py A4H F01 --params '{"table": "TSTC", "rowcount": 5}'
```

```python
# MCP/파이썬 재사용 (전 모듈 동일 계약: TOOLS + get_tool_defs + call_tool)
from sap_tcode_su01 import TOOLS, call_tool
call_tool("F01", "A4H", username="DEVELOPER")          # id 또는 name 모두 가능
call_tool("f01_get_detail", "A4H", username="DEVELOPER")
from sap_tcode_su01 import get_tool_defs
get_tool_defs()  # JSON 직렬화 가능 정의 (func 제외)
```

```python
# FastMCP 래핑 예시
import sap_tcode_su01 as m
for t in m.TOOLS:
    mcp.add_tool(getattr(m, t["func"]), name=t["name"], description=t["description"])
```

## Module catalog (11 modules, 32 tools)

| TCODE | 모듈 | 기능 수 | 한줄 요약 |
|---|---|---|---|
| SU01 | `sap_tcode_su01.py` | 11 (F01~F06, F07a~d, F08 미지원) | 사용자 단건/생성/변경/삭제/목록/존재/롤·프로파일 할당·삭제 |
| SU10 | `sap_tcode_su10.py` | 3 | SU01 BAPI 대량 반복 (생성/변경/삭제, 결과 ok/failed 분리) |
| SE16N | `sap_tcode_se16n.py` | 2 | 임의 테이블 조회 + 구조 조회 |
| ST22 | `sap_tcode_st22.py` | 2 (F01 제한) | 덤프 목록(SNAP, trial 제한) + 덤프 상세 |
| SM12 | `sap_tcode_sm12.py` | 1 | 락 목록 (ENQUEUE_READ) |
| SM21 | `sap_tcode_sm21.py` | 1 | 시스템 로그 조회 |
| SM37 | `sap_tcode_sm37.py` | 3 | 잡 목록/상세 + 중단(execute 명시) |
| SM50 | `sap_tcode_sm50.py` | 1 | 워크 프로세스 목록 (TH_WPINFO) |
| SLG1 | `sap_tcode_slg1.py` | 2 (F02 제한) | 로그 헤더 검색 + 메시지 조회(클러스터 제한) |
| SM59 | `sap_tcode_sm59.py` | 3 | RFC 목적지 목록/상세 + ping |
| DB02 | `sap_tcode_db02.py` | 3 (F03 미지원) | HANA 용량 스냅샷/히스토리 |

## Function usage (기능별 호출법)

### SU01 — `sap_tcode_su01.py`

| ID | 함수 | 필수 인자 | 호출 예 |
|---|---|---|---|
| F01 | `f01_get_detail` | username | `'{"username": "DEVELOPER"}'` |
| F02 | `f02_create` | username (+logondata/password/defaults/address/company 선택, commit) | `'{"username": "PYTEST01", "password": {"BAPIPWD": "Test2026!a"}, "commit": true}'` |
| F03 | `f03_change` | username (+변경 구조체·`*_X` 플래그, commit) | `'{"username": "PYTEST01", "commit": true, "LOGONDATA": {...}}'` |
| F04 | `f04_delete` | username (+commit) | `'{"username": "PYTEST01", "commit": true}'` — commit 없이 호출하면 ROLLBACK이라 삭제 안 됨 |
| F05 | `f05_getlist` | 없음 (selection_range/max_rows 선택) | `'{"max_rows": 20}'` |
| F06 | `f06_existence_check` | username | `'{"username": "DEVELOPER"}'` → `{"exists": true/false}` (없으면 RETURN I124) |
| F07a | `f07_actgroups_assign` | username, activitygroups | `'{"username": "U1", "activitygroups": [{"AGR_NAME": "SAP_ALL"}], "commit": true}'` |
| F07b | `f07_actgroups_delete` | username, activitygroups | 위와 동일 (DELETE BAPI). 미보유 롤이면 BAPI E 리턴 → 예외 |
| F07c | `f07_profiles_assign` | username, profiles | `'{"username": "U1", "profiles": [{"PROFILE": "SAP_ALL"}], "commit": true}'` |
| F07d | `f07_profiles_delete` | username, profiles | 위와 동일 (DELETE BAPI) |
| F08 | `f08_direct_entry` | — | 미지원 (`NotImplementedError`, dynpro 전용). F01~F07로 우회 |

### SU10 — `sap_tcode_su10.py` (대량, SU01 재사용)

| ID | 함수 | 필수 인자 | 호출 예 |
|---|---|---|---|
| F01 | `f01_mass_create` | users[] | `'{"users": ["U1", "U2"], "commit": true}'` |
| F02 | `f02_mass_change` | users[] | `'{"users": ["U1", "U2"], "commit": true}'` + 변경 키워드 |
| F03 | `f03_mass_delete` | users[] | `'{"users": ["U1", "U2"], "commit": true}'` |

반환은 `{"ok": [...], "failed": [{user, error}], "ok_count": n, "fail_count": m}`.

### SE16N — `sap_tcode_se16n.py`

| ID | 함수 | 필수 인자 | 호출 예 |
|---|---|---|---|
| F01 | `f01_display_table` | table (+fields/where/rowcount/rowskips) | `'{"table": "TSTC", "fields": ["TCODE", "PGMNA"], "where": "TCODE = ''SU01''", "rowcount": 5}'` |
| F02 | `f02_describe_table` | table | `'{"table": "USR02"}'` → FIELDNAME/DATATYPE/LENG/KEYFLAG |

### ST22 — `sap_tcode_st22.py`

| ID | 함수 | 필수 인자 | 비고 |
|---|---|---|---|
| F01 | `f01_list_dumps` | 없음 (date_from/max_rows) | SNAP이 RFC_READ_TABLE 불가(DA131) → trial에서 에러 가능. 키를 알면 F02 직접 |
| F02 | `f02_dump_detail` | datum(YYYYMMDD), uzeit(HHMMSS) | `'{"datum": "20260909", "uzeit": "120000", "uname": "DEVELOPER"}'` |

### SM12 / SM21 / SM50 — 단일 조회

```powershell
python sap_tcode_sm12.py A4H F01 --params '{}'                          # 전체 락
python sap_tcode_sm12.py A4H F01 --params '{"username": "DEVELOPER"}'    # GUNAME 필터
python sap_tcode_sm21.py A4H F01 --params '{"max_lines": 20}'           # 최신 로그 20행
python sap_tcode_sm50.py A4H F01 --params '{}'                          # WP 목록
python sap_tcode_sm50.py A4H F01 --params '{"with_cpu": "X"}'           # CPU 포함
```

### SM37 — `sap_tcode_sm37.py`

| ID | 함수 | 필수 인자 | 호출 예 |
|---|---|---|---|
| F01 | `f01_select_jobs` | 없음 (jobname prefix/max_rows) | `'{"jobname": "Z", "max_rows": 10}'` |
| F02 | `f02_job_detail` | jobname, jobcount | `'{"jobname": "ZBATCH", "jobcount": "12345678"}'` |
| F03 | `f03_abort_job` | jobname, jobcount (+execute) | 기본 dry-run(`aborted: false`). 실제 중단만 `'{"jobname": "...", "jobcount": "...", "execute": true}'` |

### SLG1 — `sap_tcode_slg1.py`

```powershell
python sap_tcode_slg1.py A4H F01 --params '{"object": "ZLOG", "max_rows": 10}'
python sap_tcode_slg1.py A4H F02 --params '{"lognumber": "<BALHDR-LOGNUMBER>"}'
```

F02 주의: BALDAT는 클러스터 테이블이라 RFC_READ_TABLE 불가(AD718 실측) → 메시지 본문은 GUI 전용 에러 가능. F01 헤더까지가 RFC 지원 범위.

### SM59 — `sap_tcode_sm59.py`

```powershell
python sap_tcode_sm59.py A4H F01 --params '{}'                          # 전체 목적지 (RFCTYPE 필터 선택)
python sap_tcode_sm59.py A4H F02 --params '{"rfcdest": "NONE"}'         # 상세 (RFCDEST/RFCTYPE/RFCOPTIONS 부분집합 — 512자 제한 실측)
python sap_tcode_sm59.py A4H F03 --params '{}'                          # STFC_CONNECTION ping
```

### DB02 — `sap_tcode_db02.py`

```powershell
python sap_tcode_db02.py A4H F01 --params '{}'                          # CON_NAME별 최신 스냅샷
python sap_tcode_db02.py A4H F02 --params '{"date_from": "20260901", "rowcount": 50}'
```

F03(`f03_table_sizes`)은 trial에 원천 테이블 없음 → `NotImplementedError`.

## Gotchas (자주 묻는 오류)

1. **쓰기가 반영 안 됨** → `commit`/`execute` 미지정. SU01/SU10은 `commit: true`, SM37 F03은 `execute: true` 필요.
2. **SU01 F07b E 리턴** → 미보유 롤 삭제 시도이거나 FROM_DAT/TO_DAT 불일치. F01(`BAPI_USER_GET_DETAIL` → ACTIVITYGROUPS)으로 보유분 먼저 확인.
3. **`unknown tool`** → id(F01) 또는 name(f01_...) 정확히. 모듈별 ID 체계가 다름(SU01 F07a~d 주의).
4. **TABLE_WITHOUT_DATA / TABLE_NOT_AVAILABLE** → dynpro·클러스터 테이블은 RFC 미지원이 정상. 스킬 함수 내 에러 메시지의 우회안(F01 헤더, F02 직접 키)을 따를 것.

## Registration (새 프로그램 추가 시 — 파일 관리)

새 `sap_tcode_<new>.py`를 추가한 에이전트/사용자는 반드시:

1. `sap-tcode-to-python` 스킬의 생성 규칙(TOOLS + get_tool_defs + call_tool)을 지킬 것.
2. `python tools/build_registry.py` 실행 → `registry.json` 갱신 (커밋에 포함).
3. 본 SKILL.md의 Module catalog + Function usage에 1행 이상 추가 (복붙용 CLI 예 포함).
4. `python -m py_compile sap_tcode_<new>.py` 통과 확인.

`registry.json`이 진실의 원천(source of truth)이다. 본 문장과 레지스트리가 다르면 레지스트리를 따른다.
