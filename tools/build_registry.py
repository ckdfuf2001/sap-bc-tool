"""sap_tcode_*.py TOOLS 레지스트리 생성기 (sap-bc-usage 스킬용).

사용법: python tools/build_registry.py [--out .opencode/skills/sap-bc-usage/registry.json]
- 각 sap_tcode_<tcode>.py의 TOOLS 리스트를 AST로 파싱(func 제외)해 단일 JSON으로 합친다.
- import 없이 파싱하므로 pyrfc/SAP 접속 없이 동작한다.
- 새 프로그램 추가 후 반드시 실행해 registry.json을 갱신할 것 (sap-tcode-to-python 스킬 규칙).
"""
import ast
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def extract_tools(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    system = tcode = None
    tools = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
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
    return system, tcode, tools or []


def main():
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(
        ROOT, ".opencode", "skills", "sap-bc-usage", "registry.json")
    modules = []
    for f in sorted(glob.glob(os.path.join(ROOT, "sap_tcode_*.py"))):
        system, tcode, tools = extract_tools(f)
        fname = os.path.basename(f)
        for t in tools:
            t.setdefault("module", fname)
            t.setdefault("tcode", tcode)
            t.setdefault("system", system)
        modules.append({"module": fname, "system": system, "tcode": tcode,
                        "tool_count": len(tools), "tools": tools})
    total = sum(m["tool_count"] for m in modules)
    data = {"modules": modules, "module_count": len(modules), "tool_count": total}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=1)
    print(f"wrote {out}: {len(modules)} modules, {total} tools")


if __name__ == "__main__":
    main()
