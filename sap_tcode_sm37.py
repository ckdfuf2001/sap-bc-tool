"""SM37 (Overview of job selection) RFC-only 재현. 분석서: docs/analysis/A4H_SM37.md
프로그램 SAPLBTCH (그룹 BTCH, TSTC 실측, DYPNO 3000).
RFC 경로: BAPI_XBP_JOB_SELECT (R 실측) + TBTCO 직접 조회 (DFIES 58필드, KEY JOBNAME+JOBCOUNT 실측).

외부 MCP 래핑용: from sap_tcode_sm37 import TOOLS, call_tool
"""
from sap_monthly_report import (get_connection_by_name, rfc_read_table,
                                rfc_read_full)

SYSTEM = "A4H"
TCODE = "SM37"


# --- F01: 잡 목록 조회 (원천: RFC_READ_TABLE TBTCO) ---
def f01_select_jobs(conn, *, jobname="", max_rows=50):
    """잡 목록 조회. Args: jobname(선택, prefix LIKE), max_rows(기본 50).
    Returns: {"jobs": [{JOBNAME, JOBCOUNT, SDLSTRTDT, SDLSTRTTM, STATUS}]}}"""
    fields = ["JOBNAME", "JOBCOUNT", "SDLSTRTDT", "SDLSTRTTM", "STATUS"]
    where = f"JOBNAME LIKE '{jobname}%'" if jobname else ""
    res = rfc_read_table(conn, "TBTCO", fields, where=where, rowcount=max_rows)
    rows = []
    for r in res["DATA"]:
        vals = [c.strip() for c in r["WA"].split("|")]
        rows.append(dict(zip(fields, vals)))
    return {"result": {"jobs": rows}, "raw": rows}


# --- F02: 잡 상세 조회 (원천: RFC_READ_TABLE TBTCO 핵심 필드) ---
def f02_job_detail(conn, *, jobname, jobcount):
    """잡 상세 조회. Args: jobname, jobcount(TBTCO KEY).
    Returns: {"job": {...}}} (핵심 8필드. SDLPRIO는 TBTCO에 없음 — 실측)"""
    fields = ["JOBNAME", "JOBCOUNT", "SDLSTRTDT", "SDLSTRTTM", "STATUS",
              "SDLUNAME", "AUTHCKNAM", "JOBCLASS"]
    res = rfc_read_full(conn, "TBTCO", fields,
                        where=f"JOBNAME = '{jobname}' AND JOBCOUNT = '{jobcount}'")
    if not res:
        raise KeyError(f"job not found: {jobname} {jobcount}")
    return {"result": {"job": res[0]}, "raw": res[0]}


# --- F03: 잡 중단 (원천: BAPI_XBP_JOB_ABORT, R 실측) ---
def f03_abort_job(conn, *, jobname, jobcount, execute=False):
    """잡 중단. Args: jobname, jobcount, execute(기본 False=dry-run).
    execute=True일 때만 실제 ABORT 호출. Returns: {"aborted": bool}}"""
    if not execute:
        return {"result": {"aborted": False, "dry_run": True,
                           "target": f"{jobname}/{jobcount}"}, "raw": {}}
    res = conn.call("BAPI_XBP_JOB_ABORT", JOBNAME=jobname, JOBCOUNT=jobcount)
    return {"result": {"aborted": True, "target": f"{jobname}/{jobcount}"}, "raw": res}


TOOLS = [
    {"id": "F01", "name": "f01_select_jobs", "description": "SM37 잡 목록 조회 (TBTCO)",
     "input_schema": {"type": "object",
        "properties": {
            "jobname": {"type": "string", "description": "prefix LIKE, 선택"},
            "max_rows": {"type": "integer", "description": "기본 50"}},
        "required": []},
     "func": "f01_select_jobs"},
    {"id": "F02", "name": "f02_job_detail", "description": "SM37 잡 상세 조회 (TBTCO KEY)",
     "input_schema": {"type": "object",
        "properties": {
            "jobname": {"type": "string", "description": "JOBNAME"},
            "jobcount": {"type": "string", "description": "JOBCOUNT"}},
        "required": ["jobname", "jobcount"]},
     "func": "f02_job_detail"},
    {"id": "F03", "name": "f03_abort_job", "description": "SM37 잡 중단 (BAPI_XBP_JOB_ABORT, execute 명시)",
     "input_schema": {"type": "object",
        "properties": {
            "jobname": {"type": "string", "description": "JOBNAME"},
            "jobcount": {"type": "string", "description": "JOBCOUNT"},
            "execute": {"type": "boolean", "description": "True일 때만 실제 중단"}},
        "required": ["jobname", "jobcount"]},
     "func": "f03_abort_job"},
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
    # 사용법: python sap_tcode_sm37.py A4H F01 --params '{"max_rows": 10}'
    system = sys.argv[1] if len(sys.argv) > 1 else SYSTEM
    tool = sys.argv[2] if len(sys.argv) > 2 else "F01"
    params = {}
    if "--params" in sys.argv:
        params = json.loads(sys.argv[sys.argv.index("--params") + 1])
    print(json.dumps(call_tool(tool, system, **params), ensure_ascii=False, default=str)[:2000])
