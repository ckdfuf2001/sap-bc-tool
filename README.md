# sap-bc-tool

SAP Basis 티코드를 RFC/BAPI만으로 재현하는 파이썬 툴셋. 티코드 분석(스킬) → 파이썬 생성(스킬) → 실서버 검증까지 이 레포에서 수행한다.

## 구성

| 경로 | 내용 |
|---|---|
| `.opencode/skills/sap-tcode-analyze/` | 분석 스킬: 시스템명+티코드 → `docs/analysis/<SYS>_<TCODE>.md` + 단일 HTML + 연계 다이어그램 |
| `.opencode/skills/sap-tcode-to-python/` | 개발 스킬: 분석서 → `sap_tcode_<tcode>.py` (MCP 재사용 구조) |
| `docs/analysis/` | 분석서 MD/HTML + `index.html` 목록 (상대경로, 오프라인 단일 파일) |
| `sap_tcode_*.py` | 티코드별 RFC-only 모듈 (TOOLS + `get_tool_defs()` + `call_tool()`) |
| `sap_monthly_report.py` | 공용: 접속(`get_connection_by_name`), `rfc_read_table`/`rfc_read_full`, 상태 기록 |
| `tools/build_html.py` | MD → HTML 전체 변환기 (`python tools/build_html.py docs/analysis`) |
| `tools/install_sdk.ps1` | 새 PC용 SDK+pyrfc 일괄 설치 |
| `sap_systems.example.json` | 접속정보 양식 (실파일 `sap_systems.json`은 gitignore) |

## 티코드 현황 (A4H 실측)

SU01(쓰기 전주기 검증済) · SU10 · SE16N(trial 미포함, equivalent) · ST22 · SM12 · SM21 · SM37 · SM50 · SLG1 · SM59.
상세는 `docs/analysis/index.html`을 브라우저로 열 것.

## 사전 준비

1. Python 3.12, Docker Desktop (WSL 메모리 20GB 권장, `.wslconfig` 참고)
2. SAP 시스템 (로컬 trial 또는 실시스템)
3. SAP NW RFC SDK 7.50 Windows x64 zip (SAP 포털에서 직접 다운로드 — **라이선스상 재배포 금지라 레포 미포함**)
4. pyrfc 휠 (PyPI 미등록 → GitHub `SAP-archive/PyRFC` releases에서 `cp312 win_amd64` 다운로드)

## 새 PC 세팅

```powershell
git clone https://github.com/ckdfuf2001/sap-bc-tool.git
pip install erpl-adt pandas openpyxl
powershell -ExecutionPolicy Bypass -File tools\install_sdk.ps1 `
  -SdkZip "$env:USERPROFILE\Downloads\nwrfc750P_19-70002755.zip" `
  -PyrfcWheel "<pyrfc-3.3.1-cp312-cp312-win_amd64.whl 경로>"
Copy-Item sap_systems.example.json sap_systems.json  # 접속정보 입력 (A4H 예: localhost/00/001/DEVELOPER/EN)
erpl-adt login --host <host> --port <port> [--https] --user <user> --client <cli>
```

로컬 trial 기동 시:

```powershell
docker run --stop-timeout 3600 -d --name a4h -h vhcala4hci `
  -p 3200:3200 -p 3300:3300 -p 8443:8443 -p 30213:30213 -p 50000:50000 -p 50001:50001 `
  sapse/abap-cloud-developer-trial:2025 -skip-limits-check -agree-to-sap-license
```

참고: WSL 커널 파라미터(`kernel.shmmni=32768` 등)는 WSL 재시작 시 초기화되므로 기동 실패 시 재적용.
trial 자체서명 인증서 때문에 erpl-adt 호출마다 `--insecure` 필요.

## 다른 PC에서 쓰기 (접속정보만 채우기)

이 레포에는 비밀번호·호스트·SID가 박혀 있지 않다. 아래 2개만 채우면 된다.

1. `Copy-Item sap_systems.example.json sap_systems.json` 후 ashost/sysnr/client/user 입력.
   비밀번호는 평문 대신 환경변수 참조: `"passwd": "${SAP_PW_A4H}"` + `$env:SAP_PW_A4H='...'`
   (`sap_systems.json`은 gitignore라 커밋되지 않는다)
2. (선택) 기본 시스템 변경: `$env:SAP_SYSTEM='PRD'` (없으면 각 모듈의 `SYSTEM` 기본값 사용).
   직접 지정도 가능: `python sap_tcode_sm50.py PRD F01 --params '{}'`

호출 3순위: 명시 인자(system/conn) > `$SAP_SYSTEM`/`$SAP_DEFAULT_SYSTEM` > 모듈 `SYSTEM` 상수.

## 사용법

```powershell
# 분석 (먼저)
# opencode 스킬 sap-tcode-analyze: 시스템명 + 티코드 입력 → docs/analysis/ 산출물
# HTML 재생성
python tools/build_html.py docs/analysis

# 파이썬 생성 (나중)
# opencode 스킬 sap-tcode-to-python: 분석서 경로 입력 → sap_tcode_<tcode>.py

# 직접 호출
python sap_tcode_su01.py A4H F01 --params '{"username": "DEVELOPER"}'
```

MCP 재사용: `from sap_tcode_su01 import TOOLS, call_tool` 후 FastMCP 등에 등록.

## 주의

- 접속 비밀번호는 `sap_systems.json` + `${ENV}` 방식만 사용 (평문 하드코딩·인자 전달 금지, 스킬 규칙)
- 쓰기 함수는 기본 dry-run (`commit=True` 명시 시에만 COMMIT)
- `sap_systems.json`, `.adt.creds`, `sap_connection_state.json`은 커밋 금지 (gitignore)
- NW RFC SDK 바이너리는 재배포 금지 — 레포에 포함하지 않음
