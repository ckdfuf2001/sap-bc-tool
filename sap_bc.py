"""SAP BC 통합 CLI (CLI-first 단일 진입점).

개별 모듈(python sap_tcode_su01.py ...)이 늘어나도 사용법은 여기서 통일한다.
SAP 접속 없이 동작하는 명령(list/usage/registry/check/skill-sync)은
import 없이 AST로 파싱하므로 pyrfc·sap_systems.json 없이 쓸 수 있다.
SAP 호출이 필요한 call만 실제 import·접속한다.

사용법:
    python sap_bc.py list [--json]
    python sap_bc.py usage <TCODE|모듈|기능ID|함수명>
    python sap_bc.py call <SYSTEM> <기능ID|함수명> --params '{...}'
    python sap_bc.py registry            # registry.json 재생성
    python sap_bc.py check               # 신규 모듈 계약 검사 (등록 게이트)
    python sap_bc.py skill-sync          # registry + SKILL.md 카운트 동기화
"""
import ast
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(ROOT, ".opencode", "skills", "sap-bc-usage", "registry.json")
USAGE_SKILL = os.path.join(ROOT, ".opencode", "skills", "sap-bc-usage", "SKILL.md")

REQUIRED_TOOL_KEYS = ("id", "name", "description", "input_schema", "func")


def _parse_module(path):
    """단일 sap_tcode_*.py를 AST로 파싱. returns dict(module, system, tcode, tools, funcs, errors)."""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    system = tcode, tools = None, None
    funcs = set()
    has_get_tool_defs = has_call_tool = False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs.add(node.name)
            if node.name == "get_tool_defs":
                has_get_tool_defs = True
            elif node.name == "call_tool":
                has_call_tool = True
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            tid = getattr(node.targets[0], "id", "")
            if tid in ("SYSTEM", "TCODE"):
                try:
                    val = ast.literal_eval(node.value)
                    if tid == "SYSTEM":
                        system = val
                    else:
                        tcode = val
                except Exception:
                    pass
            elif tid == "TOOLS":
                try:
                    tools = ast.literal_eval(node.value)
                except Exception as e:
                    tools = [{"parse_error": str(e)[:200]}]
    return {"module": os.path.basename(path), "system": system, "tcode": tcode,
            "tools": tools or [], "funcs": sorted(funcs),
            "has_get_tool_defs": has_get_tool_defs, "has_call_tool": has_call_tool}


def discover():
    """전 모듈 파싱 결과 리스트 (tcode 순 정렬)."""
    mods = [_parse_module(p) for p in sorted(glob.glob(os.path.join(ROOT, "sap_tcode_*.py")))]
    mods.sort(key=lambda m: (m["tcode"] or "", m["module"]))
    return mods


def find_tool(mods, query):
    """TCODE/모듈/ID/함수명으로 도구 검색. returns (mod, tool) 또는 (None, None)."""
    q = (query or "").upper()
    for m in mods:
        if q in ((m["tcode"] or "").upper(), m["module"].upper(),
                 m["module"].replace(".PY", "").upper()):
            return m, None  # 모듈 매칭
        for t in m["tools"]:
            if q in (str(t.get("id", "")).upper(), str(t.get("name", "")).upper()):
                return m, t
    return None, None


def _example_params(schema):
    """input_schema에서 복붙용 예시 params 생성 (required 우선)."""
    props = (schema or {}).get("properties", {}) or {}
    required = set((schema or {}).get("required", []) or [])
    ex = {}
    for k in list(required) + [k for k in props if k not in required]:
        typ = (props.get(k) or {}).get("type", "string")
        ex[k] = {"string": "<값>", "integer": 0, "boolean": False,
                 "array": [], "object": {}}.get(typ, "<값>")
    return ex


def cmd_list(as_json=False):
    mods = discover()
    total = sum(len(m["tools"]) for m in mods)
    if as_json:
        print(json.dumps({"modules": mods, "module_count": len(mods),
                           "tool_count": total}, ensure_ascii=False, indent=1, default=str))
        return
    print(f"모듈 {len(mods)}개 · 기능 {total}개 (원천: sap_tcode_*.py TOOLS)\n")
    for m in mods:
        print(f"[{m['tcode']}] {m['module']} ({len(m['tools'])}건)")
        for t in m["tools"]:
            print(f"  {t.get('id', '?'):6} {t.get('name', '?'):24} {t.get('description', '')}")
        print()


