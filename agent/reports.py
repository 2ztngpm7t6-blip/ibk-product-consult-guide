"""상담 대화를 바탕으로 제안서·보고서를 자동으로 만들고 HTML로 저장한다."""

import html
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from .catalog import catalog_text, load_catalog, products_by_id
from .llm import parse_structured

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"


# ---------- 보고서 스키마 ----------

class Recommendation(BaseModel):
    product_id: str
    product_name: str
    reason: str
    key_terms: list[str]
    cautions: list[str]


class CustomerProposal(BaseModel):
    """고객에게 건네는 상품 제안서."""
    customer_alias: str
    needs_summary: str
    recommendations: list[Recommendation]
    combined_plan: str
    things_to_check_before_signing: list[str]


class ComplianceItem(BaseModel):
    item: str
    status: str  # "이행" / "미흡" / "해당없음"
    note: str


class SalesReport(BaseModel):
    """영업점 내부용 상담·영업 보고서."""
    customer_alias: str
    consultation_summary: str
    customer_needs: list[str]
    products_proposed: list[Recommendation]
    outcome: str
    compliance_checks: list[ComplianceItem]
    follow_up_actions: list[str]


class ScoreItem(BaseModel):
    criterion: str
    score: int  # 1~5
    comment: str


class TrainingReport(BaseModel):
    """직원 교육(롤플레이·퀴즈) 결과 보고서."""
    session_topic: str
    scores: list[ScoreItem]
    strengths: list[str]
    improvements: list[str]
    best_fit_products: list[str]
    recommended_study: list[str]


REPORT_TYPES = {
    "proposal": {
        "label": "고객 제안서",
        "schema": CustomerProposal,
        "instruction": "대화에서 드러난 고객 상황을 바탕으로 고객에게 건넬 상품 제안서를 작성하라. 추천은 최대 3개, 고객이 이해하기 쉬운 말로 쓴다.",
    },
    "sales": {
        "label": "상담·영업 보고서(내부용)",
        "schema": SalesReport,
        "instruction": "영업점 내부 보고용 상담 보고서를 작성하라. compliance_checks에는 금융소비자보호법 6대 판매원칙과 예금자보호 설명, 중도해지 불이익 설명을 항목별로 넣고 대화 근거로 이행/미흡/해당없음을 판단하라.",
    },
    "training": {
        "label": "교육 결과 보고서",
        "schema": TrainingReport,
        "instruction": "직원 교육 세션 결과 보고서를 작성하라. scores는 니즈 파악, 상품 적합성, 설명의무 이행, 교차판매, 응대 태도 5개 기준을 1~5점으로 평가한다. 롤플레이가 없었다면 대화에서 드러난 상품 이해도를 기준으로 평가한다.",
    },
}

REPORT_SYSTEM = (
    "너는 IBK기업은행 영업점의 보고서 작성 담당이다. 주어진 대화 기록과 상품 카탈로그에 있는 사실만 사용한다. "
    "대화에 없는 고객 정보나 카탈로그에 없는 금리·혜택은 지어내지 않는다. 정보가 없으면 '대화에서 확인되지 않음'이라고 쓴다. "
    "product_id는 반드시 카탈로그의 id를 쓴다. 한국어로 작성한다.\n\n"
)


# ---------- 생성 ----------

def generate_report(client, kind: str, transcript: str, customer_alias: str) -> tuple[str, str, bool]:
    """(HTML, 파일명, outputs 폴더 저장 성공 여부)를 돌려준다. 저장이 안 돼도 화면에서 내려받을 수 있다."""
    spec = REPORT_TYPES[kind]
    prompt = (
        f"{spec['instruction']}\n고객 가명: {customer_alias or '고객'}\n\n"
        f"<대화기록>\n{transcript}\n</대화기록>"
    )
    data = parse_structured(client, REPORT_SYSTEM + catalog_text(), prompt, spec["schema"])
    page = render_html(kind, data)
    name = f"{datetime.now():%Y%m%d_%H%M%S}_{kind}.html"
    try:
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / name).write_text(page, encoding="utf-8")
        saved = True
    except OSError:
        saved = False
    return page, name, saved


# ---------- HTML 렌더링 ----------

def _e(text) -> str:
    return html.escape(str(text))


def _ul(items) -> str:
    items = [i for i in items if str(i).strip()]
    if not items:
        return "<p class='muted'>해당 없음</p>"
    return "<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>"


def _recs(recs: list[Recommendation]) -> str:
    out = []
    for r in recs:
        out.append(
            f"<div class='card'><h3>{_e(r.product_name)} <span class='tag'>{_e(r.product_id)}</span></h3>"
            f"<p>{_e(r.reason)}</p><h4>핵심 조건</h4>{_ul(r.key_terms)}<h4>주의사항</h4>{_ul(r.cautions)}</div>"
        )
    return "".join(out) or "<p class='muted'>추천 상품 없음</p>"


def _sources(ids: list[str]) -> str:
    catalog = products_by_id()
    rows = []
    for pid in dict.fromkeys(ids):
        p = catalog.get(pid)
        if p:
            doc = p.get("doc", "상품안내장·약관 참조")
            rows.append(f"<li>{_e(p['name'])} — {_e(doc)}<br><a href='{_e(p['source_url'])}'>공식 상품 페이지</a></li>")
        else:
            rows.append(f"<li>{_e(pid)} — <b>카탈로그에 없는 id</b> (확인 필요)</li>")
    return "<ul>" + "".join(rows) + "</ul>" if rows else "<p class='muted'>인용된 상품 없음</p>"


