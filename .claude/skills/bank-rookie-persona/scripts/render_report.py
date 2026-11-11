#!/usr/bin/env python3
"""persona.json -> 신입행원 페르소나 분석 보고서(HTML 한 장).

- 모든 항목에 출처 태그를 붙이고 신뢰도(높음/보통/추정)를 출처로 다시 계산한다.
- 어려움 맵(막대), 단계별 어려움(히트맵), 설문 분포(막대)를 인라인 SVG로 그린다. 외부 라이브러리 없음.
- 문제가 있으면 '경고:'를 출력하고 종료 코드 2.

사용: python render_report.py persona.json --out 보고서.html   ('-'이면 표준출력)
"""
import argparse, html, json, sys
from pathlib import Path

WARN = []
e = lambda s: html.escape(str(s if s is not None else ""))
CONF_RANK = {"추정": 0, "보통": 1, "높음": 2}
MIN_N = 5


class Report:
    def __init__(self, d):
        self.d = d
        self.src = {s["id"]: s for s in d.get("sources", [])}
        for s in d.get("sources", []):
            if s.get("type") not in ("데이터", "설문", "공개자료", "현장의견"):
                WARN.append(f"출처 {s.get('id')}의 type '{s.get('type')}'는 데이터/설문/공개자료/현장의견 중 하나여야 합니다.")
            if s.get("type") == "공개자료" and not s.get("url"):
                WARN.append(f"공개자료 {s['id']}에 url이 없습니다.")
        self.used = set()

    # ---------- 근거 ----------
    def conf(self, item, where):
        ids = item.get("src") or []
        if not ids:
            WARN.append(f"[{where}] 출처가 없습니다: {item.get('text') or item.get('title') or item.get('area')}")
            return "추정"
        types = set()
        for i in ids:
            s = self.src.get(i)
            if not s:
                WARN.append(f"[{where}] 없는 출처 ID: {i}")
                continue
            self.used.add(i)
            t = s.get("type")
            if t == "설문" and int(s.get("n", 0)) < MIN_N:
                t = "현장의견"  # 응답자 5명 미만 설문은 추정 수준
            types.add(t)
        strong = types - {"현장의견"}
        calc = "높음" if len(types) >= 2 and strong else "보통" if strong else "추정"
        decl = item.get("conf")
        if decl:
            if decl not in CONF_RANK:
                WARN.append(f"[{where}] conf는 높음/보통/추정 중 하나여야 합니다.")
            elif CONF_RANK[decl] > CONF_RANK[calc]:
                WARN.append(f"[{where}] 신뢰도 '{decl}'는 출처로 계산한 '{calc}'보다 높아 '{calc}'로 표시합니다.")
            else:
                calc = decl
        return calc

    def tags(self, item, where):
        c = self.conf(item, where)
        chips = "".join(f'<span class="src" title="{e(self.src.get(i, {}).get("title", "?"))}">{e(i)}</span>' for i in item.get("src", []))
        cf = f'<span class="conf c{CONF_RANK[c]}">{c}</span>'
        conflict = f'<span class="conflict" title="{e(item["conflict"])}">불일치</span>' if item.get("conflict") else ""
        note = f'<div class="cnote">불일치: {e(item["conflict"])}</div>' if item.get("conflict") else ""
        return f'<span class="tags">{chips}{cf}{conflict}</span>{note}'

    def items(self, arr, where):
        if not arr:
            return '<p class="muted">아직 근거가 모이지 않았습니다.</p>'
        return "<ul class=\"ev\">" + "".join(f"<li><span>{e(x['text'])}</span>{self.tags(x, where)}</li>" for x in arr) + "</ul>"

    # ---------- 차트 ----------
    @staticmethod
    def ramp(v):
        """1~5 -> 같은 색상의 밝기 단계(순차형). 숫자 라벨을 함께 쓰므로 색만으로 읽지 않는다."""
        steps = ["var(--seq1)", "var(--seq2)", "var(--seq3)", "var(--seq4)", "var(--seq5)"]
        i = max(1, min(5, round(float(v)))) - 1
        return steps[i], ("var(--on-dark)" if i >= 3 else "var(--ink)")

    def difficulty_bars(self, dm):
        w, lab, rowh = 640, 150, 34
        h = rowh * len(dm) + 30
        bars = []
        for k, a in enumerate(dm):
            y = 10 + k * rowh
            sc = float(a.get("score", 0))
            bw = (w - lab - 130) * sc / 5
            bars.append(
                f'<g class="hit"><title>{e(a["area"])}: 어려움 {sc:.1f} / 5, 위험도 {e(a.get("risk", "-"))}</title>'
                f'<rect x="0" y="{y - 4}" width="{w}" height="{rowh}" fill="transparent"/>'
                f'<text x="{lab - 10}" y="{y + 15}" text-anchor="end" class="axl">{e(a["area"])}</text>'
                f'<rect x="{lab}" y="{y + 3}" width="{max(bw, 2):.1f}" height="16" rx="4" style="fill:var(--brand)"/>'
                f'<text x="{lab + bw + 8:.1f}" y="{y + 15}" class="val">{sc:.1f}</text>'
                f'<text x="{lab + bw + 40:.1f}" y="{y + 15}" class="tick">위험 {e(a.get("risk", "-"))}{" · ⚠ 불일치" if a.get("conflict") else ""}</text></g>')
        grid = "".join(f'<line x1="{lab + (w - lab - 130) * t / 5:.1f}" x2="{lab + (w - lab - 130) * t / 5:.1f}" y1="4" y2="{h - 22}" class="grid"/>'
                       f'<text x="{lab + (w - lab - 130) * t / 5:.1f}" y="{h - 6}" text-anchor="middle" class="tick">{t}</text>' for t in range(0, 6))
        return f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="영역별 어려움 점수 막대그래프">{grid}{"".join(bars)}</svg>'

    def heatmap(self, dm, stages):
        rows = [a for a in dm if a.get("by_stage")]
        if not rows:
            return ""
        ns = len(stages)
        for a in rows:
            if len(a["by_stage"]) != ns:
                WARN.append(f"어려움 맵 '{a['area']}'의 by_stage 길이({len(a['by_stage'])})가 단계 수({ns})와 다릅니다.")
        lab, cw, ch = 150, 92, 34
        w, h = lab + cw * ns, 34 + ch * len(rows)
        out = [f'<text x="{lab + cw * j + cw / 2}" y="20" text-anchor="middle" class="tick">{e(s["lv"])}</text>' for j, s in enumerate(stages)]
        for i, a in enumerate(rows):
            y = 30 + i * ch
            out.append(f'<text x="{lab - 10}" y="{y + ch / 2 + 5}" text-anchor="end" class="axl">{e(a["area"])}</text>')
            for j, v in enumerate(a["by_stage"][:ns]):
                if v in (None, ""):
                    continue
                fill, ink = self.ramp(v)
                out.append(f'<g class="hit"><title>{e(a["area"])} · {e(stages[j]["lv"])} {e(stages[j].get("when", ""))}: {v} / 5</title>'
                           f'<rect x="{lab + cw * j + 1}" y="{y + 1}" width="{cw - 2}" height="{ch - 2}" rx="4" style="fill:{fill}"/>'
                           f'<text x="{lab + cw * j + cw / 2}" y="{y + ch / 2 + 5}" text-anchor="middle" style="fill:{ink}" class="cell">{v}</text></g>')
        legend = ('<div class="legend">어려움 '
                  + "".join(f'<span><i style="background:var(--seq{k})"></i>{k}</span>' for k in range(1, 6))
                  + ' <span class="muted">(진할수록 어려움)</span></div>')
        return f'<h3>단계별 어려움</h3><svg viewBox="0 0 {w} {h}" role="img" aria-label="단계별 어려움 히트맵">{"".join(out)}</svg>{legend}'

    def survey_charts(self, sv):
        if not sv:
            return ""
        n = int(sv.get("n", 0))
        sid = sv.get("source", "S1")
        if sid not in self.src:
            WARN.append(f"설문 결과의 source '{sid}'가 sources에 없습니다.")
        elif int(self.src[sid].get("n", -1)) != n:
            WARN.append(f"설문 집계 응답자 {n}명과 출처 {sid}의 n({self.src[sid].get('n')})이 다릅니다.")
        if sv.get("suppressed") or n < MIN_N:
            return f'<p class="note">설문 응답자가 {n}명({MIN_N}명 미만)이라 개인 식별을 막기 위해 분포를 표시하지 않습니다.</p>'
        out = [f'<p class="muted">응답자 {n}명 · 출처 <span class="src">{e(sid)}</span> · 복수 선택 문항은 합이 100%를 넘을 수 있습니다.</p><div class="sgrid">']
        for q in sv.get("questions", []):
            if q["type"] == "text":
                continue
            dist = q["dist"]
            keys = list(dist.keys())
            mx = max(dist.values()) or 1
            w, lab, rowh = 420, 130, 24
            h = rowh * len(keys) + 6
            rows = []
            for k, key in enumerate(keys):
                c = dist[key]
                pct = c / n * 100
                bw = (w - lab - 100) * c / mx
                y = 4 + k * rowh
                name = f"{key}점" if q["type"] == "likert" else key
                rows.append(f'<g class="hit"><title>{e(name)}: {c}명 ({pct:.0f}%)</title><rect x="0" y="{y}" width="{w}" height="{rowh}" fill="transparent"/>'
                            f'<text x="{lab - 8}" y="{y + 16}" text-anchor="end" class="axl sm">{e(name[:14])}</text>'
                            f'<rect x="{lab}" y="{y + 5}" width="{max(bw, 2):.1f}" height="13" rx="4" style="fill:var(--brand)"/>'
                            f'<text x="{lab + bw + 6:.1f}" y="{y + 16}" class="val sm">{c}명 · {pct:.0f}%</text></g>')
            mean = f' <span class="muted">평균 {q["mean"]} / 5</span>' if q.get("mean") is not None else ""
            out.append(f'<figure><figcaption>{e(q["q"])}{mean}</figcaption><svg viewBox="0 0 {w} {h}" role="img" aria-label="{e(q["q"])} 응답 분포">{"".join(rows)}</svg></figure>')
        return "".join(out) + "</div>"

    # ---------- 페이지 ----------
    def build(self):
        d, m = self.d, self.d.get("meta", {})
        p = d.get("persona", {})
        stages = d.get("stages", [])
        dm = sorted(d.get("difficulty_map", []), key=lambda a: -float(a.get("score", 0)))
        for a in dm:
            if a.get("risk") not in ("높음", "중간", "낮음"):
                WARN.append(f"어려움 맵 '{a.get('area')}'의 risk는 높음/중간/낮음 중 하나여야 합니다.")
        b = []

        # 1. 요약
        top = d.get("findings", [])[:3]
        b.append('<section id="summary"><h2>한눈에 보기</h2><div class="sumgrid">'
                 f'<div class="hero"><div class="avatar" aria-hidden="true">{e(p.get("name", "?")[:1])}</div>'
                 f'<div><b class="pname">{e(p.get("name", "대표 페르소나"))}</b> <span class="muted">{e(p.get("age", ""))}{"세" if p.get("age") else ""} · {e(m.get("role", ""))}</span>'
                 f'<p class="headline">{e(p.get("headline", ""))}</p></div></div>'
                 '<div class="kpis">'
                 f'<div><b>{len(stages)}</b><span>성장 단계</span></div>'
                 f'<div><b>{sum(1 for a in dm if a.get("risk") == "높음")}</b><span>위험도 높음 영역</span></div>'
                 f'<div><b>{len(d.get("sources", []))}</b><span>근거 자료</span></div></div></div>'
                 + ("<h3>핵심 발견</h3><ol class=\"top\">" + "".join(f"<li><b>{e(f['title'])}</b> {e(f.get('text', ''))}{self.tags(f, '핵심 발견')}</li>" for f in top) + "</ol>" if top else "")
                 + "</section>")

        # 2. 페르소나
        blocks = [("배경", "background"), ("이미 아는 것", "knows"), ("모르는 것·빈틈", "gaps"), ("마음속 부담", "worries"),
                  ("자주 받는 질문", "frequent_questions"), ("가장 위험한 실수", "critical_mistakes"), ("배우는 방식", "learning")]
        b.append('<section id="persona"><h2>대표 페르소나</h2><div class="pgrid">'
                 + "".join(f'<div class="pblock{" danger" if k == "critical_mistakes" else ""}"><h4>{t}</h4>{self.items(p.get(k), t)}</div>' for t, k in blocks)
                 + "</div></section>")

        # 3. 단계
        if stages:
            rows = "".join(f'<tr><td><b>{e(s["lv"])}</b><br><span class="muted">{e(s.get("when", ""))}</span></td><td class="quote">“{e(s.get("quote", ""))}”</td>'
                           f'<td>{e(s.get("goal", ""))}</td><td>{e(s.get("scope", ""))}</td><td>{e(s.get("practice", ""))}</td><td>{e(s.get("exit", ""))}</td>'
                           f'<td>{self.tags(s, "단계 " + s["lv"])}</td></tr>' for s in stages)
            b.append('<section id="stages"><h2>성장 단계</h2><div class="tw"><table><tr><th>단계</th><th>신입의 말</th><th>학습 목표</th><th>다룰 업무·상품</th>'
                     f'<th>연습 방식</th><th>다음 단계 기준</th><th>근거</th></tr>{rows}</table></div></section>')

        # 4. 어려움 맵
        if dm:
            rows = "".join(f'<tr><td>{e(a["area"])}</td><td class="num">{float(a.get("score", 0)):.1f}</td><td><span class="risk r{e(a.get("risk"))}">{e(a.get("risk"))}</span></td>'
                           f'<td>{e(a.get("note", ""))}</td><td>{self.tags(a, "어려움 " + a["area"])}</td></tr>' for a in dm)
            b.append('<section id="difficulty"><h2>어려움 맵</h2><p class="muted">1~5점, 높을수록 어렵습니다. 위험도는 실수했을 때 고객 피해·민원으로 이어질 가능성입니다.</p>'
                     f'{self.difficulty_bars(dm)}{self.heatmap(dm, stages)}'
                     f'<details><summary>표로 보기</summary><div class="tw"><table><tr><th>영역</th><th>어려움</th><th>위험도</th><th>설명</th><th>근거</th></tr>{rows}</table></div></details></section>')

        # 5. 발견
        if d.get("findings"):
            b.append('<section id="findings"><h2>자료에서 찾은 것</h2>'
                     + "".join(f'<div class="finding"><h4>{e(f["title"])}</h4><p>{e(f.get("text", ""))}</p>{self.tags(f, "발견")}</div>' for f in d["findings"]) + "</section>")

        # 6. 설문
        if d.get("survey"):
            sv = d["survey"]
            q = ""
            if d.get("quotes") and int(sv.get("n", 0)) >= MIN_N:
                q = "<h3>자유응답에서</h3>" + "".join(f'<blockquote>{e(x["text"])}{self.tags(x, "인용")}</blockquote>' for x in d["quotes"])
            b.append(f'<section id="survey"><h2>설문 결과</h2>{self.survey_charts(sv)}{q}</section>')

        # 7. 제안
        if d.get("proposals"):
            rows = "".join(f'<tr><td class="num">{e(x.get("priority", ""))}</td><td>{e(x.get("stage", ""))}</td><td>{e(x.get("need", ""))}</td>'
                           f'<td><b>{e(x.get("proposal", ""))}</b></td><td>{e(x.get("format", ""))}</td><td>{self.tags(x, "제안")}</td></tr>'
                           for x in sorted(d["proposals"], key=lambda x: x.get("priority", 99)))
            b.append('<section id="proposals"><h2>교육 제안</h2><div class="tw"><table><tr><th>순위</th><th>단계</th><th>해결할 니즈</th><th>제안</th><th>형식</th><th>근거</th></tr>'
                     f"{rows}</table></div></section>")

        # 8. 출처
        srows = "".join(f'<tr><td><span class="src">{e(s["id"])}</span></td><td>{e(s.get("type"))}</td><td>{e(s.get("title"))}'
                        + (f' <a href="{e(s["url"])}" target="_blank" rel="noopener">링크</a>' if s.get("url") else "")
                        + "</td><td>" + " · ".join(x for x in (e(s.get("detail", "")), f'응답 {e(s["n"])}명' if s.get("n") else "",
                                                             f'확인 {e(s["checked"])}' if s.get("checked") else "") if x) + "</td></tr>"
                        for s in d.get("sources", []))
        unused = [i for i in self.src if i not in self.used]
        if unused:
            WARN.append(f"어디에도 쓰이지 않은 출처: {', '.join(unused)}")
        oq = ""
        if d.get("open_questions"):
            oq = "<h3>아직 확인하지 못한 것</h3><ul>" + "".join(f"<li>{e(x)}</li>" for x in d["open_questions"]) + "</ul>"
        b.append('<section id="sources"><h2>근거와 신뢰도</h2>'
                 '<div class="tw"><table class="legendt"><tr><th>신뢰도</th><th>조건</th></tr>'
                 '<tr><td><span class="conf c2">높음</span></td><td>서로 다른 유형의 출처 2개 이상이 같은 내용을 가리킴</td></tr>'
                 '<tr><td><span class="conf c1">보통</span></td><td>데이터·설문·공개자료 중 한 유형만 있음</td></tr>'
                 f'<tr><td><span class="conf c0">추정</span></td><td>현장의견만 있거나 설문 응답자가 {MIN_N}명 미만</td></tr></table></div>'
                 f'<h3>출처 목록</h3><div class="tw"><table><tr><th>ID</th><th>유형</th><th>자료</th><th>상세</th></tr>{srows}</table></div>{oq}</section>')

        return PAGE.format(
            title=e(f'{m.get("bank", "")} {m.get("role", "")} 신입행원 페르소나 분석'.replace("  ", " ")),
            bank=e(m.get("bank", "")), btype=e(m.get("bank_type", "")), role=e(m.get("role", "")),
            scope=e(m.get("scope", "")), training=e(m.get("training", "")), author=e(m.get("author", "")),
            date=e(m.get("date", "")), note=e(m.get("note", "교육 설계 참고용 분석")),
            brand=e(m.get("brand_color", "#1f3a5f")), body="".join(b))


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{--brand:{brand};--ink:#1b2230;--muted:#5f6b7a;--line:#dde2ea;--bg:#f5f7fa;--card:#fff;--soft:#f8fafc;
--seq1:#e6edf6;--seq2:#bfd0e6;--seq3:#86a6cf;--seq4:#4a74aa;--seq5:#1f3f73;--on-dark:#fff;
--good:#0f7a43;--good-bg:#e5f5ec;--warn:#9a5b00;--warn-bg:#fff3dc;--crit:#b3261e;--crit-bg:#fdeceb}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--ink:#e7ebf2;--muted:#a3adbb;--line:#323b49;--bg:#141921;--card:#1c2330;--soft:#222a38;
--seq1:#24344d;--seq2:#2f4d78;--seq3:#4a6fa3;--seq4:#7c9dca;--seq5:#b9cdea;--on-dark:#10151d;--brand:#7fa3d6;
--good:#6fd39b;--good-bg:#173226;--warn:#f0b357;--warn-bg:#352812;--crit:#ff8f86;--crit-bg:#3a1d1b}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Pretendard","Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif;line-height:1.6;font-size:15px}}
header{{background:var(--brand);color:#fff;padding:22px 24px}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]) header{{background:#1f3a5f}}}}
header h1{{margin:0 0 4px;font-size:22px}}header .meta{{font-size:13px;opacity:.9;display:flex;flex-wrap:wrap;gap:4px 14px}}
nav{{position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--line);padding:8px 16px;display:flex;gap:4px 14px;flex-wrap:wrap;font-size:14px;z-index:2}}
nav a{{color:var(--muted);text-decoration:none}}nav a:hover{{color:var(--ink)}}
main{{max-width:1080px;margin:0 auto;padding:8px 16px 40px}}
section{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 22px;margin:16px 0}}
h2{{margin:0 0 12px;font-size:19px}}h3{{font-size:16px;margin:18px 0 8px}}h4{{margin:0 0 6px;font-size:15px}}
.muted{{color:var(--muted)}}a{{color:var(--brand)}}
.sumgrid{{display:grid;grid-template-columns:1.6fr 1fr;gap:16px}}@media(max-width:720px){{.sumgrid{{grid-template-columns:1fr}}}}
.hero{{display:flex;gap:14px;align-items:flex-start;background:var(--soft);border-radius:12px;padding:14px}}
.avatar{{flex:0 0 56px;height:56px;border-radius:50%;background:var(--brand);color:#fff;display:grid;place-items:center;font-size:24px;font-weight:bold}}
.pname{{font-size:18px}}.headline{{margin:6px 0 0;font-size:16px}}
.kpis{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}.kpis div{{background:var(--soft);border-radius:12px;padding:10px;text-align:center}}
.kpis b{{display:block;font-size:26px}}.kpis span{{font-size:12px;color:var(--muted)}}
ol.top li{{margin-bottom:8px}}
.pgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}}
.pblock{{border:1px solid var(--line);border-radius:12px;padding:12px 14px}}.pblock.danger{{border-color:var(--crit);background:var(--crit-bg)}}
ul.ev{{list-style:none;margin:0;padding:0}}ul.ev li{{padding:6px 0;border-top:1px dashed var(--line)}}ul.ev li:first-child{{border-top:0}}
.tags{{display:inline-flex;gap:4px;flex-wrap:wrap;margin-left:6px;vertical-align:middle}}
.src{{font-size:11px;border:1px solid var(--line);border-radius:6px;padding:0 5px;color:var(--muted);background:var(--card)}}
.conf{{font-size:11px;border-radius:6px;padding:0 6px;font-weight:bold}}.c2{{background:var(--good-bg);color:var(--good)}}
.c1{{background:var(--seq1);color:var(--ink)}}.c0{{background:var(--warn-bg);color:var(--warn)}}
.conflict{{font-size:11px;border-radius:6px;padding:0 6px;background:var(--crit-bg);color:var(--crit);font-weight:bold}}
.cnote{{font-size:12px;color:var(--crit);margin-top:2px}}
.tw{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{border-bottom:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}}
th{{color:var(--muted);font-weight:normal;font-size:13px;background:var(--soft)}}td.quote{{font-style:italic;color:var(--muted)}}td.num{{font-weight:bold}}
.risk{{font-size:12px;border-radius:6px;padding:1px 7px;font-weight:bold}}.r높음{{background:var(--crit-bg);color:var(--crit)}}
.r중간{{background:var(--warn-bg);color:var(--warn)}}.r낮음{{background:var(--good-bg);color:var(--good)}}
svg{{width:100%;height:auto;display:block;margin:6px 0}}svg text{{fill:var(--ink);font-size:13px}}
.axl{{fill:var(--ink)}}.tick{{fill:var(--muted);font-size:11px}}.val{{fill:var(--ink);font-weight:bold}}.sm{{font-size:11.5px}}.cell{{font-weight:bold}}
.grid{{stroke:var(--line);stroke-width:1}}.hit:hover rect[style]{{opacity:.85}}
.legend{{font-size:12px;color:var(--muted);display:flex;gap:10px;align-items:center;flex-wrap:wrap}}.legend i{{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-2px;margin-right:3px}}
.sgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:12px}}@media(max-width:480px){{.sgrid{{grid-template-columns:1fr}}}}
figure{{margin:0;border:1px solid var(--line);border-radius:12px;padding:10px 12px}}figcaption{{font-size:14px;font-weight:bold}}
.finding{{border-left:4px solid var(--brand);background:var(--soft);border-radius:0 10px 10px 0;padding:10px 14px;margin-bottom:10px}}.finding p{{margin:4px 0}}
blockquote{{margin:8px 0;padding:8px 14px;border-left:3px solid var(--line);color:var(--muted)}}
.note{{background:var(--warn-bg);color:var(--warn);border-radius:8px;padding:8px 12px}}
details summary{{cursor:pointer;color:var(--brand);margin-top:8px}}
.banner{{background:var(--warn-bg);color:var(--warn);padding:8px 24px;font-size:13px;font-weight:bold}}
footer{{max-width:1080px;margin:0 auto 40px;padding:0 16px;font-size:12px;color:var(--muted)}}
@media print{{nav{{display:none}}section{{break-inside:avoid}}header{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}details{{display:block}}}}
</style></head><body>
<header><h1>{title}</h1><div class="meta"><span>{btype}</span><span>직무: {role}</span><span>범위: {scope}</span><span>연수: {training}</span></div></header>
<div class="banner">{note}</div>
<nav><a href="#summary">한눈에</a><a href="#persona">페르소나</a><a href="#stages">성장 단계</a><a href="#difficulty">어려움 맵</a><a href="#findings">발견</a><a href="#survey">설문</a><a href="#proposals">교육 제안</a><a href="#sources">근거</a></nav>
<main>{body}</main>
<footer>{note} · 작성 {author} · {date}. 집단 페르소나이며 특정 개인을 평가하지 않습니다. 설문 결과는 가명화한 자료를 {min_n}명 이상 집계한 것만 표시합니다.</footer>
</body></html>""".replace("{min_n}", str(MIN_N))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("persona")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    d = json.loads(Path(a.persona).read_text(encoding="utf-8"))
    if isinstance(d.get("survey"), str):
        d["survey"] = None
    doc = Report(d).build()
    if a.out == "-":
        sys.stdout.write(doc)
    else:
        Path(a.out).write_text(doc, encoding="utf-8")
        print(f"저장: {a.out}", file=sys.stderr)
    for w in WARN:
        print("경고:", w, file=sys.stderr)
    sys.exit(2 if WARN else 0)


if __name__ == "__main__":
    main()
