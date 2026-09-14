"""SLG1 (Application Log: Display Logs) RFC-only 재현. 분석서: docs/analysis/A4H_SLG1.md
프로그램 SBAL_DISPLAY (TSTC 실측, DYPNO 1000) → CALL FUNCTION 'APPL_LOG_DISPLAY'.
BAL_* FM은 RFC 미지원(blank) 실측 → RFC_READ_TABLE(BALHDR/BALDAT) 직접 조회.

외부 MCP 래핑용: from sap_tcode_slg1 import TOOLS, call_tool
"""
import os
from sap_monthly_report import (get_connection_by_name, rfc_read_table,
                                rfc_read_full, table_fields)

SYSTEM = "A4H"

def _default_system(explicit=None):
    """접속 시스템 결정: 명시 인자 > $SAP_SYSTEM/$SAP_DEFAULT_SYSTEM > SYSTEM 상수."""
    return explicit or os.environ.get("SAP_SYSTEM") or os.environ.get("SAP_DEFAULT_SYSTEM") or SYSTEM

TCODE = "SLG1"


def _balhdr_fields(conn):
    info = table_fields(conn, "BALHDR")
    return [f["FIELDNAME"] for f in info["DFIES_TAB"]]


# --- F01: 로그 헤더 검색 (원천: RFC_READ_TABLE BALHDR) ---
def f01_search_logs(conn, *, object="", subobject="", extnumber="", max_rows=50):
    """로그 헤더 검색. Args: object(BAL OBJECT, 선택),
    subobject(선택), extnumber(선택), max_rows(기본 50).
    Returns: {"logs": [...]}}"""
    conds = []
    if object:
        conds.append(f"OBJECT = '{object}'")
    if subobject:
        conds.append(f"SUBOBJECT = '{subobject}'")
    if extnumber:
        conds.append(f"EXTNUMBER = '{extnumber}'")
    where = " AND ".join(conds)
    fields = ["LOGNUMBER", "OBJECT", "SUBOBJECT", "EXTNUMBER", "ALDATE", "ALTIME", "ALUSER"]
    res = rfc_read_table(conn, "BALHDR", fields, where=where, rowcount=max_rows)
    rows = []
    for r in res["DATA"]:
        vals = [c.strip() for c in r["WA"].split("|")]
        rows.append(dict(zip(fields, vals)))
    return {"result": {"logs": rows}, "raw": rows}


# --- F02: 로그 메시지 조회 (원천: BALDAT — RFC_READ_TABLE 제한 실측) ---
def f02_read_messages(conn, *, lognumber, max_rows=200):
    """로그 메시지 조회. Args: lognumber(BALHDR-LOGNUMBER), max_rows(기본 200).
    실측: BALDAT는 클러스터 테이블로 RFC_READ_TABLE 불가(AD718),
    APPL_LOG_READ_DB_WITH_LOGNO는 RFC 미지원 → GUI 전용 명시 에러.
    Returns: {"messages": [...]}}"""
    fields = ["LOGNUMBER", "MSGTY", "MSGID", "MSGNO", "MSGV1", "MSGV2", "MSGV3", "MSGV4"]
    try:
        res = rfc_read_full(conn, "BALDAT", fields,
                            where=f"LOGNUMBER = '{lognumber}'")[:max_rows]
    except Exception as e:
        if "TABLE_WITHOUT_DATA" in str(e):
            raise RuntimeError(
                "BALDAT는 클러스터 테이블로 RFC_READ_TABLE 불가(AD718 실측). "
                "SLG1 메시지 본문은 GUI 전용 - F01 헤더까지만 RFC 지원.") from e
        raise
    return {"result": {"messages": res}, "raw": res}


TOOLS = [
    {"id": "F01", "name": "f01_search_logs", "description": "SLG1 로그 헤더 검색 (BALHDR)",
     "input_schema": {"type": "object",
        "properties": {
            "object": {"type": "string", "description": "BAL OBJECT, 선택"},
            "subobject": {"type": "string", "description": "선택"},
            "extnumber": {"type": "string", "description": "선택"},
            "max_rows": {"type": "integer", "description": "기본 50"}},
        "required": []},
     "func": "f01_search_logs"},
    {"id": "F02", "name": "f02_read_messages", "description": "SLG1 로그 메시지 조회 (BALDAT)",
     "input_schema": {"type": "object",
        "properties": {
            "lognumber": {"type": "string", "description": "BALHDR-LOGNUMBER"},
            "max_rows": {"type": "integer", "description": "기본 200"}},
        "required": ["lognumber"]},
     "func": "f02_read_messages"},
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
    # 사용법: python sap_tcode_slg1.py A4H F01 --params '{"max_rows": 10}'
    system = sys.argv[1] if len(sys.argv) > 1 else _default_system()
    tool = sys.argv[2] if len(sys.argv) > 2 else "F01"
    params = {}
    if "--params" in sys.argv:
        params = json.loads(sys.argv[sys.argv.index("--params") + 1])
    print(json.dumps(call_tool(tool, system, **params), ensure_ascii=False, default=str)[:2000])
