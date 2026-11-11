#!/usr/bin/env python3
"""가명화된 설문 CSV를 문항별로 집계한다.

첫 줄은 문항 제목, 한 줄은 응답자 한 명. 복수 선택은 ';'로 구분.
문항 형식은 자동 판별: 1~5 정수만 있으면 척도, ';'가 있으면 복수 선택, 선택지가 적으면 단일 선택, 나머지는 자유응답.
응답자가 5명 미만이면 분포를 내보내지 않는다(개인 식별 방지).

사용:
  python survey_summary.py 가명화.csv --out survey.json
  python survey_summary.py 가명화.csv --out -          (표준출력)
"""
import argparse, csv, io, json, re, sys
from collections import Counter
from pathlib import Path

MIN_N = 5
SKIP = re.compile(r"지점|영업점|부서|소속|팀명|branch", re.I)


def kind_of(vals):
    if all(v.isdigit() and 1 <= int(v) <= 5 for v in vals):
        return "likert"
    if any(";" in v for v in vals):  # 복수 선택: ';'로 나눈 각 선택지가 짧을 때
        opts = [x.strip() for v in vals for x in v.split(";") if x.strip()]
        if opts and sum(len(x) for x in opts) / len(opts) <= 20:
            return "multi"
    if sum(len(v) for v in vals) / len(vals) > 20:  # 긴 문장은 자유응답
        return "text"
    uniq = set(vals)
    if len(uniq) <= 12 and len(uniq) < max(2, len(vals) * 0.8):
        return "single"
    return "text"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--source-id", default="S1")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(Path(a.csv).read_text(encoding="utf-8-sig"))))
    head, body = rows[0], [r for r in rows[1:] if any(c.strip() for c in r)]
    n = len(body)
    out = {"source": a.source_id, "n": n, "questions": []}
    if n < MIN_N:
        out["suppressed"] = True
        print(f"응답자 {n}명: {MIN_N}명 미만이라 분포를 내보내지 않습니다.", file=sys.stderr)
    else:
        for i, q in enumerate(head):
            if SKIP.search(q):  # 소속을 쪼개 보면 소수 응답자가 드러날 수 있어 집계하지 않는다
                print(f"건너뜀(소속 정보): {q}", file=sys.stderr)
                continue
            vals =[r[i].strip() for r in body if i < len(r) and r[i].strip()]
            if not vals:
                continue
            k = kind_of(vals)
            item = {"q": q, "type": k, "answered": len(vals)}
            if k == "likert":
                c = Counter(int(v) for v in vals)
                item["dist"] = {str(s): c.get(s, 0) for s in range(1, 6)}
                item["mean"] = round(sum(int(v) for v in vals) / len(vals), 2)
            elif k == "multi":
                c = Counter(x.strip() for v in vals for x in v.split(";") if x.strip())
                item["dist"] = dict(c.most_common())
            elif k == "single":
                item["dist"] = dict(Counter(vals).most_common())
            else:
                item["texts"] = vals  # 보고서에는 Claude가 고른 짧은 인용만 quotes로 넣는다
            out["questions"].append(item)
        print(f"응답자 {n}명, 문항 {len(out['questions'])}개 집계", file=sys.stderr)
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out == "-":
        sys.stdout.write(text)
    else:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"저장: {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
