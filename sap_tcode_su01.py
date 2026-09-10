"""SU01 (User Maintenance) RFC-only 재현. 분석서: docs/analysis/A4H_SU01.md
외부 MCP 래핑용: TOOLS[i] = {"id": 기능ID, "name": tool명,
  "description": ..., "input_schema": {...}} 와 동명 함수를 import해 쓰세요.

예 (FastMCP):
    from sap_tcode_su01 import TOOLS, call_tool
    import sap_tcode_su01 as m
    for t in TOOLS:
        mcp.add_tool(getattr(m, t["func"]), name=t["name"], description=t["description"])
"""
from sap_monthly_report import get_connection_by_name

SYSTEM = "A4H"  # find_system key (분석서 시스템과 동일)
TCODE = "SU01"


def _as_list(ret):
    """RETURN이 테이블(list) 또는 구조체(dict)로 오는 경우를 모두 리스트로 정규화."""
    if not ret:
        return []
    if isinstance(ret, dict):
        return [ret]
    return list(ret)


def _check_return(ret):
    """BAPIRET2 전건 검사. E/A 코드 있으면 예외 (원문 메시지 포함)."""
    errs = [r for r in _as_list(ret)
            if (r.get("TYPE") or "") in ("E", "A")]
    if errs:
        msgs = "; ".join(
            f"[{r.get('ID')}{r.get('NUMBER')}] {r.get('MESSAGE')}" for r in errs)
        raise RuntimeError(f"BAPI errors: {msgs}")
    return ret


def _commit(conn, wait="X"):
    conn.call("BAPI_TRANSACTION_COMMIT", WAIT=wait)


def _rollback(conn):
    try:
        conn.call("BAPI_TRANSACTION_ROLLBACK")
    except Exception:
        pass


# --- F01: 사용자 단건 조회 (원천: BAPI_USER_GET_DETAIL, R 실측) ---
def f01_get_detail(conn, *, username):
    """사용자 단건 조회. Args: username(CHAR12, 예 'DEVELOPER').
    Returns: {"logondata":..., "defaults":..., "address":..., "return":...}"""
    res = conn.call("BAPI_USER_GET_DETAIL", USERNAME=username)
    _check_return(res.get("RETURN"))
    res.pop("RETURN", None)
    return {"result": res, "raw": res}


# --- F02: 사용자 생성 (원천: BAPI_USER_CREATE, R 실측) ---
def f02_create(conn, *, username, logondata=None, password=None,
               defaults=None, address=None, company=None, commit=False):
    """사용자 생성. Args: username(CHAR12), logondata(BAPILOGOND dict, 선택),
    password(BAPIPWD dict, 선택. 예: {"BAPIPWD": "Test2026!a"} — 초기 비밀번호),
    defaults/address/company(선택 dict). 쓰기이므로 commit=True일 때만 COMMIT
    (기본 False면 ROLLBACK).
    Returns: {"return": [...]}"""
    params = {"USERNAME": username}
    if logondata is not None:
        params["LOGONDATA"] = logondata
    if password is not None:
        params["PASSWORD"] = password
    if defaults is not None:
        params["DEFAULTS"] = defaults
    if address is not None:
        params["ADDRESS"] = address
    if company is not None:
        params["COMPANY"] = company
    res = conn.call("BAPI_USER_CREATE", **params)
    try:
        _check_return(res.get("RETURN"))
    except Exception:
        _rollback(conn)
        raise
    if commit:
        _commit(conn)
    else:
        _rollback(conn)
    return {"result": {"committed": commit}, "raw": res.get("RETURN")}


