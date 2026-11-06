"""IBK 상품 영업 AI 에이전트 — Streamlit 화면.

실행: streamlit run app.py
"""

import os

import streamlit as st

from agent.catalog import load_catalog
from agent.llm import ChatStream, LLMError, make_client
from agent.prompts import PERSONAS, system_blocks
from agent.reports import REPORT_TYPES, generate_report

st.set_page_config(page_title="IBK 영업 AI 에이전트", page_icon="🏦", layout="wide")


def state(persona_key: str) -> dict:
    """페르소나마다 대화를 따로 보관한다."""
    key = f"conv_{persona_key}"
    if key not in st.session_state:
        st.session_state[key] = {"api": [], "view": [], "report": None}
    return st.session_state[key]


def transcript(conv: dict) -> str:
    who = {"user": "직원/고객", "assistant": "AI"}
    return "\n\n".join(f"[{who[r]}] {t}" for r, t in conv["view"])


def send(conv: dict, persona_key: str, text: str) -> None:
    client = make_client(st.session_state.get("api_key") or None)
    conv["api"].append({"role": "user", "content": text})
    conv["view"].append(("user", text))
    with st.chat_message("user"):
        st.markdown(text)
    with st.chat_message("assistant"):
        stream = ChatStream(client, system_blocks(persona_key), conv["api"])
        try:
            reply = st.write_stream(stream)
        except LLMError as err:
            conv["api"].pop()
            conv["view"].pop()
            st.error(str(err))
            return
    # thinking 블록까지 그대로 다음 턴에 넘긴다.
    conv["api"].append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in stream.final.content]})
    conv["view"].append(("assistant", reply))


# ---------- 사이드바 ----------
catalog = load_catalog()
with st.sidebar:
    st.title("🏦 IBK 영업 AI")
    st.session_state["api_key"] = st.text_input(
        "Claude API 키",
        value=st.session_state.get("api_key", ""),
        type="password",
        help="입력하지 않으면 ANTHROPIC_API_KEY 환경변수를 사용합니다. 키는 이 화면에만 보관됩니다.",
    )
    if not (st.session_state["api_key"] or os.environ.get("ANTHROPIC_API_KEY")):
        st.warning("API 키를 입력해야 AI가 답할 수 있어요.")

    persona_key = st.radio(
        "모드 선택",
        list(PERSONAS),
        format_func=lambda k: f"{PERSONAS[k]['icon']} {PERSONAS[k]['label']}",
    )
    conv = state(persona_key)

    profile_msg = None
    if persona_key == "teller":
        with st.expander("고객 프로필", expanded=True):
            with st.form("profile"):
                alias = st.text_input("가명", "김고객")
                age = st.selectbox("연령대", ["20대", "30대", "40대", "50대", "60대 이상"])
                job = st.text_input("직업", "중소기업 직장인")
                purpose = st.multiselect(
                    "방문 목적·니즈",
                    ["목돈 예치", "적금으로 모으기", "내 집 마련", "노후 준비", "세액공제", "카드 혜택", "생활비 절약", "이벤트 자금(결혼·이사 등)"],
                )
                funds = st.text_input("자금 상황", "만기 적금 1,000만원, 월 여유자금 50만원")
                main_bank = st.text_input("IBK 거래 현황", "급여이체 없음, 입출금 통장만 보유")
                spending = st.text_input("카드 사용 패턴", "월 80만원, 온라인쇼핑·편의점 많음")
                notes = st.text_area("특이사항", "금리에 민감, 예금자보호 여부를 꼭 물어봄")
                if st.form_submit_button("상담 준비", use_container_width=True):
                    st.session_state["alias"] = alias
                    profile_msg = (
                        f"[고객 프로필]\n가명: {alias}\n연령대: {age}\n직업: {job}\n"
                        f"니즈: {', '.join(purpose) or '미입력'}\n자금 상황: {funds}\nIBK 거래 현황: {main_bank}\n"
                        f"카드 사용 패턴: {spending}\n특이사항: {notes}\n\n이 고객 상담을 준비해 줘."
                    )

    st.divider()
    st.subheader("📄 보고서 자동 작성")
    default_report = {"edu": "training", "guide": "proposal", "teller": "sales"}[persona_key]
    report_kind = st.selectbox(
        "종류", list(REPORT_TYPES), index=list(REPORT_TYPES).index(default_report),
        format_func=lambda k: REPORT_TYPES[k]["label"],
    )
    make_report = st.button("현재 대화로 작성", use_container_width=True)

    st.divider()
    if st.button("대화 새로 시작", use_container_width=True):
        st.session_state.pop(f"conv_{persona_key}", None)
        st.rerun()
    st.caption(f"상품 {len(catalog['products'])}개 · {catalog['bank']} 공식 홈페이지 기준 {catalog['checked_at']}")
    st.caption("교육·연습용 시뮬레이션입니다. 실제 고객 개인정보는 입력하지 마세요.")


# ---------- 본문 ----------
p = PERSONAS[persona_key]
st.header(f"{p['icon']} {p['label']}")
st.caption(p["description"])

with st.chat_message("assistant"):
    st.markdown(p["starter"])
for role, text in conv["view"]:
    with st.chat_message(role):
        st.markdown(text)

if profile_msg:
    send(conv, persona_key, profile_msg)
if user_text := st.chat_input("메시지를 입력하세요"):
    send(conv, persona_key, user_text)

if make_report and not conv["view"]:
    st.info("먼저 대화를 나눈 뒤에 보고서를 만들 수 있어요.")
elif make_report:
    with st.spinner(f"{REPORT_TYPES[report_kind]['label']} 작성 중..."):
        try:
            page, name, saved = generate_report(
                make_client(st.session_state.get("api_key") or None),
                report_kind, transcript(conv), st.session_state.get("alias", ""),
            )
            conv["report"] = (report_kind, page, name)
            if saved:
                st.toast(f"outputs/{name} 에 저장했습니다.")
        except LLMError as err:
            st.error(str(err))

if conv["report"]:
    kind, page, name = conv["report"]
    st.divider()
    st.subheader(f"📄 {REPORT_TYPES[kind]['label']}")
    st.download_button("HTML 내려받기 (브라우저에서 열고 Ctrl+P로 PDF 저장)", page, file_name=name, mime="text/html")
    # AI가 쓴 값은 render_html에서 모두 이스케이프되고, 링크는 카탈로그에서만 온다.
    st.iframe(page, height=900)
