#!/usr/bin/env python3
"""IBK 신입행원 코치 - 결과물 HTML 렌더러.

Claude가 쓴 내용 JSON(대화 예시·퀴즈·플랜·피드백)에
data/products.json의 상품 사실(금리·조건·보호 여부)을 그대로 붙여 HTML 한 장을 만든다.
숫자는 이 스크립트가 데이터에서 직접 넣으므로 Claude가 지어낼 수 없다.

사용:
  python render.py <content.json> [--out 경로.html]
content.json의 kind: material | plan | feedback
"""
import argparse, html, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve()


def find_root():
    cwd = Path.cwd().resolve()
    for p in [*HERE.parents, cwd, *cwd.parents]:
        if (p / "data" / "products.json").exists():
            return p
    sys.exit("data/products.json을 찾지 못했습니다. 스킬을 ibk-sales-agent 폴더 안에 두세요.")


ROOT = find_root()
DATA = json.loads((ROOT / "data" / "products.json").read_text(encoding="utf-8"))
P = {p["id"]: p for p in DATA["products"]}
LOGO = ""
logo_file = ROOT / "report-studio" / "assets" / "logo.b64"
if logo_file.exists():
    LOGO = logo_file.read_text(encoding="utf-8").splitlines()[1].strip()  # 흰색 로고

LEVELS = {
    "Lv1": "입행 1주(연수)", "Lv2": "배치 1개월", "Lv3": "3개월",
    "Lv4": "6개월", "Lv5": "1년",
}
WARN = []
e = lambda s: html.escape(str(s))


def prod(pid):
    if pid not in P:
        sys.exit(f"알 수 없는 상품 ID: {pid}. data/products.json에 있는 ID만 쓰세요.")
    return P[pid]


def protection(p):
    if p["category"] == "카드":
        return "해당 없음(카드)"
    if p["category"].startswith("보험"):
        return f"예금 아님 · 보험금 지급 책임은 {p.get('insurer', '보험회사')}"
    return p.get("protection", "-")


def prot_class(p):
    t = protection(p)
    if "아님" in t or "보호되지 않" in t or "예금 아님" in t:
        return "bad"
    return "ok" if "대상" in t else "muted"


def rate_rows(p):
    rows, top = [], None
    for k, v in (p.get("rates") or {}).items():
        if isinstance(v, dict):
            rows += [(k, t, r) for t, r in v.items()]
        elif k == "최고":
            top = v
    return rows, top


def fmt_rate(r):
    return f"{r:.2f}%" if isinstance(r, (int, float)) else e(r)


def card(p):
    """한 장 요약 카드. 순서: 종류 → 대상 → 금리(기본→우대→최고) → 보호 → 주의 → 채널."""
    out = [f'<section class="pcard"><div class="ph"><span class="pid">{e(p["id"])}</span>'
           f'<h3>{e(p["name"])}</h3><span class="ptype">{e(p.get("type", ""))}</span></div>'
           f'<p class="one">{e(p.get("one_liner", ""))}</p><table class="kv">']
    row = lambda k, v: out.append(f"<tr><th>{e(k)}</th><td>{v}</td></tr>")
    if p.get("target"): row("가입 대상", e(p["target"]))
    if p.get("term"): row("기간", e(p["term"]))
    if p.get("amount"): row("금액", e(p["amount"]))
    if p.get("insurer"): row("보험회사", e(p["insurer"]))
    if p.get("annual_fee"): row("연회비", e(p["annual_fee"]))
    if p.get("requirement"): row("전월실적", e(p["requirement"]))
    if p.get("limits"): row("할인 한도", e(p["limits"]))
    row("예금자보호", f'<b class="{prot_class(p)}">{e(protection(p))}</b>')
    if p.get("channels"): row("가입 채널", e(p["channels"]))
    out.append("</table>")
    rows, top = rate_rows(p)
    if rows:
        head = rows[0][0]
        out.append(f'<h4>① 기본금리 <small>({e(head)}, 세전 연%)</small></h4><table class="grid"><tr>'
                   + "".join(f"<th>{e(t)}</th>" for _, t, _ in rows) + "</tr><tr>"
                   + "".join(f"<td>{fmt_rate(r)}</td>" for *_, r in rows) + "</tr></table>")
    if p.get("preferential"):
        out.append("<h4>② 우대조건</h4><ul>" + "".join(f"<li>{e(x)}</li>" for x in p["preferential"]) + "</ul>")
    if top is not None:
        out.append(f'<p class="top">③ 최고금리 <b>연 {fmt_rate(top)}</b> <small>우대조건을 모두 채웠을 때</small></p>')
    for key, title in (("benefits", "주요 혜택"), ("highlights", "핵심 내용"), ("features", "특징")):
        if p.get(key):
            items = p[key][:6]
            out.append(f"<h4>{title}</h4><ul>" + "".join(f"<li>{e(x)}</li>" for x in items) + "</ul>")
    if p.get("cautions"):
        out.append('<h4 class="warnh">가입 전 꼭 설명</h4><ul>' + "".join(f"<li>{e(x)}</li>" for x in p["cautions"]) + "</ul>")
    if p.get("coverage_note"):
        out.append(f'<p class="note">{e(p["coverage_note"])}</p>')
    src = f'<a href="{e(p["source_url"])}" target="_blank">공식 페이지</a>' if p.get("source_url") else ""
    out.append(f'<p class="src">{e(p.get("doc", ""))} {src}</p></section>')
    return "".join(out)