# --- F03: 사용자 변경 (원천: BAPI_USER_CHANGE, R 실측) ---
def f03_change(conn, *, username, commit=False, **changes):
    """사용자 변경. Args: username + 변경 구조체(LOGONDATA 등)와 *_X 플래그 구조체
    (예: logondata={...}, logondatax={...})를 키워드로 전달.
    Returns: {"return": [...]} (commit 여부는 result.committed)"""
    params = {"USERNAME": username}
    params.update({k.upper(): v for k, v in changes.items()})
    res = conn.call("BAPI_USER_CHANGE", **params)
    try:
        _check_return(res.get("RETURN"))
    except Exception:
        _rollback(conn)
        raise
    if commit:
        _commit(conn)
    else:
        _rollback(conn)
    return {"result": {"committed": commit}, "raw": res.get("RETURN")}


# --- F04: 사용자 삭제 (원천: BAPI_USER_DELETE, R 실측) ---
def f04_delete(conn, *, username, commit=False):
    """사용자 삭제. Args: username(CHAR12). commit=True일 때만 COMMIT.
    Returns: {"return": [...]}}"""
    res = conn.call("BAPI_USER_DELETE", USERNAME=username)
    try:
        _check_return(res.get("RETURN"))
    except Exception:
        _rollback(conn)
        raise
    if commit:
        _commit(conn)
    else:
        _rollback(conn)
    return {"result": {"committed": commit}, "raw": res.get("RETURN")}


# --- F05: 사용자 목록 조회 (원천: BAPI_USER_GETLIST, R 실측) ---
def f05_getlist(conn, *, selection_range=None, max_rows=0):
    """사용자 목록 조회. Args: selection_range(BAPIUSSRNG 행 리스트, 선택.
    예: [{"PARAMETER":"LOGONDATA","FIELD":"UFLAG","SIGN":"I","OPTION":"EQ","LOW":"0"}]),
    max_rows(0=무제한). Returns: {"usernames": [...]}}"""
    params = {"MAX_ROWS": max_rows}
    if selection_range is not None:
        params["SELECTION_RANGE"] = selection_range
    res = conn.call("BAPI_USER_GETLIST", **params)
    _check_return(res.get("RETURN"))
    users = res.get("USERLIST") or res.get("USERNAMES") or []
    return {"result": {"usernames": users},
            "raw": users}


# --- F06: 존재 여부 체크 (원천: BAPI_USER_EXISTENCE_CHECK, R 실측) ---
def f06_existence_check(conn, *, username):
    """존재 여부 체크. Args: username(CHAR12).
    실측: 존재하면 RETURN이 비어있고, 없으면 TYPE=I NUMBER=124.
    Returns: {"exists": bool, "return": ...}"""
    res = conn.call("BAPI_USER_EXISTENCE_CHECK", USERNAME=username)
    rets = _as_list(res.get("RETURN"))
    missing = any(r.get("TYPE") == "I" and str(r.get("NUMBER")) == "124"
                  for r in rets)
    return {"result": {"exists": not missing}, "raw": res.get("RETURN")}


def _assign_delete(conn, fm, username, table_name, rows, commit):
    res = conn.call(fm, USERNAME=username, **{table_name: rows})
    try:
        _check_return(res.get("RETURN"))
    except Exception:
        _rollback(conn)
        raise
    if commit:
        _commit(conn)
    else:
        _rollback(conn)
    return {"result": {"committed": commit}, "raw": res.get("RETURN")}


# --- F07a: 롤 할당 (원천: BAPI_USER_ACTGROUPS_ASSIGN, R 실측) ---
def f07_actgroups_assign(conn, *, username, activitygroups, commit=False):
    """롤 할당. Args: username, activitygroups(BAPIACTV 행 리스트.
    예: [{"AGR_NAME":"SAP_ALL"}]). Returns: {"return": [...]}}"""
    return _assign_delete(conn, "BAPI_USER_ACTGROUPS_ASSIGN",
                          username, "ACTIVITYGROUPS", activitygroups, commit)


# --- F07b: 롤 삭제 (원천: BAPI_USER_ACTGROUPS_DELETE, R 실측) ---
def f07_actgroups_delete(conn, *, username, activitygroups, commit=False):
    """롤 삭제. Args는 f07_actgroups_assign과 동일."""
    return _assign_delete(conn, "BAPI_USER_ACTGROUPS_DELETE",
                          username, "ACTIVITYGROUPS", activitygroups, commit)


