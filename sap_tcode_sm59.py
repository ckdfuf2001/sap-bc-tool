"""SM59 (RFC Destinations) RFC-only 재현. 분석서: docs/analysis/A4H_SM59.md
프로그램 SAPMCRFC (모듈풀, TSTC 실측, DYPNO 0100). 원천 테이블 RFCDES (DFIES 17필드, KEY RFCDEST 실측).

외부 MCP 래핑용: from sap_tcode_sm59 import TOOLS, call_tool
"""
import os
from sap_monthly_report import (get_connection_by_name, rfc_read_table,
                                rfc_read_full)

SYSTEM = "A4H"

def _default_system(explicit=None):
    """접속 시스템 결정: 명시 인자 > $SAP_SYSTEM/$SAP_DEFAULT_SYSTEM > SYSTEM 상수."""
    return explicit or os.environ.get("SAP_SYSTEM") or os.environ.get("SAP_DEFAULT_SYSTEM") or SYSTEM

TCODE = "SM59"


# --- F01: RFC 목적지 목록 (원천: RFC_READ_TABLE RFCDES) ---
def f01_list_destinations(conn, *, rfctype="", max_rows=100):
    """RFC 목적지 목록. Args: rfctype(선택, RFCTYPE 예 '3'=ABAP),
    max_rows(기본 100). Returns: {"destinations": [...]}}"""
    fields = ["RFCDEST", "RFCTYPE", "RFCOPTIONS"]
    where = f"RFCTYPE = '{rfctype}'" if rfctype else ""
    res = rfc_read_table(conn, "RFCDES", fields, where=where, rowcount=max_rows)
    rows = []
    for r in res["DATA"]:
        vals = [c.strip() for c in r["WA"].split("|")]
        rows.append(dict(zip(fields, vals)))
    return {"result": {"destinations": rows}, "raw": rows}


# --- F02: RFC 목적지 상세 (원천: RFC_READ_TABLE RFCDES) ---
def f02_destination_detail(conn, *, rfcdest):
    """RFC 목적지 상세. Args: rfcdest.
    실측: RFCDES 행 전체(250자 필드 다수)는 RFC_READ_TABLE 512자 제한 초과
    (DATA_BUFFER_EXCEEDED) → RFCDEST/RFCTYPE/RFCOPTIONS 부분집합 반환.
    Returns: {"destination": {...}}}"""
    fields = ["RFCDEST", "RFCTYPE", "RFCOPTIONS"]
    res = rfc_read_full(conn, "RFCDES", fields, where=f"RFCDEST = '{rfcdest}'")
    if not res:
        raise KeyError(f"destination not found: {rfcdest}")
    return {"result": {"destination": res[0]}, "raw": res[0]}


# --- F03: 연결 테스트 (원천: RFC ping — STFC_CONNECTION) ---
def f03_ping(conn):
    """RFC 레이어 연결 테스트 (SM59 연결 테스트의 전송계층 equivalent).
    대상별 테스트는 GUI 전용. Returns: {"ok": True, ...}}"""
    res = conn.call("STFC_CONNECTION", REQUTEXT="sm59-ping")
    return {"result": {"ok": True, "echotext": res.get("ECHOTEXT"),
                       "responsetext": res.get("RESPTEXT")}, "raw": res}


TOOLS = [
    {"id": "F01", "name": "f01_list_destinations", "description": "SM59 RFC 목적지 목록 (RFCDES)",
     "input_schema": {"type": "object",
        "properties": {
            "rfctype": {"type": "string", "description": "RFCTYPE, 예 3=ABAP. 선택"},
            "max_rows": {"type": "integer", "description": "기본 100"}},
        "required": []},
     "func": "f01_list_destinations"},
    {"id": "F02", "name": "f02_destination_detail", "description": "SM59 RFC 목적지 상세 (RFCDES 전 필드)",
     "input_schema": {"type": "object",
        "properties": {"rfcdest": {"type": "string", "description": "RFCDEST"}},
        "required": ["rfcdest"]},
     "func": "f02_destination_detail"},
    {"id": "F03", "name": "f03_ping", "description": "SM59 연결 테스트 전송계층 equivalent (STFC_CONNECTION)",
     "input_schema": {"type": "object", "properties": {}, "required": []},
     "func": "f03_ping"},
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
    # 사용법: python sap_tcode_sm59.py A4H F01 --params '{}'
    system = sys.argv[1] if len(sys.argv) > 1 else _default_system()
    tool = sys.argv[2] if len(sys.argv) > 2 else "F01"
    params = {}
    if "--params" in sys.argv:
        params = json.loads(sys.argv[sys.argv.index("--params") + 1])
    print(json.dumps(call_tool(tool, system, **params), ensure_ascii=False, default=str)[:2000])
