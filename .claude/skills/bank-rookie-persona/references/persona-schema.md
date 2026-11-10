# persona.json 형식 (`render_report.py` 입력)

- 근거가 필요한 항목은 모두 `{"text": "...", "src": ["D1","S1"]}` 꼴로 쓴다.
- `conf`(신뢰도)는 쓰지 않아도 된다. 스크립트가 `src`로 계산한다.
- 낮추고 싶을 때만 `"conf": "추정"`처럼 적는다. 계산값보다 높게 적으면 경고가 난다.
- 서로 다른 출처가 어긋나면 `"conflict": "설문은 ~, 현장의견은 ~"`를 적는다. 보고서에 불일치 표시가 붙는다.

```json
{
  "meta": {
    "bank": "예시은행",
    "bank_type": "지방은행",
    "role": "개인금융 창구",
    "author": "인사부 연수팀",
    "date": "2026-11-10",
    "scope": "2025~2026년 입행, 영업점 배치자",
    "training": "집합연수 4주 후 영업점 배치, 6개월 멘토링",
    "brand_color": "#1f3a5f",
    "note": "교육 설계 참고용 분석"
  },
  "sources": [
    {"id": "D1", "type": "데이터", "title": "개인 수신상품 목록", "detail": "상품 32개, 2026-10 기준"},
    {"id": "S1", "type": "설문", "title": "신입행원 설문", "n": 24, "detail": "2026-10 실시"},
    {"id": "P1", "type": "공개자료", "title": "채용 공고·인재상", "url": "https://...", "checked": "2026-11-10"},
    {"id": "F1", "type": "현장의견", "title": "연수 담당자 문답", "detail": "과장급"}
  ],
  "persona": {
    "name": "서윤(가명)",
    "age": 26,
    "headline": "배치 1개월 차, 상품은 외웠는데 고객 앞에서 꼬이는 신입",
    "background": [{"text": "상경계 전공, 은행 인턴 경험", "src": ["S1", "F1"]}],
    "knows": [{"text": "...", "src": ["S1"]}],
    "gaps": [{"text": "...", "src": ["D1", "S1"]}],
    "worries": [{"text": "...", "src": ["S1"]}],
    "frequent_questions": [{"text": "...", "src": ["S1", "F1"]}],
    "critical_mistakes": [{"text": "...", "src": ["D1", "F1"]}],
    "learning": [{"text": "하루 30분, 요약 카드·대화 예시 선호", "src": ["S1"]}]
  },
  "stages": [
    {"lv": "Lv1", "when": "입행 1주(연수)", "quote": "신입이 할 법한 말", "goal": "...", "scope": "...", "practice": "...", "exit": "다음 단계 기준", "src": ["F1"]}
  ],
  "difficulty_map": [
    {"area": "상품 지식", "score": 4.1, "risk": "높음", "by_stage": [5, 4, 3, 2, 2], "note": "...", "src": ["S1"]}
  ],
  "findings": [
    {"title": "보호 체계가 다른 상품 9개", "text": "...", "src": ["D1"]}
  ],
  "survey": "survey_summary.py 출력 JSON을 그대로 넣는다(선택)",
  "quotes": [{"text": "가명화된 자유응답 인용", "src": ["S1"]}],
  "proposals": [
    {"priority": 1, "stage": "Lv2", "need": "...", "proposal": "...", "format": "요약 카드 + 롤플레이", "src": ["S1", "D1"]}
  ],
  "open_questions": ["아직 확인하지 못한 것, 다음에 모을 자료"]
}
```

필드 설명:
- `risk`: `높음`, `중간`, `낮음` 중 하나
- `score`, `by_stage`: 1~5. 높을수록 어렵다.
- `by_stage`: 길이가 `stages` 수와 같아야 한다.
- `survey`의 `n`이 5 미만이면 분포 그래프를 그리지 않는다.
- `quotes`는 `survey.n`이 5 이상일 때만 표시한다.