def compare(ids):
    ps = [prod(i) for i in ids]
    def first_rate(p):
        rows, _ = rate_rows(p)
        return " / ".join(f"{t} {fmt_rate(r)}" for _, t, r in rows[:3]) if rows else "-"
    def top(p):
        _, t = rate_rows(p)
        return f"연 {fmt_rate(t)}" if t is not None else "-"
    fields = [
        ("종류", lambda p: e(p.get("type", "-"))),
        ("가입 대상", lambda p: e(p.get("target", "-"))),
        ("기간", lambda p: e(p.get("term", "-"))),
        ("금액", lambda p: e(p.get("amount", "-"))),
        ("기본금리", first_rate),
        ("최고금리", top),
        ("연회비", lambda p: e(p.get("annual_fee", "-"))),
        ("전월실적", lambda p: e(p.get("requirement", "-"))),
        ("할인 한도", lambda p: e(p.get("limits", "-"))),
        ("예금자보호", lambda p: f'<b class="{prot_class(p)}">{e(protection(p))}</b>'),
        ("가입 채널", lambda p: e(p.get("channels", "-"))),
    ]
    rows = []
    for name, f in fields:
        vals = [f(p) for p in ps]
        if all(v in ("-", "") for v in vals):
            continue
        diff = ' class="diff"' if len(set(vals)) > 1 else ""
        rows.append(f"<tr{diff}><th>{name}</th>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>")
    return ('<table class="cmp"><tr><th></th>' + "".join(f"<th>{e(p['name'])}</th>" for p in ps)
            + "</tr>" + "".join(rows) + "</table><p class=\"hint\">색이 칠해진 줄이 서로 다른 부분입니다.</p>")


def check_numbers(text, pids, where):
    """Claude가 쓴 문장 속 % 숫자가 해당 상품 데이터에 있는지 검사(정확성 안전장치)."""
    blob = json.dumps([P[i] for i in pids if i in P], ensure_ascii=False)
    norm = {str(float(n)) for n in re.findall(r"\d+(?:\.\d+)?", blob)}  # 금리표 숫자·문장 속 숫자 모두
    for m in re.findall(r"(\d+(?:\.\d+)?)\s*%", text):
        if str(float(m)) not in norm:
            WARN.append(f"[{where}] '{m}%'가 상품 데이터({', '.join(pids)})에 없습니다. 확인하세요.")


