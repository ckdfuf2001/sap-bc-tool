"""SM21 (system log) RFC-only 재현. 분석서: docs/analysis/A4H_SM21.md
프로그램 RSYSLOG (TSTC 실측, DYPNO 1000). RFC 경로 SALC_MSC_READ_SYSLOG (R 실측).

외부 MCP 래핑용: from sap_tcode_sm21 import TOOLS, call_tool
"""
from sap_monthly_report import get_connection_by_name

SYSTEM = "A4H"
TCODE = "SM21"


# --- F01: 시스템 로그 조회 (원천: SALC_MSC_READ_SYSLOG) ---
def f01_read_syslog(conn, *, start_timestamp="", end_timestamp="", max_lines=200):
    """시스템 로그 조회. Args: start_timestamp/end_timestamp(선택, YYYYMMDDHHMMSS),
    max_lines(기본 200, 초과분 절단). Returns: {"lines": [...]}}"""
    params = {}
    if start_timestamp:
        params["START_TIMESTAMP"] = start_timestamp
    if end_timestamp:
        params["END_TIMESTAMP"] = end_timestamp
    res = conn.call("SALC_MSC_READ_SYSLOG", **params)
    lines = res.get("MSC_SYSLOG_LINES", [])[:max_lines]
    return {"result": {"lines": lines, "count": len(lines)}, "raw": lines}


TOOLS = [
    {"id": "F01", "name": "f01_read_syslog", "description": "SM21 시스템 로그 조회 (SALC_MSC_READ_SYSLOG)",
     "input_schema": {"type": "object",
        "properties": {
            "start_timestamp": {"type": "string", "description": "YYYYMMDDHHMMSS, 선택"},
            "end_timestamp": {"type": "string", "description": "YYYYMMDDHHMMSS, 선택"},
            "max_lines": {"type": "integer", "description": "기본 200"}},
        "required": []},
     "func": "f01_read_syslog"},
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
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    import sys
    import json
    # 사용법: python sap_tcode_sm21.py A4H F01 --params '{"max_lines": 20}'
    system = sys.argv[1] if len(sys.argv) > 1 else SYSTEM
    tool = sys.argv[2] if len(sys.argv) > 2 else "F01"
    params = {}
    if "--params" in sys.argv:
        params = json.loads(sys.argv[sys.argv.index("--params") + 1])
    print(json.dumps(call_tool(tool, system, **params), ensure_ascii=False, default=str)[:2000])
