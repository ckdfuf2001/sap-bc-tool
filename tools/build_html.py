"""분석서 MD -> 오프라인 단일 HTML 변환기 (sap-tcode-analyze 산출물용).

사용법: python tools/build_html.py [docs/analysis]
- 입력 MD의 전체 섹션(1~9장)을 빠짐없이 HTML로 변환한다 (요약 금지).
- mermaid flowchart LR 블록은 CSS 박스+화살표 레인으로 자동 렌더링한다 (CDN 불필요).
- 테이블/코드펜스/리스트/인라인코드를 지원한다.
"""
import html
import os
import re
import sys

CSS = """body{font-family:'Malgun Gothic',sans-serif;max-width:1100px;margin:0 auto;padding:24px;color:#222}
h1{border-bottom:3px solid #0a6ebd;padding-bottom:8px}
h2{margin-top:36px;border-left:6px solid #0a6ebd;padding-left:10px}
h3{margin-top:24px;color:#0a6ebd}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border:1px solid #bbb;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#eaf3fb}
code{background:#f4f4f4;padding:1px 4px;font-size:13px}
pre{background:#f4f4f4;padding:12px;overflow-x:auto;font-size:13px}
pre code{background:none;padding:0}
.meta{background:#f7f9fc;border:1px solid #ddd;padding:12px 16px}
.diagram{background:#fafafa;border:1px solid #ccc;padding:18px;overflow-x:auto;margin:12px 0}
.lane{margin:14px 0}
.lane-title{font-weight:bold;margin-bottom:6px;color:#0a6ebd}
.flow{display:flex;align-items:stretch;min-width:900px}
.node{border:2px solid #0a6ebd;border-radius:8px;padding:8px 10px;background:#fff;font-size:13px;min-width:120px;max-width:200px}
.node small{color:#555}
.node.screen{border-color:#7b1fa2}
.node.fm{border-color:#2e7d32}
.node.tbl{border-color:#e65100}
.node.bapi{border-color:#00695c;background:#e0f2f1}
.node.dim{border-color:#999;border-style:dashed;color:#555}
.arrow{align-self:center;font-size:20px;color:#666;padding:0 6px;white-space:nowrap}
footer{margin-top:40px;font-size:12px;color:#777;border-top:1px solid #ccc;padding-top:8px}
a{color:#0a6ebd}"""


def inline(s):
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return s


def node_class(nid, label):
    l = (nid + " " + re.sub(r"<[^>]+>", " ", label)).upper()
    if l.startswith("S") and re.match(r"S\d", nid.upper()):
        return "screen"
    if "BAPI" in l:
        return "bapi"
    if re.search(r"\b(T|TUSR02|SNAP|TBTCO|BALHDR|BALDAT|RFCDES|USR02)\b", l) and "SCREEN" not in l and "CALL" not in l:
        return "tbl"
    if re.search(r"FM|FUNCTION|BAPI|ENQUEUE|TH_WPINFO|RFC_READ|DDIF|SALC_|SABP_|APPL_LOG|STFC_|COMMIT", l):
        return "fm"
    if "미포함" in label or "미확인" in label:
        return "dim"
    return "src"