def dialogs(items):
    out = []
    for d in items:
        pids = d.get("products", [d["product"]] if d.get("product") else [])
        for i in pids: prod(i)
        lines = []
        for who, said in d["lines"]:
            cls = "c" if who in ("고객", "customer") else "t"
            if cls == "t":  # 고객은 틀린 숫자(타행 금리 등)를 말할 수 있으므로 행원 말만 검사
                check_numbers(said, pids, d["title"])
            lines.append(f'<div class="ln {cls}"><span>{e(who)}</span><p>{e(said)}</p></div>')
        tip = f'<p class="tip"><b>포인트</b> {e(d["tip"])}</p>' if d.get("tip") else ""
        out.append(f'<section class="dlg"><h3>{e(d["title"])}</h3><p class="meta">고객 유형: {e(d.get("customer", "기본"))}'
                   f' · 상품: {e(", ".join(P[i]["name"] for i in pids))}</p>{"".join(lines)}{tip}</section>')
    return "".join(out)


def quiz(items, pids):
    out = ['<ol class="quiz">']
    for q in items:
        check_numbers(q["a"] + q.get("why", ""), q.get("products", pids), "퀴즈")
        out.append(f'<li><p class="q">{e(q["q"])}</p><details><summary>정답 보기</summary>'
                   f'<p><b>{e(q["a"])}</b></p><p class="why">{e(q.get("why", ""))}</p></details></li>')
    return "".join(out) + "</ol>"


def page(title, sub, body):
    logo = f'<img src="{LOGO}" alt="IBK기업은행 로고">' if LOGO else "<b>IBK기업은행</b>"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title><style>