def render_html(kind: str, data: BaseModel) -> str:
    cat = load_catalog()
    title = REPORT_TYPES[kind]["label"]
    ids: list[str] = []

    if isinstance(data, CustomerProposal):
        ids = [r.product_id for r in data.recommendations]
        body = (
            f"<p class='lead'><b>{_e(data.customer_alias)}</b> 고객님을 위한 상품 제안</p>"
            f"<h2>고객님 상황 요약</h2><p>{_e(data.needs_summary)}</p>"
            f"<h2>추천 상품</h2>{_recs(data.recommendations)}"
            f"<h2>함께 쓰면 좋은 방법</h2><p>{_e(data.combined_plan)}</p>"
            f"<h2>가입 전 꼭 확인하세요</h2>{_ul(data.things_to_check_before_signing)}"
        )
    elif isinstance(data, SalesReport):
        ids = [r.product_id for r in data.products_proposed]
        checks = "".join(
            f"<tr><td>{_e(c.item)}</td><td class='st st-{_e(c.status)}'>{_e(c.status)}</td><td>{_e(c.note)}</td></tr>"
            for c in data.compliance_checks
        )
        body = (
            f"<p class='lead'>고객: <b>{_e(data.customer_alias)}</b></p>"
            f"<h2>상담 요약</h2><p>{_e(data.consultation_summary)}</p>"
            f"<h2>고객 니즈</h2>{_ul(data.customer_needs)}"
            f"<h2>제안 상품</h2>{_recs(data.products_proposed)}"
            f"<h2>상담 결과</h2><p>{_e(data.outcome)}</p>"
            f"<h2>판매원칙 점검</h2><table><tr><th>항목</th><th>결과</th><th>근거</th></tr>{checks}</table>"
            f"<h2>후속 조치</h2>{_ul(data.follow_up_actions)}"
        )
    else:
        total = sum(s.score for s in data.scores)
        rows = "".join(
            f"<tr><td>{_e(s.criterion)}</td><td class='num'>{_e(s.score)} / 5</td><td>{_e(s.comment)}</td></tr>"
            for s in data.scores
        )
        body = (
            f"<p class='lead'>주제: <b>{_e(data.session_topic)}</b> · 총점 {total} / {5 * len(data.scores)}</p>"
            f"<h2>평가</h2><table><tr><th>기준</th><th>점수</th><th>코멘트</th></tr>{rows}</table>"
            f"<h2>잘한 점</h2>{_ul(data.strengths)}"
            f"<h2>보완할 점</h2>{_ul(data.improvements)}"
            f"<h2>이 고객에게 맞았을 상품</h2>{_ul(data.best_fit_products)}"
            f"<h2>추천 학습</h2>{_ul(data.recommended_study)}"
        )

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<style>
  :root {{ --ink:#1d2433; --muted:#6b7280; --line:#d9dee7; --brand:#0b4ea2; --soft:#eef4fc; }}
  body {{ font-family: "Malgun Gothic","Apple SD Gothic Neo",sans-serif; color:var(--ink); background:#fff; max-width:820px; margin:32px auto; padding:0 16px; line-height:1.6; }}
  header {{ border-bottom:3px solid var(--brand); padding-bottom:12px; margin-bottom:20px; }}
  header h1 {{ margin:0; font-size:24px; color:var(--brand); }}
  header .meta {{ color:var(--muted); font-size:13px; }}
  h2 {{ font-size:17px; margin-top:28px; border-left:4px solid var(--brand); padding-left:8px; }}
  h3 {{ margin:0 0 6px; font-size:16px; }} h4 {{ margin:10px 0 2px; font-size:13px; color:var(--muted); }}
  .lead {{ font-size:16px; }} .muted {{ color:var(--muted); }}
  .card {{ border:1px solid var(--line); border-radius:8px; padding:14px 16px; margin:10px 0; background:var(--soft); }}
  .tag {{ font-size:12px; color:var(--brand); border:1px solid var(--brand); border-radius:10px; padding:0 6px; }}
  table {{ border-collapse:collapse; width:100%; font-size:14px; }} th,td {{ border:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }}
  th {{ background:var(--soft); }} .num {{ white-space:nowrap; }}
  .st-미흡 {{ color:#b42318; font-weight:bold; }} .st-이행 {{ color:#067647; font-weight:bold; }}
  footer {{ margin-top:32px; font-size:12px; color:var(--muted); border-top:1px solid var(--line); padding-top:10px; }}
  @media print {{ body {{ margin:0; }} a {{ color:inherit; }} }}
</style></head><body>
<header><h1>{_e(title)}</h1>
<div class="meta">작성일 {datetime.now():%Y-%m-%d %H:%M} · {_e(cat['bank'])} 상품 기준일 {_e(cat['checked_at'])} · AI 자동 작성(교육·연습용)</div></header>
{body}
<h2>근거 자료</h2>{_sources(ids)}
<footer>본 문서는 AI가 상담 내용을 바탕으로 자동 작성한 교육·연습용 자료이며 실제 가입 권유나 금융 자문이 아닙니다.
금리·혜택은 변경될 수 있으므로 실제 가입 전 상품설명서와 약관을 반드시 확인하세요. 일반금융소비자는 금융소비자보호법에 따라 충분한 설명을 받을 권리가 있습니다.</footer>
</body></html>"""
