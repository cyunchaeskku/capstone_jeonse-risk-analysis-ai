"""배점 방식별 민감도 측정.

현행 배점(D 반영본)을 기준으로, 각 설계 변경을 하나씩 되돌렸을 때 등급이 어디로 돌아가는지 잰다.
변경의 기여를 분리해 보여주는 before/after 표가 목적이다. 되돌리는 항목은 넷이다.

  비례 배점    계단 시절 전세가율 79.9%는 0점, 80.3%는 45점. 80.3%와 99.6%도 똑같이 45점이었다.
  R8 가중치    R2와 §1의 동일 부등식인데 25라 단독 fail이 '주의'에 그쳤다.
  unknown 바닥  §0-2는 unknown을 "확인 필요"로 노출하라 하지만 등급 계산에선 pass와 같았다.
  오버라이드 임계  R2-b가 1.0 초과에서만 발동해 전세가율 96.6%가 '위험'에 머물렀다.

규칙 함수는 그대로 쓰고 점수 합산만 바꾼다. 비례 배점에 필요한 비율은 각 규칙이
이미 evidence에 남겨 둔 값(R1 ratio, R2 combined_ratio)을 읽는다.

주의 — 합성 29건의 정답 등급은 '현행 설계 의도대로' 붙인 것이라, 되돌린 스킴에서는 정답도
같이 되돌아가야 한다. 따라서 되돌린 스킴의 합성 등급 지표는 읽지 않는다. 등급 판단의 근거는
실측 4건이고, 합성은 어느 케이스가 설계 변경에 반응하는지 보는 용도다.

더 중요한 한계 — 실측 4건이 전부 정답 `high_risk`다. **안전한 실제 매물이 0건**이라
오탐을 측정할 표본이 없다. 네 변경 모두 엄격해지는 방향이므로 '오탐 0'은 성과가 아니라
표본이 없다는 뜻이다. 대가는 합성 쪽 safe → caution 이동으로만 보인다.

실행: PYTHONPATH=. .venv/bin/python eval/sensitivity.py
"""

import json
import sys
from pathlib import Path

from backend.app.main import _CHECK_WEIGHTS, _COMBINED_OVERRIDE_THRESHOLD, _risk_grade
from backend.app.schemas import ListingCheckResult, RiskAssessRequest
from eval.engine import assess, run_checks

CASES_DIR = Path(__file__).parent / "cases"
DANGEROUS = {"risk", "high_risk"}
BURDEN_CODES = ("deposit_to_market_ratio", "mortgage_ratio", "senior_deposit")  # 담보 여력 3종

PROP_FLOOR = 0.6  # 비례 구간 시작. 이하는 0점
PROP_CEIL = 1.0  # 시세 전액. 이상은 만점


def _prop(ratio: float, weight: int) -> int:
    """PROP_FLOOR~PROP_CEIL 사이를 선형 배점."""
    if ratio <= PROP_FLOOR:
        return 0
    if ratio >= PROP_CEIL:
        return weight
    return round(weight * (ratio - PROP_FLOOR) / (PROP_CEIL - PROP_FLOOR))


def _stepwise(check: ListingCheckResult, weight: int) -> int:
    if check.status == "fail":
        return weight
    if check.status == "warn":
        return weight // 2
    return 0


def score(
    checks: list[ListingCheckResult],
    *,
    proportional: bool = True,
    r8_weight: int = _CHECK_WEIGHTS["senior_deposit"],
    unknown_floor: bool = True,
) -> int:
    """기본값이 곧 현행 설계. kwargs로 개별 변경을 되돌린다."""
    total = 0
    for check in checks:
        weight = r8_weight if check.code == "senior_deposit" else _CHECK_WEIGHTS[check.code]
        if proportional and check.code == "deposit_to_market_ratio":
            ratio = check.evidence.get("ratio")
            total += _prop(ratio, weight) if ratio is not None else 0
        elif proportional and check.code == "mortgage_ratio":
            # R2-b(combined)만 비례화한다. 근저당 단독 비율(R2-a)은 계단 그대로 두고 둘 중 큰 값.
            # combined로 통째로 갈음하면 보증금이 작은 고근저당 물건의 점수가 내려간다.
            combined, alone = check.evidence.get("combined_ratio"), check.evidence.get("ratio")
            if combined is None:
                total += _stepwise(check, weight)
            else:
                step = weight if alone > 0.6 else weight // 2 if alone > 0.4 else 0
                total += max(step, _prop(combined, weight))
        else:
            total += _stepwise(check, weight)

    total = min(total, 100)
    if unknown_floor:
        by_code = {c.code: c.status for c in checks}
        if all(by_code[code] == "unknown" for code in BURDEN_CODES):
            total = max(total, 15)  # 담보 여력을 하나도 못 봤으면 '안전'이라 말하지 않는다
    return total


