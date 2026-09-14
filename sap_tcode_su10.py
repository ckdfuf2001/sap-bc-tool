"""SU10 (User Mass Maintenance) RFC-only 재현. 분석서: docs/analysis/A4H_SU10.md
프로그램 SAPMSUU0M (TSTC 실측) → CALL FUNCTION 'SUID_IDENTITY_MAINT' (I_TCODE_MODE=10, 원문 실측).
RFC 재현은 sap_tcode_su01의 BAPI 함수를 재사용한 대량 래퍼.

외부 MCP 래핑용: from sap_tcode_su10 import TOOLS, call_tool
"""
import os
from sap_monthly_report import get_connection_by_name
from sap_tcode_su01 import f02_create, f03_change, f04_delete

SYSTEM = "A4H"

def _default_system(explicit=None):
    """접속 시스템 결정: 명시 인자 > $SAP_SYSTEM/$SAP_DEFAULT_SYSTEM > SYSTEM 상수."""
    return explicit or os.environ.get("SAP_SYSTEM") or os.environ.get("SAP_DEFAULT_SYSTEM") or SYSTEM

TCODE = "SU10"


def _mass(conn, func, users, **kw):
    """users 행 리스트에 func逐行 적용. 결과 {ok:[...], failed:[{user, error}]}"""
    ok, failed = [], []
    for u in users:
        try:
            func(conn, username=u, **kw)
            ok.append(u)
        except Exception as e:
            failed.append({"user": u, "error": str(e)[:200]})
    return {"result": {"ok": ok, "failed": failed,
                       "ok_count": len(ok), "fail_count": len(failed)},
            "raw": {"ok": ok, "failed": failed}}


# --- F01: 대량 생성 (원천: BAPI_USER_CREATE 반복) ---
def f01_mass_create(conn, *, users, logondata=None, password=None, commit=False):
    """대량 생성. Args: users(USERNAME 리스트), logondata/password(공통, 선택),
    commit(기본 False). Returns: {"ok": [...], "failed": [...]}}"""
    return _mass(conn, f02_create, users, logondata=logondata,
                 password=password, commit=commit)


# --- F02: 대량 변경 (원천: BAPI_USER_CHANGE 반복) ---
def f02_mass_change(conn, *, users, commit=False, **changes):
    """대량 변경. Args: users + 변경 구조체 키워드. Returns: {"ok": [...], "failed": [...]}}"""
    return _mass(conn, f03_change, users, commit=commit, **changes)


# --- F03: 대량 삭제 (원천: BAPI_USER_DELETE 반복) ---
def f03_mass_delete(conn, *, users, commit=False):
    """대량 삭제. Args: users, commit(기본 False). Returns: {"ok": [...], "failed": [...]}}"""
    return _mass(conn, f04_delete, users, commit=commit)


TOOLS = [
    {"id": "F01", "name": "f01_mass_create", "description": "SU10 대량 생성 (BAPI_USER_CREATE 반복)",
     "input_schema": {"type": "object",
        "properties": {
            "users": {"type": "array", "description": "USERNAME 리스트"},
            "logondata": {"type": "object", "description": "공통 BAPILOGOND, 선택"},
            "password": {"type": "object", "description": "공통 BAPIPWD, 선택"},
            "commit": {"type": "boolean", "description": "True일 때만 COMMIT"}},
        "required": ["users"]},
     "func": "f01_mass_create"},
    {"id": "F02", "name": "f02_mass_change", "description": "SU10 대량 변경 (BAPI_USER_CHANGE 반복)",
     "input_schema": {"type": "object",
        "properties": {
            "users": {"type": "array", "description": "USERNAME 리스트"},
            "commit": {"type": "boolean", "description": "True일 때만 COMMIT"}},
        "required": ["users"]},
     "func": "f02_mass_change"},
    {"id": "F03", "name": "f03_mass_delete", "description": "SU10 대량 삭제 (BAPI_USER_DELETE 반복)",
     "input_schema": {"type": "object",
        "properties": {
            "users": {"type": "array", "description": "USERNAME 리스트"},
            "commit": {"type": "boolean", "description": "True일 때만 COMMIT"}},
        "required": ["users"]},
     "func": "f03_mass_delete"},
]


def get_tool_defs():
    """외부 MCP 서버용: TOOLS에서 func 객체를 제외한 JSON 직렬화 가능 정의 반환."""
    return [{k: v for k, v in t.items() if k != "func"} for t in TOOLS]


def call_tool(name_or_id, conn_or_system=None, **kwargs):
    """외부 MCP 핸들러용 단일 진입점: tool명/F01 → 함수 디스패치."""
    conn = conn_or_system if hasattr(conn_or_system, "call") else get_connection_by_name(_default_system(conn_or_system))
    try:
        for t in TOOLS:
            if name_or_id in (t["id"], t["name"]):
                return globals()[t["func"]](conn, **kwargs)
        raise KeyError(f"unknown tool: {name_or_id}, available: {[t['id'] for t in TOOLS]}")
    finally:
        if not hasattr(conn_or_system, "call"):
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    import sys
    import json
    # 사용법: python sap_tcode_su10.py A4H F01 --params '{"users": ["U1", "U2"]}'
    system = sys.argv[1] if len(sys.argv) > 1 else _default_system()
    tool = sys.argv[2] if len(sys.argv) > 2 else "F01"
    params = {}
    if "--params" in sys.argv:
        params = json.loads(sys.argv[sys.argv.index("--params") + 1])
    print(json.dumps(call_tool(tool, system, **params), ensure_ascii=False, default=str)[:2000])
