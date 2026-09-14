"""ST22 (ABAP Dump Analysis) RFC-only 재현. 분석서: docs/analysis/A4H_ST22.md
프로그램 RSSHOWRABAX (TSTC 실측, DYPNO 1000). 덤프 원천 테이블 SNAP (DFIES 실측).

외부 MCP 래핑용: from sap_tcode_st22 import TOOLS, call_tool
"""
import os
from sap_monthly_report import get_connection_by_name, rfc_read_table

SYSTEM = "A4H"

def _default_system(explicit=None):
    """접속 시스템 결정: 명시 인자 > $SAP_SYSTEM/$SAP_DEFAULT_SYSTEM > SYSTEM 상수."""
    return explicit or os.environ.get("SAP_SYSTEM") or os.environ.get("SAP_DEFAULT_SYSTEM") or SYSTEM

TCODE = "ST22"
SNAP_KEY = ["DATUM", "UZEIT", "AHOST", "UNAME", "MANDT", "MODNO", "SEQNO"]  # DFIES KEYFLAG 실측


def _snap_fields(conn):
    info = table_fields(conn, "SNAP")
    return [f["FIELDNAME"] for f in info["DFIES_TAB"]]


# --- F01: 덤프 목록 조회 (원천: SNAP — RFC_READ_TABLE 제한 실측) ---
def f01_list_dumps(conn, *, date_from="", max_rows=50):
    """덤프 목록 조회. Args: date_from(DATS YYYYMMDD, 선택), max_rows(기본 50).
    실측: SNAP은 RFC_READ_TABLE로 읽기 불가(DA131 TABLE_NOT_AVAILABLE).
    Returns: {"dumps": [...]}"""
    where = f"DATUM >= '{date_from}'" if date_from else ""
    try:
        res = rfc_read_table(conn, "SNAP", SNAP_KEY, where=where, rowcount=max_rows)
    except Exception as e:
        if "TABLE_NOT_AVAILABLE" in str(e):
            raise RuntimeError(
                "SNAP 테이블은 RFC_READ_TABLE로 읽기 불가(DA131 실측). "
                "ST22 목록은 GUI 전용 - 덤프 키(DATUM/UZEIT)를 알면 F02로 직접 조회.") from e
        raise
    rows = []
    for r in res["DATA"]:
        vals = [c.strip() for c in r["WA"].split("|")]
        rows.append(dict(zip(SNAP_KEY, vals)))
    rows.sort(key=lambda x: (x.get("DATUM", ""), x.get("UZEIT", "")), reverse=True)
    return {"result": {"dumps": rows}, "raw": rows}


# --- F02: 덤프 상세 조회 (원천: SABP_RABAX_GET_DUMP_FORMATTED, R 실측) ---
def f02_dump_detail(conn, *, datum, uzeit, uname="", ahost="", modno=""):
    """덤프 상세 조회. Args: datum(DATS), uzeit(TIMS), uname/ahost/modno(선택, SNAP_KEY 보완).
    MANDT는 접속 클라이언트로 자동 설정.
    Returns: {"lines": [...]}} (포맷 덤프 텍스트 행)"""
    from sap_monthly_report import find_system
    snap_key = {"DATUM": datum, "UZEIT": uzeit, "AHOST": ahost,
                "UNAME": uname, "MANDT": find_system(SYSTEM).get("client", "001"),
                "MODNO": modno}
    res = conn.call("SABP_RABAX_GET_DUMP_FORMATTED", I_SNAP=snap_key)
    lines = [r.get("LINE", "") if isinstance(r, dict) else str(r)
             for r in (res.get("RESULT") or [])]
    if not lines:
        raise KeyError(f"dump not found or empty: {datum} {uzeit} {uname}")
    return {"result": {"lines": lines}, "raw": lines}


TOOLS = [
    {"id": "F01", "name": "f01_list_dumps", "description": "ST22 덤프 목록 조회 (SNAP)",
     "input_schema": {"type": "object",
        "properties": {
            "date_from": {"type": "string", "description": "DATS YYYYMMDD, 선택"},
            "max_rows": {"type": "integer", "description": "기본 50"}},
        "required": []},
     "func": "f01_list_dumps"},
    {"id": "F02", "name": "f02_dump_detail", "description": "ST22 덤프 상세 조회 (SABP_RABAX_GET_DUMP_FORMATTED)",
     "input_schema": {"type": "object",
        "properties": {
            "datum": {"type": "string", "description": "DATS YYYYMMDD"},
            "uzeit": {"type": "string", "description": "TIMS HHMMSS"},
            "uname": {"type": "string", "description": "선택"},
            "ahost": {"type": "string", "description": "선택"},
            "modno": {"type": "string", "description": "선택"}},
        "required": ["datum", "uzeit"]},
     "func": "f02_dump_detail"},
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
    # 사용법: python sap_tcode_st22.py A4H F01 --params '{"max_rows": 10}'
    system = sys.argv[1] if len(sys.argv) > 1 else _default_system()
    tool = sys.argv[2] if len(sys.argv) > 2 else "F01"
    params = {}
    if "--params" in sys.argv:
        params = json.loads(sys.argv[sys.argv.index("--params") + 1])
    print(json.dumps(call_tool(tool, system, **params), ensure_ascii=False, default=str)[:2000])