# --- F07c: 프로파일 할당 (원천: BAPI_USER_PROFILES_ASSIGN, R 실측) ---
def f07_profiles_assign(conn, *, username, profiles, commit=False):
    """프로파일 할당. Args: username, profiles(BAPIPROF 행 리스트.
    예: [{"PROFILE":"SAP_ALL"}]). Returns: {"return": [...]}}"""
    return _assign_delete(conn, "BAPI_USER_PROFILES_ASSIGN",
                          username, "PROFILES", profiles, commit)


# --- F07d: 프로파일 삭제 (원천: BAPI_USER_PROFILES_DELETE, R 실측) ---
def f07_profiles_delete(conn, *, username, profiles, commit=False):
    """프로파일 삭제. Args는 f07_profiles_assign과 동일."""
    return _assign_delete(conn, "BAPI_USER_PROFILES_DELETE",
                          username, "PROFILES", profiles, commit)


# --- F08: 초기 화면 스킵 직접 진입 (dynpro 전용 → 미지원) ---
def f08_direct_entry(conn, *, username=None, tcode_mode=1, su01_display=None):
    """SUID_IDENTITY_MAINT 직접 호출 자리. dynpro를 실행하므로 RFC-only로 재현 불가.
    F01~F07 BAPI로 우회할 것."""
    raise NotImplementedError(
        "다이얼로그 전용: SUID_IDENTITY_MAINT는 dynpro를 실행하므로 RFC로 재현 불가. "
        "F01~F07 BAPI를 사용하세요.")


