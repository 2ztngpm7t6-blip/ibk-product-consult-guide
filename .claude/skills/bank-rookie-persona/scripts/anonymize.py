#!/usr/bin/env python3
"""설문·인터뷰 원자료 가명화.

CSV: 이름·사번·연락처·이메일 같은 식별 열은 지우고, 지점·부서 열은 '지점A'처럼 바꾼다.
모든 셀(또는 텍스트 파일 전체)에서 전화번호·이메일·긴 숫자(사번 등)·'홍길동 대리' 같은 호칭·지점명을 지운다.

사용:
  python anonymize.py 원본.csv --out 가명화.csv
  python anonymize.py 인터뷰메모.txt --out 가명화.txt
  (--keep-cols "열이름,열이름" 으로 지우지 않을 열 지정)
요약은 표준오류로 출력한다. 결과를 눈으로 한 번 더 확인할 것.
"""
import argparse, csv, io, re, sys
from collections import Counter
from pathlib import Path

DROP = re.compile(r"이름|성명|성함|name|사번|직원\s*번호|employee|연락처|전화|휴대|핸드폰|phone|mobile|이메일|메일|e-?mail|주민|생년월일|계좌", re.I)
MAP = re.compile(r"지점|영업점|branch|부서|팀명|소속", re.I)

PHONE = re.compile(r"(?<!\d)(01[016789]|0\d{1,2})[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
LONGNUM = re.compile(r"(?<![\d.])\d{6,}(?![\d.])")
TITLES = "행원|계장|주임|대리|과장|차장|부장|팀장|지점장|센터장|부지점장|선배님|멘토님"
PERSON = re.compile(rf"(?<![가-힣])([가-힣]{{2,4}})\s?({TITLES})(님)?")
GENERIC = {"신입", "선배", "담당", "우리", "다른", "모든", "같은", "그", "여러", "한", "두", "첫", "새"}
BRANCH = re.compile(r"(?<![가-힣])[가-힣A-Za-z0-9]{2,10}(지점|영업점|출장소|금융센터|기업금융센터)")

count = Counter()
branch_map = {}


def branch_alias(name):
    if name not in branch_map:
        branch_map[name] = f"지점{chr(65 + len(branch_map) % 26)}{'' if len(branch_map) < 26 else len(branch_map) // 26}"
    return branch_map[name]


def scrub(text):
    if not text:
        return text
    def sub(rx, rep, key, s):
        n = len(rx.findall(s))
        if n:
            count[key] += n
        return rx.sub(rep, s)
    text = sub(EMAIL, "[이메일]", "이메일", text)
    text = sub(PHONE, "[전화번호]", "전화번호", text)
    text = sub(LONGNUM, "[번호]", "긴 숫자(사번 등)", text)

    def person(m):
        if m.group(1) in GENERIC:
            return m.group(0)
        count["이름+호칭"] += 1
        return "[직원]"
    text = PERSON.sub(person, text)

    def branch(m):
        count["지점명"] += 1
        return branch_alias(m.group(0))
    return BRANCH.sub(branch, text)


def do_csv(src, keep):
    raw = src.read_text(encoding="utf-8-sig")
    rows = list(csv.reader(io.StringIO(raw)))
    if not rows:
        sys.exit("빈 CSV입니다.")
    head = rows[0]
    drop = [i for i, h in enumerate(head) if DROP.search(h) and h not in keep]
    mapc = [i for i, h in enumerate(head) if MAP.search(h) and h not in keep and i not in drop]
    out = []
    for r_i, r in enumerate(rows):
        r = r + [""] * (len(head) - len(r))
        if r_i == 0:
            out.append([h for i, h in enumerate(r) if i not in drop])
            continue
        new = []
        for i, v in enumerate(r):
            if i in drop:
                continue
            new.append(branch_alias(v.strip()) if i in mapc and v.strip() else scrub(v))
        out.append(new)
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(out)
    print(f"지운 열: {', '.join(head[i] for i in drop) or '없음'}", file=sys.stderr)
    print(f"바꾼 열(지점·부서): {', '.join(head[i] for i in mapc) or '없음'}", file=sys.stderr)
    print(f"응답 행 수: {len(rows) - 1}", file=sys.stderr)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", required=True, help="'-'이면 표준출력")
    ap.add_argument("--keep-cols", default="")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    src = Path(a.src)
    keep = {k.strip() for k in a.keep_cols.split(",") if k.strip()}
    if src.suffix.lower() == ".csv":
        result = do_csv(src, keep)
    else:
        result = scrub(src.read_text(encoding="utf-8-sig"))
    if a.out == "-":
        sys.stdout.write(result)
    else:
        Path(a.out).write_text(result, encoding="utf-8")
        print(f"저장: {a.out}", file=sys.stderr)
    for k, v in count.items():
        print(f"지움·바꿈 - {k}: {v}건", file=sys.stderr)
    if branch_map:
        print(f"지점 가명 {len(branch_map)}개 (대응표는 저장하지 않음)", file=sys.stderr)
    print("확인: 자유응답에 남은 이름·별명·특정 사건이 없는지 눈으로 한 번 더 보세요.", file=sys.stderr)


if __name__ == "__main__":
    main()
