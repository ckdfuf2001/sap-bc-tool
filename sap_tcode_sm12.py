"""SM12 (Display and Delete Locks) RFC-only 재현. 분석서: docs/analysis/A4H_SM12.md
프로그램 RS_ENQ_ADMIN (TSTC 실측, DYPNO 1000). RFC 경로 ENQUEUE_READ (FMODE=R 실측).

외부 MCP 래핑용: from sap_tcode_sm12 import TOOLS, call_tool
"""
import os
from sap_monthly_report import get_connection_by_name

SYSTEM = "A4H"

def _default_system(explicit=None):
    """접속 시스템 결정: 명시 인자 > $SAP_SYSTEM/$SAP_DEFAULT_SYSTEM > SYSTEM 상수."""
    return explicit or os.environ.get("SAP_SYSTEM") or os.environ.get("SAP_DEFAULT_SYSTEM") or SYSTEM

TCODE = "SM12"


# --- F01: 락 목록 조회 (원천: ENQUEUE_READ) ---
def f01_list_locks(conn, *, username="", tablename="", client=""):
    """락 목록 조회. Args: username(선택, GUNAME), tablename(선택, GNAME),
    client(선택, GCLIENT. 생략 시 전체). Returns: {"locks": [...], "count": n}}"""
    params = {}
    if client:
        params["GCLIENT"] = client
    if username:
        params["GUNAME"] = username
    if tablename:
        params["GNAME"] = tablename
    res = conn.call("ENQUEUE_READ", **params)
    locks = res.get("ENQ", [])
    return {"result": {"locks": locks, "count": len(locks)}, "raw": locks}


TOOLS = [
    {"id": "F01", "name": "f01_list_locks", "description": "SM12 락 목록 조회 (ENQUEUE_READ)",
     "input_schema": {"type": "object",
        "properties": {
            "username": {"type": "string", "description": "GUNAME, 선택"},
            "tablename": {"type": "string", "description": "GNAME, 선택"}},
        "required": []},
     "func": "f01_list_locks"},
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
    # 사용법: python sap_tcode_sm12.py A4H F01 --params '{}'
    system = sys.argv[1] if len(sys.argv) > 1 else _default_system()
    tool = sys.argv[2] if len(sys.argv) > 2 else "F01"
    params = {}
    if "--params" in sys.argv:
        params = json.loads(sys.argv[sys.argv.index("--params") + 1])
    print(json.dumps(call_tool(tool, system, **params), ensure_ascii=False, default=str)[:2000])
