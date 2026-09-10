"""
SAP 월간보고 (시스템 통계, HANA DB 전용) - RFC/BAPI + Python(pyrfc)
대상 3종: 1) 유저수(활성/잠금/다이얼로그) 2) 티코드 사용량 TOP 3) DB용량 증감

아래 사용된 FM/테이블은 전부 실존 객체만 사용:
- FM: RFC_READ_TABLE, BAPI_USER_GETLIST, BAPI_USER_GET_DETAIL,
      DDIF_FIELDINFO_GET,
      SWNC_GET_WORKLOAD_STATISTIC (FG SCSM_GLOB_SYSTEM, RFC 실증 예제 존재),
      SWNC_COLLECTOR_GET_AGGREGATES / SWNC_COLLECTOR_GET_DIRECTORY (FG SCSM_COLLECTOR),
      SWNC_GET_AGGREGATES_FRAME / SWNC_GET_DIRECTORY_FRAME (Note 1053634, S/4 대응)
- TABLE: USR02, HDB_SIZE_HISTORY (SDBA_HDB, CON_NAME+COLLECT_DATE key),
         DB_SIZE_HISTORY_FOR_COCKPIT (DBACOCKPIT 히스토리), TBTCO (배치잡 확인)

pip install pyrfc pandas openpyxl
NW RFC SDK: https://support.sap.com/nwrfcsdk
"""

import textwrap
from datetime import date, datetime, timedelta
from pyrfc import Connection

# ------------------------------------------------------------------
# 0-1. 시스템별 접속정보 (sap_systems.json) + name/SID 접속
# ------------------------------------------------------------------
CONFIG_DEFAULT = "sap_systems.json"


def _expand_env(value):
    """${VAR} 형태 환경변수 참조 치환."""
    import os
    import re
    if not isinstance(value, str):
        return value
    return re.sub(r"\$\{([^}]+)\}", lambda m: os.environ.get(m.group(1), ""), value)


def load_systems(path=CONFIG_DEFAULT):
    """sap_systems.json 로드. returns {key: entry} (name/SID 대소문자 무시)."""
    import json
    import os
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    index = {}
    for entry in data.get("systems", []):
        entry = {k: _expand_env(v) for k, v in entry.items()}
        for key in (entry.get("name", ""), entry.get("sid", "")):
            if key:
                index[key.upper()] = entry
    return index


def find_system(name_or_sid, path=CONFIG_DEFAULT):
    """name 또는 SID로 항목 조회. 없으면 사용 가능한 목록과 함께 에러."""
    index = load_systems(path)
    hit = index.get((name_or_sid or "").upper())
    if not hit:
        avail = sorted({e.get("name", "") + "/" + e.get("sid", "")
                        for e in index.values()})
        raise KeyError(f"시스템 '{name_or_sid}' 없음. 사용 가능: {avail}")
    missing = [k for k in ("ashost", "sysnr", "client", "user", "passwd")
               if not hit.get(k)]
    if missing:
        raise ValueError(f"[{hit.get('name')}] sap_systems.json 미입력 항목: {missing}")
    return hit


def get_connection_by_name(name_or_sid, path=CONFIG_DEFAULT):
    """sap_systems.json에서 name/SID 찾아 RFC 커넥션 생성.

    예: conn = get_connection_by_name("PRD")
        conn = get_connection_by_name("PED")  # SID로도 가능
    비밀번호는 ${SAP_PW_PRD} 처럼 환경변수 참조 권장.

    잠김 방지: 직전 시도가 비밀번호 오류(auth_failed)였고, 그 이후
    접속정보가 바뀌지 않았으면(cred_hash 동일) 재시도하지 않고 에러.
    sap_systems.json(또는 환경변수) 수정 후 다시 시도하세요.
    """
    s = find_system(name_or_sid, path)
    key = (s.get("name") or s.get("sid") or name_or_sid).upper()
    fp = _cred_fingerprint(s)
    st = _load_state().get(key)
    if st and st.get("status") == "auth_failed" and st.get("cred_hash") == fp:
        raise RuntimeError(
            f"[{s.get('name')}] 직전 접속이 비밀번호 오류로 실패했습니다 "
            f"(마지막 시도: {st.get('last_attempt')}). "
            f"SAP 계정 잠김 방지를 위해 접속정보가 수정되기 전에는 재시도하지 않습니다. "
            f"sap_systems.json의 id/pw(또는 참조 환경변수)를 수정 후 다시 실행하세요.")
    try:
        conn = Connection(ashost=s["ashost"], sysnr=s["sysnr"],
                          client=s["client"], user=s["user"],
                          passwd=s["passwd"], lang=s.get("lang", "KO"))
    except Exception as e:  # noqa: BLE001 - 상태 기록 후 재발생
        _save_state(key, s, _classify_error(e), fp, e)
        raise
    _save_state(key, s, "ok", fp, None)
    return conn