def mermaid_to_html(block):
    nodes, edges, order = {}, [], []
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("flowchart"):
            continue
        line = re.sub(r"-.->", "-->", line)
        parts = re.split(r"\s*-->\s*", line)
        seq = []
        for p in parts:
            p = p.split("|")[0].strip()
            m = re.match(r"(\w+)\[\"(.*)\"\]|\b(\w+)$", p)
            if not m:
                continue
            nid = m.group(1) or m.group(3)
            label = (m.group(2) or nid).replace("\\n", "<br/>")
            if nid not in nodes:
                nodes[nid] = label
                order.append(nid)
            seq.append(nid)
        for a, b in zip(seq, seq[1:]):
            if (a, b) not in edges:
                edges.append((a, b))
    if not nodes:
        return "<pre>" + html.escape(block) + "</pre>"
    incoming = {n: 0 for n in nodes}
    for a, b in edges:
        incoming[b] += 1
    roots = [n for n in order if incoming[n] == 0] or order[:1]
    succ = {}
    for a, b in edges:
        succ.setdefault(a, []).append(b)
    paths = []

    def dfs(n, path, seen):
        path = path + [n]
        seen = seen | {n}
        if n not in succ:
            paths.append(path)
            return
        for s in succ[n]:
            if s in seen:
                paths.append(path + [s])
            else:
                dfs(s, path, seen)

    for r in roots:
        dfs(r, [], set())
    lanes = []
    for i, p in enumerate(paths):
        cells = []
        for nid in p:
            cls = node_class(nid, nodes[nid])
            cells.append(f'<div class="node {cls}">{nodes[nid]}</div>')
        lanes.append(f'<div class="lane"><div class="flow">'
                     + '<div class="arrow">&rarr;</div>'.join(cells) + "</div></div>")
    return '<div class="diagram">' + "".join(lanes) + "</div>"


def md_to_body(md):
    lines = md.splitlines()
    out, i, in_list, list_tag = [], 0, False, ""
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            lang = line[3:].strip()
            buf = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            if lang == "mermaid":
                out.append(mermaid_to_html("\n".join(buf)))
            else:
                out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            continue
        if line.startswith("### "):
            out.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            if in_list:
                out.append(f"</{list_tag}>")
                in_list = False
            out.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{inline(line[2:])}</h1>")
        elif re.match(r"^\|.*\|$", line) and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|$", lines[i + 1]):
            if in_list:
                out.append(f"</{list_tag}>")
                in_list = False
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows = ["<tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells) + "</tr>"]
            i += 2
            while i < len(lines) and re.match(r"^\|.*\|$", lines[i]):
                cells = [c.strip() for c in lines[i].strip("|").split("|")]
                rows.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
            out.append("<table>" + "".join(rows) + "</table>")
            continue
        elif re.match(r"^(\d+)\.\s+", line):
            if not in_list or list_tag != "ol":
                if in_list:
                    out.append(f"</{list_tag}>")
                out.append("<ol>")
                in_list, list_tag = True, "ol"
            out.append(f"<li>{inline(re.sub(r'^\d+\.\s+', '', line))}</li>")
        elif re.match(r"^[-*]\s+", line):
            if not in_list or list_tag != "ul":
                if in_list:
                    out.append(f"</{list_tag}>")
                out.append("<ul>")
                in_list, list_tag = True, "ul"
            out.append(f"<li>{inline(re.sub(r'^[-*]\s+', '', line))}</li>")
        elif line.strip() == "":
            if in_list:
                out.append(f"</{list_tag}>")
                in_list = False
        else:
            if in_list:
                out.append(f"</{list_tag}>")
                in_list = False
            out.append(f"<p>{inline(line)}</p>")
        i += 1
    if in_list:
        out.append(f"</{list_tag}>")
    return "\n".join(out)


def convert(md_path, html_path):
    md = open(md_path, encoding="utf-8").read()
    m = re.search(r"^# (.+)$", md, re.M)
    title = m.group(1) if m else os.path.basename(md_path)
    body = md_to_body(md)
    doc = ("<!DOCTYPE html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
           f"<title>{html.escape(title)}</title>\n<style>\n{CSS}\n</style>\n</head>\n<body>\n"
           + body +
           "\n<footer>대응 MD와 동일 내용(전체 섹션) · sap-tcode-analyze · "
           "상대경로·오프라인 단일 파일</footer>\n</body>\n</html>\n")
    open(html_path, "w", encoding="utf-8").write(doc)
    return html_path


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "docs/analysis"
    for f in sorted(os.listdir(target)):
        if f.endswith(".md"):
            out = convert(os.path.join(target, f), os.path.join(target, f[:-3] + ".html"))
            print("built", out)


if __name__ == "__main__":
    main()