def overrides(
    checks: list[ListingCheckResult],
    payload: RiskAssessRequest,
    *,
    combined_threshold: float = _COMBINED_OVERRIDE_THRESHOLD,
) -> list[str]:
    """§4-5 복제. 임계만 바꿀 수 있게 열어 둔다."""
    by_code = {c.code: c for c in checks}
    reasons = []
    if by_code["rights_encumbrance"].status == "fail":
        reasons.append("R4")
    if by_code["owner_mismatch"].status == "fail":
        reasons.append("R3")
    if payload.market_price_krw > 0:
        mortgage = by_code["mortgage_ratio"].evidence.get(
            "allocated_mortgage_krw", payload.mortgage_total_krw
        )
        if (mortgage + payload.deposit_krw) / payload.market_price_krw > combined_threshold:
            reasons.append("R2-b")
    return reasons


# (설명, score kwargs, overrides kwargs)
SCHEMES: dict[str, tuple[str, dict, dict]] = {
    "current": ("현행 (D 반영본)", {}, {}),
    "-proportional": ("비례 배점을 계단으로 되돌림", {"proportional": False}, {}),
    "-r8-weight": ("R8 가중치 30→25", {"r8_weight": 25}, {}),
    "-unknown-floor": ("unknown 바닥 제거", {"unknown_floor": False}, {}),
    "-override-90": ("오버라이드 임계 90%→100%", {}, {"combined_threshold": 1.0}),
    "legacy": (
        "D 이전 전체",
        {"proportional": False, "r8_weight": 25, "unknown_floor": False},
        {"combined_threshold": 1.0},
    ),
}


def load_cases() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASES_DIR.rglob("*.json"))]


def main() -> int:
    cases = load_cases()
    graded: dict[str, dict[str, str]] = {}  # scheme -> case_id -> grade

    for name, (_, score_kw, override_kw) in SCHEMES.items():
        graded[name] = {}
        for case in cases:
            payload = RiskAssessRequest(**case["payload"])
            checks = run_checks(payload)
            fired = overrides(checks, payload, **override_kw)
            s = score(checks, **score_kw)
            graded[name][case["case_id"]] = "high_risk" if fired else _risk_grade(s)

    # current가 실제 엔진과 어긋나면 이 스크립트의 복제 로직이 틀린 것이다
    for case in cases:
        if graded["current"][case["case_id"]] != assess(RiskAssessRequest(**case["payload"]))["grade"]:
            print(f"✗ current 불일치: {case['case_id']}")
            return 1

    real = [c for c in cases if c["label_source"] != "synthetic_boundary"]
    synthetic = [c for c in cases if c["label_source"] == "synthetic_boundary"]

    # ── 1) 실측 케이스 등급 이동 ─────────────────────────────────────────
    print("■ 실측 케이스 등급 이동\n")
    width = max(len(c["case_id"]) for c in real) + 2
    header = f"  {'케이스':<{width}} {'정답':<10}" + "".join(f"{n:>16}" for n in SCHEMES)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for case in real:
        row = f"  {case['case_id']:<{width}} {case['expected']['grade']:<10}"
        for name in SCHEMES:
            got = graded[name][case["case_id"]]
            mark = "✓" if got == case["expected"]["grade"] else " "
            row += f"{got + mark:>16}"
        print(row)

    # ── 2) 실측 기준 미탐/오탐 ───────────────────────────────────────────
    print("\n■ 실측 4건 기준 지표 (합성은 정답이 현행 설계에 묶여 있어 제외)\n")
    print(f"  {'스킴':<16} {'설명':<34} {'완전일치':>9} {'미탐':>6} {'오탐':>6}")
    print("  " + "-" * 76)
    for name, (desc, _, _o) in SCHEMES.items():
        exact = miss = alarm = 0
        for case in real:
            want, got = case["expected"]["grade"], graded[name][case["case_id"]]
            exact += want == got
            miss += want in DANGEROUS and got not in DANGEROUS
            alarm += want not in DANGEROUS and got in DANGEROUS
        print(f"  {name:<16} {desc:<34} {f'{exact}/{len(real)}':>9} {miss:>6} {alarm:>6}")

    # ── 3) 합성 케이스 중 등급이 움직인 것 = 라벨 재작성 대상 ────────────
    print("\n■ 되돌렸을 때 등급이 움직이는 합성 케이스\n")
    for name in SCHEMES:
        if name == "current":
            continue
        moved = [
            (c["case_id"], graded["current"][c["case_id"]], graded[name][c["case_id"]])
            for c in synthetic
            if graded["current"][c["case_id"]] != graded[name][c["case_id"]]
        ]
        print(f"  {name} — {len(moved)}건")
        for case_id, before, after in moved:
            print(f"    {case_id:<42} {before} → {after}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
