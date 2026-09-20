"""규칙 엔진 정확도 측정.

두 층으로 나눠 집계한다.
  1) 규칙별 status 정확도 — 케이스 1건이 최대 8개 판정을 주므로 표본이 8배가 된다
  2) 등급 이진 정확도 — 4x4 혼동행렬은 30건으로 못 채우므로 안전/위험으로 접는다

미탐(위험한데 안전하다고 함)을 오탐과 분리해 센다. 전자가 훨씬 치명적이다.

실행: PYTHONPATH=. .venv/bin/python eval/run_rules_eval.py
"""

import json
import sys
from pathlib import Path

from backend.app.schemas import RiskAssessRequest
from eval.engine import assess

CASES_DIR = Path(__file__).parent / "cases"
DANGEROUS = {"risk", "high_risk"}  # 이진화 기준: 사용자에게 "위험하다"고 말한 등급

# 회귀 기준선. 현재 성적이고, 아래로 내려가면 CI가 막는다.
# 올라가면 같이 올려야 다음 회귀를 잡는다. 미탐은 늘어나는 것 자체를 막는다.
BASELINE_RULE_OK = 249
BASELINE_GRADE_EXACT = 31
BASELINE_MAX_MISSES = 0


def load_cases() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASES_DIR.rglob("*.json"))
    ]


def main() -> int:
    cases = load_cases()
    if not cases:
        print("케이스 없음")
        return 1

    grade_rows = []
    rule_hit: dict[str, list[int]] = {}
    rule_errors: list[tuple[str, str, str, str]] = []

    for case in cases:
        actual = assess(RiskAssessRequest(**case["payload"]))
        exp = case["expected"]
        grade_rows.append((case["case_id"], case["label_source"], exp["grade"], actual["grade"]))

        for code, expected_status in exp["checks"].items():
            if expected_status is None:  # 정답을 모르는 항목은 집계에서 뺀다
                continue
            got = actual["checks"].get(code)
            tally = rule_hit.setdefault(code, [0, 0])
            tally[1] += 1
            if got == expected_status:
                tally[0] += 1
            else:
                rule_errors.append((case["case_id"], code, expected_status, got))

    # ── 1) 규칙별 status 정확도 ──────────────────────────────────────────
    print("■ 규칙별 판정 정확도\n")
    print(f"  {'규칙':<26} {'정답/전체':>10} {'정확도':>8}")
    print("  " + "-" * 46)
    total_ok = total_n = 0
    for code in sorted(rule_hit):
        ok, n = rule_hit[code]
        total_ok += ok
        total_n += n
        print(f"  {code:<26} {f'{ok}/{n}':>10} {ok / n:>7.1%}")
    print("  " + "-" * 46)
    print(f"  {'합계':<26} {f'{total_ok}/{total_n}':>10} {total_ok / total_n:>7.1%}")

    if rule_errors:
        print(f"\n  불일치 {len(rule_errors)}건:")
        for case_id, code, want, got in rule_errors:
            print(f"    {case_id:<40} {code:<26} 정답 {want} → 실제 {got}")

    # ── 2) 등급 정확도 ───────────────────────────────────────────────────
    exact = sum(1 for _, _, want, got in grade_rows if want == got)
    print(f"\n■ 등급 정확도\n\n  4단계 완전일치 {exact}/{len(grade_rows)} ({exact / len(grade_rows):.1%})")

    tp = fp = fn = tn = 0
    misses, false_alarms = [], []
    for case_id, _, want, got in grade_rows:
        want_d, got_d = want in DANGEROUS, got in DANGEROUS
        if want_d and got_d:
            tp += 1
        elif want_d and not got_d:
            fn += 1
            misses.append((case_id, want, got))
        elif not want_d and got_d:
            fp += 1
            false_alarms.append((case_id, want, got))
        else:
            tn += 1

    print(f"\n  이진 혼동행렬 (위험 = risk·high_risk)\n")
    print(f"    {'':12} {'실제 위험':>10} {'실제 안전':>10}")
    print(f"    {'정답 위험':12} {tp:>10} {fn:>10}   ← 미탐 {fn}건")
    print(f"    {'정답 안전':12} {fp:>10} {tn:>10}   ← 오탐 {fp}건")

    recall = tp / (tp + fn) if tp + fn else float("nan")
    precision = tp / (tp + fp) if tp + fp else float("nan")
    print(f"\n    재현율(미탐 없음) {recall:.1%}   정밀도 {precision:.1%}")

    if misses:
        print(f"\n  ⚠ 미탐 — 위험한데 안전하다고 함:")
        for case_id, want, got in misses:
            print(f"    {case_id:<40} 정답 {want} → 실제 {got}")
    if false_alarms:
        print(f"\n  오탐 — 안전한데 위험하다고 함:")
        for case_id, want, got in false_alarms:
            print(f"    {case_id:<40} 정답 {want} → 실제 {got}")

    # ── 3) 등급 불일치 전체 ──────────────────────────────────────────────
    mismatched = [r for r in grade_rows if r[2] != r[3]]
    if mismatched:
        print(f"\n■ 등급 불일치 {len(mismatched)}건 (이진화하면 같은 쪽인 것 포함)\n")
        for case_id, source, want, got in mismatched:
            print(f"  {case_id:<40} [{source:<18}] 정답 {want:<10} → 실제 {got}")

    # ── 4) 회귀 판정 ─────────────────────────────────────────────────────
    regressions = []
    if total_ok < BASELINE_RULE_OK:
        regressions.append(f"규칙별 판정 {total_ok} < 기준선 {BASELINE_RULE_OK}")
    if exact < BASELINE_GRADE_EXACT:
        regressions.append(f"등급 완전일치 {exact} < 기준선 {BASELINE_GRADE_EXACT}")
    if fn > BASELINE_MAX_MISSES:
        regressions.append(f"미탐 {fn}건 > 허용 {BASELINE_MAX_MISSES}건")

    if regressions:
        print("\n✗ 회귀 발생")
        for line in regressions:
            print(f"    {line}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
