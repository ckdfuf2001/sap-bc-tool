"""DB02 (Tables and Indexes Monitor) RFC-only 재현. 분석서: docs/analysis/A4H_DB02.md
A4H trial 실측: TSTC-PGMNA=RSDB0002/DYPNO 1000, HDB_SIZE_HISTORY 실존,
DB_SIZE_HISTORY_FOR_COCKPIT 미존재(NOT_FOUND 실측) → F01은 HDB 최신 스냅샷으로 대체.
외부 MCP 래핑용: from sap_tcode_db02 import TOOLS, call_tool
"""
from sap_monthly_report import get_connection_by_name, rfc_read_full

SYSTEM = "A4H"
TCODE = "DB02"

HDB_FIELDS = ["CON_NAME", "COLLECT_DATE", "MEMORY_USED",
              "DISK_USED_DATA", "DISK_USED_LOG", "DISK_USED_TRACE"]


# --- F01: HANA 용량 최신 스냅샷 (원천: HDB_SIZE_HISTORY, A4H 실측) ---
def f01_db_overview(conn):
    """DB 용량 최신 스냅샷. CON_NAME별 최신 COLLECT_DATE 1행.
    Returns: {"rows": [...], "count": n}}"""
    rows = rfc_read_full(conn, "HDB_SIZE_HISTORY", HDB_FIELDS)
    latest = {}
    for r in rows:
        k = r.get("CON_NAME")
        if k not in latest or r.get("COLLECT_DATE", "") > latest[k].get("COLLECT_DATE", ""):
            latest[k] = r
    snap = sorted(latest.values(), key=lambda r: r.get("CON_NAME", ""))
    return {"result": {"rows": snap, "count": len(snap)}, "raw": snap}


# --- F02: HANA 용량 히스토리 조회 (원천: HDB_SIZE_HISTORY, A4H 실측) ---
def f02_hdb_size_history(conn, *, date_from="", date_to="", rowcount=200):
    """HANA 용량 히스토리. Args: date_from/date_to(DATS YYYYMMDD, 선택), rowcount(기본 200).
    Returns: {"rows": [...], "count": n}}"""
    where = []
    if date_from:
        where.append(f"COLLECT_DATE >= '{date_from}'")
    if date_to:
        where.append(f"COLLECT_DATE <= '{date_to}'")
    rows = rfc_read_full(conn, "HDB_SIZE_HISTORY", HDB_FIELDS,
                         where=" AND ".join(where) if where else "")
    rows = sorted(rows, key=lambda r: (r.get("CON_NAME", ""), r.get("COLLECT_DATE", "")))
    n = int(rowcount) if str(rowcount).isdigit() else 200
    rows = rows[:n]
    return {"result": {"rows": rows, "count": len(rows)}, "raw": rows}


# --- F03: 테이블별 용량 TOP (trial 미지원) ---
def f03_table_sizes(conn, **kwargs):
    raise NotImplementedError("DB02 F03: 테이블별 용량 테이블이 A4H trial에 없음 (분석서 9장).")


TOOLS = [
    {"id": "F01", "name": "f01_db_overview", "description": "DB02 HANA 용량 최신 스냅샷 (HDB_SIZE_HISTORY)",
     "input_schema": {"type": "object", "properties": {}, "required": []},
     "func": "f01_db_overview"},
    {"id": "F02", "name": "f02_hdb_size_history", "description": "DB02 HANA 용량 히스토리 (HDB_SIZE_HISTORY)",
     "input_schema": {"type": "object",
        "properties": {
            "date_from": {"type": "string", "description": "DATS YYYYMMDD, 선택"},
            "date_to": {"type": "string", "description": "DATS YYYYMMDD, 선택"},
            "rowcount": {"type": "integer", "description": "최대 행수, 기본 200"}},
        "required": []},
     "func": "f02_hdb_size_history"},
    {"id": "F03", "name": "f03_table_sizes", "description": "DB02 테이블별 용량 TOP (trial 미지원)",
     "input_schema": {"type": "object", "properties": {}, "required": []},
     "func": "f03_table_sizes"},
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
    # 사용법: python sap_tcode_db02.py A4H F01 --params '{}'
    system = sys.argv[1] if len(sys.argv) > 1 else SYSTEM
    tool = sys.argv[2] if len(sys.argv) > 2 else "F01"
    params = {}
    if "--params" in sys.argv:
        params = json.loads(sys.argv[sys.argv.index("--params") + 1])
    print(json.dumps(call_tool(tool, system, **params), ensure_ascii=False, default=str)[:2000])
