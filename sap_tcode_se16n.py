"""SE16N (Table Display) RFC-only 재현. 분석서: docs/analysis/A4H_SE16N.md
참고: SE16N 티코드는 A4H trial의 TSTC/TSTCP/ADT에 없음(미포함 추정).
본 모듈은 SE16N의 RFC 핵심(RFC_READ_TABLE 기반 테이블 조회)을 구현한다.

외부 MCP 래핑용: from sap_tcode_se16n import TOOLS, call_tool
"""
import os
from sap_monthly_report import (get_connection_by_name, rfc_read_table,
                                rfc_read_full, table_fields)

SYSTEM = "A4H"

def _default_system(explicit=None):
    """접속 시스템 결정: 명시 인자 > $SAP_SYSTEM/$SAP_DEFAULT_SYSTEM > SYSTEM 상수."""
    return explicit or os.environ.get("SAP_SYSTEM") or os.environ.get("SAP_DEFAULT_SYSTEM") or SYSTEM

TCODE = "SE16N"


# --- F01: 테이블 내용 조회 (원천: RFC_READ_TABLE, R 실측) ---
def f01_display_table(conn, *, table, fields=None, where="",
                      rowcount=100, rowskips=0):
    """테이블 내용 조회. Args: table(예 'TSTC'), fields(선택, 기본 전체),
    where(예 "TCODE = 'SU01'"), rowcount(기본 100), rowskips(기본 0).
    Returns: {"columns": [...], "rows": [...]}"""
    if not fields:
        info = table_fields(conn, table)
        fields = [f["FIELDNAME"] for f in info["DFIES_TAB"]]
    res = rfc_read_table(conn, table, fields, where=where,
                         rowcount=rowcount, rowskips=rowskips)
    delim = res.get("DELIMITER", "|") if isinstance(res, dict) else "|"
    rows = []
    for r in res["DATA"]:
        vals = [c.strip() for c in r["WA"].split(delim)]
        rows.append(dict(zip(fields, vals)))
    return {"result": {"columns": fields, "rows": rows}, "raw": rows}


# --- F02: 테이블 구조 조회 (원천: DDIF_FIELDINFO_GET) ---
def f02_describe_table(conn, *, table):
    """테이블 구조 조회. Args: table. Returns: {"fields": [{FIELDNAME, DATATYPE, LENG, KEYFLAG}...]}}"""
    info = table_fields(conn, table)
    fields = [{"FIELDNAME": f.get("FIELDNAME"), "DATATYPE": f.get("DATATYPE"),
               "LENG": f.get("LENG"), "KEYFLAG": f.get("KEYFLAG")}
              for f in info["DFIES_TAB"]]
    return {"result": {"fields": fields}, "raw": fields}


TOOLS = [
    {"id": "F01", "name": "f01_display_table", "description": "SE16N 테이블 내용 조회 (RFC_READ_TABLE)",
     "input_schema": {"type": "object",
        "properties": {
            "table": {"type": "string", "description": "테이블명, 예 TSTC"},
            "fields": {"type": "array", "description": "필드 목록, 생략 시 전체"},
            "where": {"type": "string", "description": "WHERE 조건"},
            "rowcount": {"type": "integer", "description": "기본 100"},
            "rowskips": {"type": "integer", "description": "기본 0"}},
        "required": ["table"]},
     "func": "f01_display_table"},
    {"id": "F02", "name": "f02_describe_table", "description": "SE16N 테이블 구조 조회 (DDIF_FIELDINFO_GET)",
     "input_schema": {"type": "object",
        "properties": {"table": {"type": "string", "description": "테이블명"}},
        "required": ["table"]},
     "func": "f02_describe_table"},
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
    # 사용법: python sap_tcode_se16n.py A4H F01 --params '{"table": "TSTC", "rowcount": 5}'
    system = sys.argv[1] if len(sys.argv) > 1 else _default_system()
    tool = sys.argv[2] if len(sys.argv) > 2 else "F01"
    params = {}
    if "--params" in sys.argv:
        params = json.loads(sys.argv[sys.argv.index("--params") + 1])
    print(json.dumps(call_tool(tool, system, **params), ensure_ascii=False, default=str)[:2000])