:root{{--ink:#1d2433;--muted:#667085;--line:#dfe3ea;--bg:#f4f6fa;--card:#fff;--brand:#0b4ea2;--brand-soft:#e8f0fb;
--ok:#067647;--ok-soft:#e7f6ec;--warn:#b54708;--warn-soft:#fff4e5;--bad:#b42318;--bad-soft:#fdecea}}
*{{box-sizing:border-box}}body{{margin:0;font-family:"Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif;color:var(--ink);background:var(--bg);line-height:1.6;font-size:15px}}
.top-bar{{background:var(--brand);color:#fff;padding:14px 20px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}}
.top-bar img{{height:24px}}.top-bar h1{{margin:0;font-size:19px}}.top-bar .sub{{font-size:13px;opacity:.85}}
.top-bar .date{{margin-left:auto;background:rgba(255,255,255,.15);border-radius:999px;padding:3px 12px;font-size:13px}}
main{{max-width:980px;margin:18px auto;padding:0 16px}}
h2{{font-size:18px;border-left:4px solid var(--brand);padding-left:10px;margin:28px 0 12px}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin-bottom:14px}}
.pcard{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin-bottom:14px;break-inside:avoid}}
.ph{{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}}.ph h3{{margin:0;font-size:17px}}
.pid{{font-size:12px;background:var(--brand-soft);color:var(--brand);border-radius:6px;padding:1px 7px;font-weight:bold}}
.ptype{{font-size:13px;color:var(--muted)}}.one{{margin:6px 0 10px;color:var(--muted)}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top;font-size:14px}}
.kv th{{width:110px;background:#f8fafc;color:var(--muted);font-weight:normal}}
.grid th{{background:#f8fafc;font-weight:normal;font-size:13px}}.grid td{{font-weight:bold;color:var(--brand)}}
h4{{font-size:14px;margin:14px 0 4px}}.warnh{{color:var(--warn)}}ul{{margin:4px 0;padding-left:20px}}
.top{{background:var(--brand-soft);border-radius:8px;padding:8px 12px}}.top b{{color:var(--brand);font-size:17px}}
.ok{{color:var(--ok)}}.bad{{color:var(--bad)}}.muted{{color:var(--muted)}}
.note{{background:var(--warn-soft);border-radius:8px;padding:8px 12px;font-size:13px}}.src{{font-size:12px;color:var(--muted)}}
.cmp{{background:var(--card)}}.cmp th{{background:#f8fafc}}.cmp tr.diff td{{background:#fffbea}}.hint{{font-size:12px;color:var(--muted)}}
.dlg{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin-bottom:14px;break-inside:avoid}}
.dlg h3{{margin:0;font-size:16px}}.meta{{font-size:12px;color:var(--muted);margin:2px 0 10px}}
.ln{{display:flex;gap:10px;margin:6px 0}}.ln span{{flex:0 0 44px;font-size:12px;font-weight:bold;padding-top:7px}}
.ln p{{margin:0;padding:7px 12px;border-radius:10px;flex:1}}.ln.c p{{background:#f2f4f7}}.ln.t p{{background:var(--brand-soft)}}
.ln.t span{{color:var(--brand)}}.tip{{background:var(--ok-soft);border-radius:8px;padding:8px 12px;font-size:14px;margin:10px 0 0}}
.quiz li{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-bottom:8px}}
.q{{margin:0;font-weight:bold}}.why{{color:var(--muted);font-size:14px}}summary{{cursor:pointer;color:var(--brand);font-size:14px}}
.week{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin-bottom:12px;break-inside:avoid}}
.week h3{{margin:0 0 6px;font-size:16px}}.days td:first-child{{width:70px;font-weight:bold}}
.score td.n{{width:80px;font-weight:bold;color:var(--brand)}}.score td:nth-child(3){{width:180px}}.score td:first-child{{width:140px}}.bar{{height:8px;background:var(--line);border-radius:4px}}
.bar i{{display:block;height:8px;background:var(--brand);border-radius:4px}}
.crit{{background:var(--bad-soft);border:1px solid #f5c2bd;border-radius:10px;padding:10px 14px;margin-bottom:12px}}
.crit b{{color:var(--bad)}}.fix td:first-child{{color:var(--bad)}}.fix td:nth-child(2){{color:var(--ok);font-weight:bold}}
footer{{max-width:980px;margin:24px auto 40px;padding:0 16px;font-size:12px;color:var(--muted)}}
@media print{{body{{background:#fff}}.top-bar{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}details{{display:block}}details>*{{display:block}}}}
</style></head><body>
<div class="top-bar">{logo}<div><h1>{e(title)}</h1><div class="sub">{e(sub)}</div></div>
<span class="date">상품정보 기준일 {e(DATA.get("checked_at", ""))}</span></div>
<main>{body}</main>
<footer>개인이 만든 교육·연습용 자료입니다. IBK기업은행의 공식 자료나 금융 자문이 아니며, 로고 상표는 IBK기업은행 소유입니다.
금리는 세전 연%이고 바뀔 수 있으니 실제 안내 전 공식 페이지와 상품설명서를 다시 확인하세요. 등장인물은 모두 가명입니다.</footer>
</body></html>"""


def lv(c):
    l = c.get("level", "")
    return f"{l} {LEVELS.get(l, '')}".strip()


def render_material(c):
    pids = c.get("products", [])
    for i in pids: prod(i)
    b = []
    if c.get("intro"):
        b.append(f'<div class="box">{e(c["intro"])}</div>')
    if c.get("goals"):
        b.append('<h2>오늘의 목표</h2><div class="box"><ul>' + "".join(f"<li>{e(g)}</li>" for g in c["goals"]) + "</ul></div>")
    if pids:
        b.append("<h2>한 장 요약 카드</h2>" + "".join(card(P[i]) for i in pids))
    for pair in c.get("compare", []):
        b.append(f"<h2>비교표: {e(' vs '.join(P[i]['name'] for i in pair if i in P))}</h2>" + compare(pair))
        note = c.get("compare_notes", {}).get("|".join(pair))
        if note:
            check_numbers(note, pair, "비교 설명")
            b.append(f'<p class="tip">{e(note)}</p>')
    if c.get("dialogs"):
        b.append("<h2>실제 대화 예시</h2>" + dialogs(c["dialogs"]))
    if c.get("quiz"):
        b.append("<h2>확인 퀴즈</h2>" + quiz(c["quiz"], pids))
    if c.get("ask_template"):
        b.append('<h2>모를 때 이렇게 확인하기</h2><div class="box"><ul>' + "".join(f"<li>{e(x)}</li>" for x in c["ask_template"]) + "</ul></div>")
    return page(c.get("title", "신입행원 학습 노트"), f"{lv(c)} · {c.get('persona', '신입행원')}", "".join(b))


def render_plan(c):
    b = []
    if c.get("intro"):
        b.append(f'<div class="box">{e(c["intro"])}</div>')
    for w in c["weeks"]:
        pids = w.get("products", [])
        for i in pids: prod(i)
        names = ", ".join(P[i]["name"] for i in pids)
        days = "".join(f"<tr><td>{e(d['day'])}</td><td>{e(d['todo'])}</td></tr>" for d in w.get("days", []))
        b.append(f'<section class="week"><h3>{e(w["week"])}주차 · {e(w["goal"])}</h3>'
                 + (f'<p class="meta">다룰 상품: {e(names)}</p>' if names else "")
                 + (f'<table class="days">{days}</table>' if days else "")
                 + (f'<p class="tip"><b>주말 점검</b> {e(w["check"])}</p>' if w.get("check") else "") + "</section>")
    return page(c.get("title", "주간 학습 플랜"), f"{lv(c)} · 하루 {c.get('minutes', 30)}분", "".join(b))


RUBRIC = ["니즈 파악", "상품 정확성", "설명의무·적합성", "화법·공감", "교차판매·마무리"]


def render_feedback(c):
    pids = c.get("products", [])
    for i in pids: prod(i)
    b = [f'<div class="box"><b>상황</b> {e(c.get("scenario", ""))}<br><b>고객</b> {e(c.get("customer", ""))}</div>']
    crit = c.get("critical", [])
    if crit:
        b.append('<div class="crit"><b>치명 실수</b> 이 장면은 꼭 다시 연습하세요.<ul>' + "".join(f"<li>{e(x)}</li>" for x in crit) + "</ul></div>")
    sc = c.get("scores", {})
    missing = [k for k in RUBRIC if k not in sc]
    if missing:
        WARN.append(f"채점 항목 누락: {', '.join(missing)}")
    rows = "".join(f'<tr><td>{e(k)}</td><td class="n">{sc.get(k, "-")} / 5</td><td><div class="bar"><i style="width:{int(sc.get(k, 0)) * 20}%"></i></div>'
                   f'</td><td>{e(c.get("reasons", {}).get(k, ""))}</td></tr>' for k in RUBRIC)
    avg = sum(sc.get(k, 0) for k in RUBRIC) / len(RUBRIC)
    b.append(f'<h2>항목별 점수 (평균 {avg:.1f} / 5)</h2><table class="score">{rows}</table>')
    if c.get("good"):
        b.append('<h2>잘한 점</h2><div class="box"><ul>' + "".join(f"<li>{e(x)}</li>" for x in c["good"]) + "</ul></div>")
    if c.get("fix"):
        for f in c["fix"]:
            check_numbers(f["better"], pids, "개선 화법")
        b.append('<h2>이렇게 말해 보세요</h2><table class="fix"><tr><th>한 말</th><th>바꿔 말하기</th><th>이유</th></tr>'
                 + "".join(f"<tr><td>{e(f['said'])}</td><td>{e(f['better'])}</td><td>{e(f.get('why', ''))}</td></tr>" for f in c["fix"]) + "</table>")
    if pids:
        b.append("<h2>이번에 다룬 상품 다시 보기</h2>" + "".join(card(P[i]) for i in pids))
    if c.get("next"):
        b.append(f'<h2>다음 연습</h2><div class="box">{e(c["next"])}</div>')
    return page(c.get("title", "롤플레이 피드백"), f"{lv(c)} · {c.get('persona', '신입행원')}", "".join(b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("content")
    ap.add_argument("--out")
    a = ap.parse_args()
    c = json.loads(Path(a.content).read_text(encoding="utf-8"))
    kind = c.get("kind")
    fn = {"material": render_material, "plan": render_plan, "feedback": render_feedback}.get(kind)
    if not fn:
        sys.exit("kind는 material, plan, feedback 중 하나여야 합니다.")
    doc = fn(c)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if a.out == "-":  # 파일 쓰기가 막힌 환경: 표준출력으로 내보내고 셸에서 > 로 저장
        sys.stdout.write(doc)
    else:
        out = Path(a.out) if a.out else ROOT / "outputs" / "rookie" / (Path(a.content).stem + ".html")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(doc, encoding="utf-8")
        print(f"저장: {out}", file=sys.stderr)
    for w in WARN:
        print("경고:", w, file=sys.stderr)
    if WARN:
        sys.exit(2)


if __name__ == "__main__":
    main()