def cmd_usage(query):
    mods = discover()
    mod, tool = find_tool(mods, query)
    if mod is None:
        print(f"못 찾음: {query}\n힌트: python sap_bc.py list  로 전체 목록 확인")
        sys.exit(1)
    if tool is None:  # 모듈 조회
        print(f"[{mod['tcode']}] {mod['module']} - 기능 {len(mod['tools'])}건\n")
        for t in mod["tools"]:
            req = ", ".join((t.get("input_schema") or {}).get("required", []) or []) or "(필수 없음)"
            print(f"- {t.get('id')} {t.get('name')}: {t.get('description')} [필수: {req}]")
        print(f"\n상세: python sap_bc.py usage <기능ID|함수명>  (예: python sap_bc.py usage {mod['tools'][0].get('id') if mod['tools'] else 'F01'})")
        return
    schema = tool.get("input_schema") or {}
    ex = _example_params(schema)
    print(f"[{mod['tcode']}] {tool.get('id')} {tool.get('name')}")
    print(f"설명: {tool.get('description')}")
    print(f"모듈: {mod['module']}")
    print(f"스키마: {json.dumps(schema, ensure_ascii=False)}")
    print(f"\nCLI 예:\n  python sap_bc.py call A4H {tool.get('id')} --params '{json.dumps(ex, ensure_ascii=False)}'")
    print(f"  python {mod['module']} A4H {tool.get('id')} --params '{json.dumps(ex, ensure_ascii=False)}'")
    print(f"\n파이썬 예:\n  from {mod['module'].replace('.py', '')} import call_tool"
          f"\n  call_tool({tool.get('id')!r}, 'A4H', **{json.dumps(ex, ensure_ascii=False)})")


def cmd_call(system, tool_id, params):
    sys.path.insert(0, ROOT)
    mods = discover()
    mod, tool = find_tool(mods, tool_id)
    if mod is None:
        print(f"못 찾음: {tool_id}  (python sap_bc.py list 로 확인)")
        sys.exit(1)
    target = tool.get("name") if tool else tool_id
    module = __import__(mod["module"].replace(".py", ""))
    print(json.dumps(module.call_tool(target, system, **params),
                     ensure_ascii=False, default=str)[:4000])


def cmd_registry():
    import runpy
    runpy.run_path(os.path.join(ROOT, "tools", "build_registry.py"), run_name="__main__")


def cmd_check():
    """신규 등록 게이트: 계약 위반 모듈을 실패로 보고. exit 1이면 등록 불가."""
    mods = discover()
    ok_all = True
    for m in mods:
        errs = []
        if not m["tcode"]:
            errs.append("TCODE 상수 없음")
        if not m["has_get_tool_defs"]:
            errs.append("get_tool_defs 없음")
        if not m["has_call_tool"]:
            errs.append("call_tool 없음")
        for t in m["tools"]:
            if isinstance(t, dict) and "parse_error" in t:
                errs.append(f"TOOLS 파싱 실패: {t['parse_error']}")
                continue
            missing = [k for k in REQUIRED_TOOL_KEYS if k not in t]
            if missing:
                errs.append(f"{t.get('id', '?')}: 키 누락 {missing}")
            elif t.get("func") not in m["funcs"]:
                errs.append(f"{t.get('id')}: func {t.get('func')} 미정의")
            schema = t.get("input_schema") or {}
            if not isinstance(schema.get("properties"), dict):
                errs.append(f"{t.get('id')}: input_schema.properties 비정상")
        status = "OK " if not errs else "FAIL"
        if errs:
            ok_all = False
        print(f"[{status}] {m['tcode']} {m['module']} ({len(m['tools'])}건)")
        for e in errs:
            print(f"       - {e}")
    print("\n전체 통과" if ok_all else "\n실패 있음 → 등록 불가 (sap-tcode-to-python 스킬 규칙 확인)")
    sys.exit(0 if ok_all else 1)


def cmd_skill_sync():
    """registry 재생성 + SKILL.md 카운트 동기화 (등록 시 1회)."""
    cmd_registry()
    data = json.load(open(REGISTRY, encoding="utf-8"))
    mc, tc = data["module_count"], data["tool_count"]
    if os.path.exists(USAGE_SKILL):
        import re
        src = open(USAGE_SKILL, encoding="utf-8").read()
        new = re.sub(r"\(\d+ modules?, \d+ tools?\)", f"({mc} modules, {tc} tools)", src)
        new = re.sub(r"\d+ modules? / \d+ tools?", f"{mc} modules / {tc} tools", new)
        if new != src:
            open(USAGE_SKILL, "w", encoding="utf-8").write(new)
            print(f"SKILL.md 카운트 동기화: {mc} modules, {tc} tools")
        else:
            print(f"SKILL.md 카운트 이미 일치: {mc} modules, {tc} tools")
    print(f"완료: {mc} modules, {tc} tools")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "list":
        cmd_list(as_json="--json" in sys.argv)
    elif cmd == "usage":
        if len(sys.argv) < 3:
            print("사용법: python sap_bc.py usage <TCODE|모듈|기능ID|함수명>")
            sys.exit(1)
        cmd_usage(sys.argv[2])
    elif cmd == "call":
        if len(sys.argv) < 4:
            print("사용법: python sap_bc.py call <SYSTEM> <기능ID|함수명> --params '{...}'")
            sys.exit(1)
        params = {}
        if "--params" in sys.argv:
            params = json.loads(sys.argv[sys.argv.index("--params") + 1])
        cmd_call(sys.argv[2], sys.argv[3], params)
    elif cmd == "registry":
        cmd_registry()
    elif cmd == "check":
        cmd_check()
    elif cmd == "skill-sync":
        cmd_skill_sync()
    else:
        print(f"알 수 없는 명령: {cmd}\n{__doc__}")
        sys.exit(1)
