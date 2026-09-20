"""케이스 파일 스키마 검증. 라벨링 오류를 평가 실행 전에 잡는다.

실행: PYTHONPATH=. .venv/bin/python eval/validate.py
"""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

from backend.app.schemas import RiskAssessRequest

CASES_DIR = Path(__file__).parent / "cases"
GRADES = {"safe", "caution", "risk", "high_risk"}
STATUSES = {"pass", "warn", "fail", "unknown"}
LABEL_SOURCES = {"auction_outcome", "expert_judgment", "synthetic_boundary"}
CHECK_CODES = {
    "deposit_to_market_ratio",
    "mortgage_ratio",
    "owner_mismatch",
    "rights_encumbrance",
    "residential_use",
    "illegal_building",
    "duplicate_contract",
    "senior_deposit",
}


def check_case(path: Path) -> list[str]:
    errors = []
    try:
        case = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"JSON 파싱 실패: {exc}"]

    for field in ("case_id", "description", "label_source", "payload", "expected"):
        if field not in case:
            errors.append(f"필수 필드 누락: {field}")
    if errors:
        return errors

    if case["case_id"] != path.stem:
        errors.append(f"case_id({case['case_id']})가 파일명({path.stem})과 다름")
    if case["label_source"] not in LABEL_SOURCES:
        errors.append(f"label_source 값이 잘못됨: {case['label_source']}")

    # payload가 실제로 엔진에 들어갈 수 있어야 한다. 이게 이 스크립트의 핵심 검사.
    try:
        RiskAssessRequest(**case["payload"])
    except ValidationError as exc:
        for err in exc.errors():
            errors.append(f"payload.{'.'.join(map(str, err['loc']))}: {err['msg']}")

    expected = case["expected"]
    if expected.get("grade") not in GRADES:
        errors.append(f"expected.grade 값이 잘못됨: {expected.get('grade')}")
    if not expected.get("rationale"):
        errors.append("expected.rationale 비어 있음")

    checks = expected.get("checks", {})
    for code, status in checks.items():
        if code not in CHECK_CODES:
            errors.append(f"expected.checks에 모르는 코드: {code}")
        elif status is not None and status not in STATUSES:
            errors.append(f"expected.checks.{code} 값이 잘못됨: {status}")
    for code in CHECK_CODES - set(checks):
        errors.append(f"expected.checks에 {code} 누락 (모르면 null로 명시)")

    if case["label_source"] != "synthetic_boundary" and "provenance" not in case:
        errors.append("실제 사례인데 provenance 없음")

    return errors


def main() -> int:
    paths = sorted(CASES_DIR.rglob("*.json"))
    if not paths:
        print(f"케이스 없음: {CASES_DIR}")
        return 1

    failed = 0
    by_source: dict[str, int] = {}
    by_grade: dict[str, int] = {}
    labeled = 0

    for path in paths:
        errors = check_case(path)
        rel = path.relative_to(CASES_DIR)
        if errors:
            failed += 1
            print(f"✗ {rel}")
            for err in errors:
                print(f"    {err}")
            continue
        case = json.loads(path.read_text(encoding="utf-8"))
        by_source[case["label_source"]] = by_source.get(case["label_source"], 0) + 1
        grade = case["expected"]["grade"]
        by_grade[grade] = by_grade.get(grade, 0) + 1
        labeled += sum(1 for v in case["expected"]["checks"].values() if v is not None)
        print(f"✓ {rel}")

    print(f"\n케이스 {len(paths)}건, 실패 {failed}건")
    print(f"출처별 {by_source}")
    print(f"정답등급 분포 {by_grade}")
    print(f"규칙 단위 라벨 {labeled}개 (전체 가능 {len(paths) * len(CHECK_CODES)}개)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