# MCP 재사용 계약: 기능ID → 함수 매핑 (분석서 2장 순서 유지, F07은 a~d로 전개)
TOOLS = [
    {"id": "F01", "name": "f01_get_detail", "description": "SU01 사용자 단건 조회 (BAPI_USER_GET_DETAIL)",
     "input_schema": {"type": "object",
        "properties": {"username": {"type": "string", "description": "CHAR12, 예 DEVELOPER"}},
        "required": ["username"]},
     "func": "f01_get_detail"},
    {"id": "F02", "name": "f02_create", "description": "SU01 사용자 생성 (BAPI_USER_CREATE + COMMIT 옵션)",
     "input_schema": {"type": "object",
        "properties": {
            "username": {"type": "string", "description": "CHAR12"},
            "logondata": {"type": "object", "description": "BAPILOGOND, 선택"},
            "password": {"type": "object", "description": "BAPIPWD, 선택. 예 {\"BAPIPWD\": \"...\"}"},
            "defaults": {"type": "object", "description": "BAPIDEFAUL, 선택"},
            "address": {"type": "object", "description": "BAPIADDR3, 선택"},
            "company": {"type": "object", "description": "선택"},
            "commit": {"type": "boolean", "description": "True일 때만 COMMIT, 기본 False(ROLLBACK)"}},
        "required": ["username"]},
     "func": "f02_create"},
    {"id": "F03", "name": "f03_change", "description": "SU01 사용자 변경 (BAPI_USER_CHANGE + COMMIT 옵션)",
     "input_schema": {"type": "object",
        "properties": {
            "username": {"type": "string", "description": "CHAR12"},
            "commit": {"type": "boolean", "description": "True일 때만 COMMIT"}},
        "required": ["username"]},
     "func": "f03_change"},
    {"id": "F04", "name": "f04_delete", "description": "SU01 사용자 삭제 (BAPI_USER_DELETE + COMMIT 옵션)",
     "input_schema": {"type": "object",
        "properties": {
            "username": {"type": "string", "description": "CHAR12"},
            "commit": {"type": "boolean", "description": "True일 때만 COMMIT"}},
        "required": ["username"]},
     "func": "f04_delete"},
    {"id": "F05", "name": "f05_getlist", "description": "SU01 사용자 목록 조회 (BAPI_USER_GETLIST)",
     "input_schema": {"type": "object",
        "properties": {
            "selection_range": {"type": "array", "description": "BAPIUSSRNG 행 리스트, 선택"},
            "max_rows": {"type": "integer", "description": "0=무제한"}},
        "required": []},
     "func": "f05_getlist"},
    {"id": "F06", "name": "f06_existence_check", "description": "SU01 존재 여부 체크 (BAPI_USER_EXISTENCE_CHECK)",
     "input_schema": {"type": "object",
        "properties": {"username": {"type": "string", "description": "CHAR12"}},
        "required": ["username"]},
     "func": "f06_existence_check"},
    {"id": "F07a", "name": "f07_actgroups_assign", "description": "SU01 롤 할당 (BAPI_USER_ACTGROUPS_ASSIGN)",
     "input_schema": {"type": "object",
        "properties": {
            "username": {"type": "string", "description": "CHAR12"},
            "activitygroups": {"type": "array", "description": "BAPIACTV 행, 예 [{\"AGR_NAME\":\"SAP_ALL\"}]"},
            "commit": {"type": "boolean", "description": "True일 때만 COMMIT"}},
        "required": ["username", "activitygroups"]},
     "func": "f07_actgroups_assign"},
    {"id": "F07b", "name": "f07_actgroups_delete", "description": "SU01 롤 삭제 (BAPI_USER_ACTGROUPS_DELETE)",
     "input_schema": {"type": "object",
        "properties": {
            "username": {"type": "string", "description": "CHAR12"},
            "activitygroups": {"type": "array", "description": "BAPIACTV 행"},
            "commit": {"type": "boolean", "description": "True일 때만 COMMIT"}},
        "required": ["username", "activitygroups"]},
     "func": "f07_actgroups_delete"},
    {"id": "F07c", "name": "f07_profiles_assign", "description": "SU01 프로파일 할당 (BAPI_USER_PROFILES_ASSIGN)",
     "input_schema": {"type": "object",
        "properties": {
            "username": {"type": "string", "description": "CHAR12"},
            "profiles": {"type": "array", "description": "BAPIPROF 행, 예 [{\"PROFILE\":\"SAP_ALL\"}]"},
            "commit": {"type": "boolean", "description": "True일 때만 COMMIT"}},
        "required": ["username", "profiles"]},
     "func": "f07_profiles_assign"},
    {"id": "F07d", "name": "f07_profiles_delete", "description": "SU01 프로파일 삭제 (BAPI_USER_PROFILES_DELETE)",
     "input_schema": {"type": "object",
        "properties": {
            "username": {"type": "string", "description": "CHAR12"},
            "profiles": {"type": "array", "description": "BAPIPROF 행"},
            "commit": {"type": "boolean", "description": "True일 때만 COMMIT"}},
        "required": ["username", "profiles"]},
     "func": "f07_profiles_delete"},
    {"id": "F08", "name": "f08_direct_entry", "description": "SU01 초기 화면 스킵 진입 (dynpro 전용, 미지원)",
     "input_schema": {"type": "object",
        "properties": {
            "username": {"type": "string", "description": "I_USERNAME, 선택"},
            "tcode_mode": {"type": "integer", "description": "1=single, 10=mass, 3=own, 6=display"},
            "su01_display": {"type": "string", "description": "CHAR1, 선택"}},
        "required": []},
     "func": "f08_direct_entry"},
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
    # 사용법: python sap_tcode_su01.py A4H F01 --params '{"username": "DEVELOPER"}'
    system = sys.argv[1] if len(sys.argv) > 1 else SYSTEM
    tool = sys.argv[2] if len(sys.argv) > 2 else "F01"
    params = {}
    if "--params" in sys.argv:
        params = json.loads(sys.argv[sys.argv.index("--params") + 1])
    print(json.dumps(call_tool(tool, system, **params), ensure_ascii=False, default=str)[:2000])