# ------------------------------------------------------------------
# 0-2. 접속 상태 기록 (마지막 접속시간/결과 + 비밀번호 오류 시 재시도 차단)
# ------------------------------------------------------------------
STATE_DEFAULT = "sap_connection_state.json"


def _cred_fingerprint(entry):
    """접속정보 지문. 평문 저장 없이 변경 여부만 판단 (sha256)."""
    import hashlib
    raw = "|".join(str(entry.get(k, "")) for k in
                   ("ashost", "sysnr", "client", "user", "passwd"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _state_path():
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        STATE_DEFAULT)


def _load_state():
    import json
    import os
    p = _state_path()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(key, entry, status, cred_hash, err):
    import json
    data = _load_state()
    data[key] = {"name": entry.get("name"), "sid": entry.get("sid"),
                 "last_attempt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "status": status,
                 "detail": (str(err)[:200] if err is not None else "접속 성공"),
                 "cred_hash": cred_hash}
    with open(_state_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _classify_error(err):
    """pyrfc 예외 분류: LogonError=비밀번호 오류, CommunicationError=네트워크."""
    names = " ".join(c.__name__ for c in type(err).__mro__).lower()
    if "logon" in names:
        return "auth_failed"
    if "communication" in names:
        return "comm_failed"
    return "error"


def last_status(name_or_sid=None):
    """마지막 접속시간/상태 조회. 인자 없으면 전체 반환.

    예: last_status("PRD")
        -> {"name": "PRD", "last_attempt": "2026-09-05 10:01:22",
            "status": "auth_failed", "detail": "..."}
    status: ok | auth_failed | comm_failed | error
    """
    data = _load_state()
    if name_or_sid is None:
        return data
    for rec in data.values():
        if name_or_sid.upper() in (rec.get("name", "").upper(),
                                   rec.get("sid", "").upper()):
            return rec
    return {"status": "never", "detail": "접속 기록 없음"}

# ------------------------------------------------------------------
# 0. 접속 + 공용 래퍼
# ------------------------------------------------------------------
def get_connection(ashost, sysnr, client, user, passwd, lang="KO"):
    """SAP RFC 커넥션 생성."""
    return Connection(ashost=ashost, sysnr=sysnr, client=client,
                      user=user, passwd=passwd, lang=lang)


def _split_options(where):
    """RFC_READ_TABLE OPTIONS는 한 줄 72자 제한 → 자동 분할."""
    if not where:
        return []
    return [{"TEXT": chunk} for chunk in textwrap.wrap(where, 72)]


def rfc_read_table(conn, table, fields, where="", rowcount=0,
                   rowskips=0, delimiter="|"):
    """RFC_READ_TABLE 래퍼. 대량은 ROWSKIPS 루프 호출."""
    return conn.call("RFC_READ_TABLE",
                     QUERY_TABLE=table,
                     DELIMITER=delimiter,
                     FIELDS=[{"FIELDNAME": f} for f in fields],
                     OPTIONS=_split_options(where),
                     ROWCOUNT=rowcount,
                     ROWSKIPS=rowskips)


def rfc_read_full(conn, table, fields, where="", delimiter="|", batch=5000):
    """전체 건수 페이징 읽기."""
    out, skip = [], 0
    while True:
        res = rfc_read_table(conn, table, fields, where,
                             rowcount=batch, rowskips=skip,
                             delimiter=delimiter)
        rows = [dict(zip(fields, [c.strip() for c in r["WA"].split(delimiter)]))
                for r in res["DATA"]]
        out.extend(rows)
        if len(res["DATA"]) < batch:
            break
        skip += batch
    return out


def table_fields(conn, table):
    """DDIF_FIELDINFO_GET: 테이블 필드 존재 확인용 (HANA 히스토리 테이블 점검)."""
    return conn.call("DDIF_FIELDINFO_GET", TABNAME=table, LANGU="K")


# ------------------------------------------------------------------
# 1. 유저수: 활성 / 잠금 / 다이얼로그
# 근거 테이블 USR02 (실존): BNAME, UFLAG, USTYP, TRDAT, GLTGV, GLTGB
#   UFLAG: 0=정상, 32=전역잠금, 64=로컬잠금, 128=오입력잠금, 192 등 조합
#   USTYP: A=Dialog, B=System, C=Communication, S=Service, L=Reference
#   TRDAT: 최종 로그온 일자 (YYYYMMDD)
# ------------------------------------------------------------------
USTYP_MAP = {"A": "dialog", "B": "system", "C": "communication",
             "S": "service", "L": "reference"}
USTYP_COL = {"A": "dialog_A", "B": "system_B", "C": "communication_C",
             "S": "service_S", "L": "reference_L"}


def get_user_stats(conn, active_days=90):
    """USR02 전수 집계. returns dict."""
    cutoff = (date.today() - timedelta(days=active_days)).strftime("%Y%m%d")
    rows = rfc_read_full(conn, "USR02",
                         ["BNAME", "UFLAG", "USTYP", "TRDAT"])
    stats = {"total": 0, "active_uflag0": 0,
             "locked_local64": 0, "locked_global32": 0,
             "locked_wrong_logon128": 0, "locked_other": 0,
             "dialog_A": 0, "system_B": 0, "communication_C": 0,
             "service_S": 0, "reference_L": 0,
             f"logon_last_{active_days}d": 0}
    for r in rows:
        if r["BNAME"].startswith("!") or r["BNAME"].startswith("#"):
            continue
        stats["total"] += 1
        try:
            flag = int(r["UFLAG"])
        except ValueError:
            flag = -1
        if flag == 0:
            stats["active_uflag0"] += 1
        elif flag == 64:
            stats["locked_local64"] += 1
        elif flag == 32:
            stats["locked_global32"] += 1
        elif flag == 128:
            stats["locked_wrong_logon128"] += 1
        else:
            stats["locked_other"] += 1
        col = USTYP_COL.get(r["USTYP"])
        if col:
            stats[col] += 1
        if r["TRDAT"] and r["TRDAT"] >= cutoff and r["TRDAT"] != "00000000":
            stats[f"logon_last_{active_days}d"] += 1
    return stats


def get_user_list_by_lock(conn, lock="locked"):
    """BAPI_USER_GETLIST (실존) 교차확인용. lock: locked|unlocked|wrong_logon."""
    if lock == "unlocked":
        sel = [{"PARAMETER": "LOGONDATA", "FIELD": "UFLAG",
                "SIGN": "I", "OPTION": "EQ", "LOW": "0"}]
    elif lock == "wrong_logon":
        sel = [{"PARAMETER": "ISLOCKED", "FIELD": "WRNG_LOGON",
                "SIGN": "I", "OPTION": "EQ", "LOW": "L"}]
    else:
        sel = [{"PARAMETER": "LOGONDATA", "FIELD": "UFLAG",
                "SIGN": "I", "OPTION": "NE", "LOW": "0"}]
    return conn.call("BAPI_USER_GETLIST", MAX_ROWS=0,
                     WITH_USERNAME="X", SELECTION_RANGE=sel)


def get_user_detail(conn, username):
    """BAPI_USER_GET_DETAIL (실존). 개별 유저 USTYP/잠금 교차확인."""
    return conn.call("BAPI_USER_GET_DETAIL", USERNAME=username)


# ------------------------------------------------------------------
# 2. 티코드 사용량 TOP — ST03N 월간 집계 (RFC 실증 FM 우선)
# [1순위] SWNC_GET_WORKLOAD_STATISTIC (FG SCSM_GLOB_SYSTEM, Remote-Enabled)
#   IMPORTING: SYSTEMID, INSTANCE='TOTAL', PERIODTYPE='M',
#              PERIODSTRT='YYYYMM01'
#   TABLES: HITLIST_RESPTIME (TCODE/REPORT/DBCALLS/RESPTI/PROCTI/QUEUETI/CPUTI),
#           HITLIST_DATABASE — RFC 호출 실증 코드 존재 (SAP Community)
# [2순위] SWNC_COLLECTOR_GET_AGGREGATES (FG SCSM_COLLECTOR)
#   COMPONENT='TOTAL', PERIODTYPE='M', PERIODSTRT, TABLES TASKTYPE/USERTCODE
#   ENTRY_ID=티코드, COUNT=Dialog Steps
# [S/4 최신] SWNC_GET_AGGREGATES_FRAME / SWNC_GET_DIRECTORY_FRAME (Note 1053634)
# ------------------------------------------------------------------
def get_tcode_top(conn, systemid, year_month="202601", top_n=20,
                  by="resptime"):
    """월간 티코드 TOP N. by='resptime'|'database'.

    HITLIST_RESPTIME 행 예: {ACCOUNT, TCODE, REPORT, DBCALLS, RESPTI,
                             PROCTI, QUEUETI, CPUTI}
    """
    res = conn.call("SWNC_GET_WORKLOAD_STATISTIC",
                    SYSTEMID=systemid,
                    INSTANCE="TOTAL",
                    PERIODTYPE="M",
                    PERIODSTRT=f"{year_month}01")
    table = "HITLIST_RESPTIME" if by == "resptime" else "HITLIST_DATABASE"
    rows = res.get(table, [])[:top_n]
    return [{"rank": i + 1, "tcode": r.get("TCODE", "").strip(),
             "report": r.get("REPORT", "").strip(),
             "user": r.get("ACCOUNT", "").strip(),
             "dbcalls": r.get("DBCALLS"), "respti": r.get("RESPTI"),
             "procti": r.get("PROCTI"), "queueti": r.get("QUEUETI"),
             "cputi": r.get("CPUTI")}
            for i, r in enumerate(rows)]


def get_tcode_top_aggregates(conn, year_month="202601", top_n=20):
    """SWNC_COLLECTOR_GET_AGGREGATES 버전 (TASKTYPE.ENTRY_ID 기준)."""
    res = conn.call("SWNC_COLLECTOR_GET_AGGREGATES",
                    COMPONENT="TOTAL",
                    PERIODTYPE="M",
                    PERIODSTRT=f"{year_month}01",
                    SUMMARY_ONLY="",
                    FACTOR=1000)
    task = sorted(res.get("TASKTYPE", []),
                  key=lambda r: int(r.get("COUNT", 0) or 0),
                  reverse=True)[:top_n]
    return [{"tcode": r.get("ENTRY_ID", "").strip(),
             "tasktype": r.get("TASKTYPE"),
             "count": int(r.get("COUNT", 0) or 0),
             "respti_ms": r.get("RESPTI"), "cputi_ms": r.get("CPUTI"),
             "dbcalls": r.get("DBCALLS")} for r in task]


def list_workload_periods(conn):
    """SWNC_COLLECTOR_GET_DIRECTORY (실존): 수집된 집계기간 목록."""
    return conn.call("SWNC_COLLECTOR_GET_DIRECTORY")


# ------------------------------------------------------------------
# 3. HANA DB 용량 증감 — 실존 테이블 2종 (DB02/DBACOCKPIT 화면과 동일 원천)
# [1순위] HDB_SIZE_HISTORY (패키지 SDBA_HDB, 실존 테이블)
#   KEY: CON_NAME + COLLECT_DATE
#   값: MEMORY_USED, DISK_USED_DATA, DISK_USED_LOG, DISK_USED_TRACE
#   원천: DBACOCKPIT > System Information > DB Size History
# [2순위] DB_SIZE_HISTORY_FOR_COCKPIT (KBA 3396860/3121227 언급 실존 테이블)
# 수집 잡: SAP_COLLECTOR_FOR_PERFMONITOR (미수집 시 히스토리 비어있음, KBA 2453269)
# ------------------------------------------------------------------
HDB_FIELDS = ["CON_NAME", "COLLECT_DATE", "MEMORY_USED",
              "DISK_USED_DATA", "DISK_USED_LOG", "DISK_USED_TRACE"]


def check_hana_collector(conn):
    """수집잡 스케줄 확인 (TBTCO 실존 테이블). 비어있으면 DBACOCKPIT 히스토리 없음."""
    rows = rfc_read_full(
        conn, "TBTCO", ["JOBNAME", "SDLSTRTDT", "SDLSTRTTM", "STATUS"],
        where="JOBNAME = 'SAP_COLLECTOR_FOR_PERFMONITOR'")
    return rows


def get_hana_db_growth(conn, con_name="", months=6):
    """HDB_SIZE_HISTORY 월말 스냅샷 → 전월대비 증감.

    returns [{collect_date, memory_used, disk_data, disk_log, disk_trace,
              disk_total, growth_total, growth_data}, ...] (오름차순)
    단위: 테이블 원시값 그대로 (DBACOCKPIT 화면 단위와 대조, 보통 MB/GB).
    """
    where = f"CON_NAME = '{con_name}'" if con_name else ""
    rows = rfc_read_full(conn, "HDB_SIZE_HISTORY", HDB_FIELDS, where=where)
    if not rows:
        return {"error": "HDB_SIZE_HISTORY empty",
                "hint": "DBACOCKPIT>DB Size History 확인 + "
                        "SAP_COLLECTOR_FOR_PERFMONITOR 스케줄 확인(KBA 2453269). "
                        "대체: get_hana_db_growth_cockpit()"}
    # 월별 마지막 수집일만 남기기
    by_month = {}
    for r in rows:
        ym = r["COLLECT_DATE"][:6]
        if ym not in by_month or r["COLLECT_DATE"] > by_month[ym]["COLLECT_DATE"]:
            by_month[ym] = r
    hist = [by_month[k] for k in sorted(by_month)[-months:]]

    def f(x):
        try:
            return float(str(x).replace(",", ""))
        except ValueError:
            return None

    out = []
    prev_total = None
    for r in hist:
        vals = {k.lower(): f(r[k]) for k in HDB_FIELDS[2:]}
        total = sum(v for v in [vals.get("disk_used_data"),
                                vals.get("disk_used_log"),
                                vals.get("disk_used_trace")] if v is not None)
        row = {"collect_date": r["COLLECT_DATE"],
               "memory_used": vals.get("memory_used"),
               "disk_data": vals.get("disk_used_data"),
               "disk_log": vals.get("disk_used_log"),
               "disk_trace": vals.get("disk_used_trace"),
               "disk_total": total,
               "growth_total": (total - prev_total)
               if prev_total is not None else 0.0}
        prev_total = total
        out.append(row)
    return out


def get_hana_db_growth_cockpit(conn, months=6):
    """대체 원천: DB_SIZE_HISTORY_FOR_COCKPIT (필드는 DDIF_FIELDINFO_GET로 확인 후 사용)."""
    info = table_fields(conn, "DB_SIZE_HISTORY_FOR_COCKPIT")
    known = [f["FIELDNAME"] for f in info["FIELDINFO"]]
    fields = [c for c in ["DBSYS", "COLLECT_DATE", "DB_SIZE", "DB_USED",
                          "DB_FREE", "MEMORY_USED"] if c in known] or known[:6]
    return rfc_read_full(conn, "DB_SIZE_HISTORY_FOR_COCKPIT", fields)


# ------------------------------------------------------------------
# 4. 월간 오케스트레이터 + 엑셀 출력
# ------------------------------------------------------------------
def monthly_report(conn, systemid, year_month, con_name=""):
    """3종 묶음 추출."""
    users = get_user_stats(conn)
    tcodes = get_tcode_top(conn, systemid, year_month)
    db = get_hana_db_growth(conn, con_name)
    jobs = check_hana_collector(conn)
    return {"year_month": year_month, "users": users,
            "tcode_top": tcodes, "db_growth": db,
            "collector_jobs": jobs}


def monthly_report_by_name(name_or_sid, year_month, con_name=""):
    """name/SID만 주면 접속→3종 추출→접속종료까지 한 번에."""
    conn = get_connection_by_name(name_or_sid)
    try:
        systemid = find_system(name_or_sid).get("sid") or name_or_sid
        return monthly_report(conn, systemid, year_month, con_name)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def to_excel(report, path=None):
    """pandas로 시트 4개 저장."""
    import pandas as pd
    path = path or f"SAP_월간보고_HANA_{report['year_month']}.xlsx"
    with pd.ExcelWriter(path) as w:
        pd.DataFrame([report["users"]]).T.rename(
            columns={0: "count"}).to_excel(w, sheet_name="1_유저수")
        pd.DataFrame(report["tcode_top"]).to_excel(
            w, sheet_name="2_티코드TOP", index=False)
        d = report["db_growth"]
        pd.DataFrame(d if isinstance(d, list) else [d]).to_excel(
            w, sheet_name="3_DB용량", index=False)
        pd.DataFrame(report["collector_jobs"] or [{}]).to_excel(
            w, sheet_name="4_수집잡", index=False)
    return path


if __name__ == "__main__":
    import sys
    # 사용법: python sap_monthly_report.py PRD [YYYYMM]
    if len(sys.argv) >= 2:
        target = sys.argv[1]
        ym = sys.argv[2] if len(sys.argv) >= 3 else datetime.now().strftime("%Y%m")
        rep = monthly_report_by_name(target, ym)
        print("엑셀 저장:", to_excel(rep))
    else:
        ym = datetime.now().strftime("%Y%m")
        print("사용법: python sap_monthly_report.py <name 또는 SID> [YYYYMM]")
        print(f"  예: python sap_monthly_report.py PRD {ym}")
        print("  또는 코드에서:")
        print('    rep = monthly_report_by_name("PRD", "202601")')
        print("사전 점검(SE37/RFC): BAPI_USER_GETLIST, SWNC_GET_WORKLOAD_STATISTIC,")
        print("  SWNC_COLLECTOR_GET_DIRECTORY, DDIF_FIELDINFO_GET + 테이블")
        print("  HDB_SIZE_HISTORY / DB_SIZE_HISTORY_FOR_COCKPIT 읽기 권한(S_TABU_NAM).")
