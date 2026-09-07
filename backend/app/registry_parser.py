import re
import zlib
from dataclasses import dataclass, field


_OBJ_RE = re.compile(rb"(\d+)\s+0\s+obj(.*?)endobj", re.DOTALL)
_HEX_TEXT_RE = re.compile(r"<([0-9A-Fa-f]+)>\s*Tj")
_LITERAL_TEXT_RE = re.compile(r"\((.*?)\)\s*Tj", re.DOTALL)
_MAX_CLAIM_RE = re.compile(r"채권최고액\s*(?:금\s*)?([0-9,]+)\s*(?:원)?")
# 근저당 항목 끝에 붙는 "공동담보목록  제2013-432호" 참조.
_COLLATERAL_REF_RE = re.compile(r"공동담보목록\s*제\s*([0-9]{4}-[0-9]+)\s*호")
# 목록 본문은 목록번호만 적힌 줄로 시작한다. 위 참조 문구와 구분하려고 줄 전체를 맞춘다.
_COLLATERAL_BODY_RE = re.compile(r"(?m)^\s*([0-9]{4}-[0-9]+)\s*$")
# 목록 본문의 물건 한 건. 매 페이지 머리글의 "[집합건물] ... 제201호"와 겹치지 않도록
# 대괄호까지 포함해 맞춘다. 집합건물 대지도 [토지]로 한 건 잡힌다.
_COLLATERAL_PROPERTY_RE = re.compile(r"\[건물\]|\[토지\]")


@dataclass
class RegistryMaxClaimMatch:
    amount_krw: int
    raw_text: str
    page: int | None = None
    collateral_list_no: str | None = None
    # 공동담보로 묶인 물건 수. 단독담보면 1.
    shared_property_count: int = 1


@dataclass
class RegistryParseResult:
    max_claim_amount_krw: int | None
    max_claim_amounts: list[RegistryMaxClaimMatch] = field(default_factory=list)
    text: str = ""


def parse_registry_pdf(pdf_bytes: bytes) -> RegistryParseResult:
    text = _extract_text_with_pymupdf(pdf_bytes) or _extract_text_with_pdf_cmap(pdf_bytes)
    matches = _extract_max_claim_amounts(text)
    _attach_shared_collateral(matches, text)
    return RegistryParseResult(
        max_claim_amount_krw=matches[-1].amount_krw if matches else None,
        max_claim_amounts=matches,
        text=text,
    )


def _extract_text_with_pymupdf(pdf_bytes: bytes) -> str:
    try:
        import fitz  # type: ignore
    except ImportError:
        return ""

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return ""

    pages: list[str] = []
    for index, page in enumerate(document, start=1):
        text = page.get_text("text").strip()
        if text:
            pages.append(f"[page {index}]\n{text}")
    return "\n".join(pages).strip()


def _extract_text_with_pdf_cmap(pdf_bytes: bytes) -> str:
    streams = _read_pdf_streams(pdf_bytes)
    to_unicode_refs = _find_to_unicode_refs(pdf_bytes)
    cmap = _build_cmap(streams, to_unicode_refs)
    if not cmap:
        return ""

    page_content_refs = _find_page_content_refs(pdf_bytes)
    pages: list[str] = []
    for page_number, ref in enumerate(page_content_refs, start=1):
        content = streams.get(ref, b"").decode("latin1", errors="ignore")
        lines = _decode_text_items(content, cmap)
        if lines:
            pages.append(f"[page {page_number}]\n" + "\n".join(lines))
    return "\n".join(pages).strip()


def _read_pdf_streams(pdf_bytes: bytes) -> dict[int, bytes]:
    streams: dict[int, bytes] = {}
    for match in _OBJ_RE.finditer(pdf_bytes):
        obj_id = int(match.group(1))
        body = match.group(2)
        stream_marker = body.find(b"stream")
        endstream_marker = body.find(b"endstream")
        if stream_marker < 0 or endstream_marker < 0:
            continue

        header = body[:stream_marker]
        stream_start = stream_marker + len(b"stream")
        if body[stream_start : stream_start + 2] == b"\r\n":
            stream_start += 2
        elif body[stream_start : stream_start + 1] in (b"\r", b"\n"):
            stream_start += 1
        stream = body[stream_start:endstream_marker].rstrip(b"\r\n")
        if b"FlateDecode" in header:
            try:
                stream = zlib.decompress(stream)
            except zlib.error:
                continue
        streams[obj_id] = stream
    return streams


def _find_to_unicode_refs(pdf_bytes: bytes) -> list[int]:
    refs: list[int] = []
    for match in re.finditer(rb"/ToUnicode\s+(\d+)\s+0\s+R", pdf_bytes):
        refs.append(int(match.group(1)))
    return refs


def _build_cmap(streams: dict[int, bytes], to_unicode_refs: list[int]) -> dict[int, str]:
    cmap: dict[int, str] = {}
    for ref in to_unicode_refs:
        text = streams.get(ref, b"").decode("latin1", errors="ignore")
        for line in text.splitlines():
            values = re.findall(r"<([0-9A-Fa-f]+)>", line)
            if len(values) != 3:
                continue
            start, end, target = (int(value, 16) for value in values)
            for code in range(start, end + 1):
                cmap[code] = chr(target + code - start)
    return cmap


def _find_page_content_refs(pdf_bytes: bytes) -> list[int]:
    refs: list[int] = []
    for match in _OBJ_RE.finditer(pdf_bytes):
        body = match.group(2)
        if b"/Type /Page" not in body or b"/Contents" not in body:
            continue
        ref_match = re.search(rb"/Contents\s+(\d+)\s+0\s+R", body)
        if ref_match:
            refs.append(int(ref_match.group(1)))
    return refs


def _decode_text_items(content: str, cmap: dict[int, str]) -> list[str]:
    items: list[tuple[float, float, str]] = []
    for block in re.findall(r"BT\n(.*?)\nET", content, re.DOTALL):
        position = re.search(r"([-0-9.]+)\s+([-0-9.]+)\s+Td", block)
        if not position:
            continue
        x = float(position.group(1))
        y = float(position.group(2))
        for hex_text in _HEX_TEXT_RE.findall(block):
            decoded = _decode_hex_text(hex_text, cmap).strip()
            if decoded:
                items.append((y, x, decoded))
        for literal_text in _LITERAL_TEXT_RE.findall(block):
            decoded = _decode_literal_text(literal_text, cmap).strip()
            if decoded:
                items.append((y, x, decoded))

    lines: list[str] = []
    for _, _, text in sorted(items, key=lambda item: (-item[0], item[1])):
        lines.append(text)
    return lines


def _decode_hex_text(hex_text: str, cmap: dict[int, str]) -> str:
    if len(hex_text) % 4 != 0:
        return ""
    chars = []
    for index in range(0, len(hex_text), 4):
        code = int(hex_text[index : index + 4], 16)
        chars.append(cmap.get(code, ""))
    return "".join(chars)


def _decode_literal_text(literal_text: str, cmap: dict[int, str]) -> str:
    raw = literal_text.encode("latin1", errors="ignore").decode("unicode_escape").encode("latin1")
    chars = []
    for index in range(0, len(raw) - 1, 2):
        code = raw[index] * 256 + raw[index + 1]
        chars.append(cmap.get(code, ""))
    return "".join(chars)


def _extract_max_claim_amounts(text: str) -> list[RegistryMaxClaimMatch]:
    matches: list[RegistryMaxClaimMatch] = []
    current_page: int | None = None
    for line in text.splitlines():
        page_match = re.fullmatch(r"\[page\s+(\d+)\]", line.strip())
        if page_match:
            current_page = int(page_match.group(1))
            continue

        for match in _MAX_CLAIM_RE.finditer(line):
            amount_text = match.group(1).replace(",", "")
            matches.append(
                RegistryMaxClaimMatch(
                    amount_krw=int(amount_text),
                    raw_text=line.strip(),
                    page=current_page,
                )
            )
    return matches


def _count_collateral_properties(text: str) -> dict[str, int]:
    """공동담보목록별 물건 수를 센다."""
    bodies = [(match.group(1), match.start()) for match in _COLLATERAL_BODY_RE.finditer(text)]
    counts: dict[str, int] = {}
    for index, (list_no, start) in enumerate(bodies):
        end = bodies[index + 1][1] if index + 1 < len(bodies) else len(text)
        counts[list_no] = len(_COLLATERAL_PROPERTY_RE.findall(text[start:end]))
    return counts


def _attach_shared_collateral(matches: list[RegistryMaxClaimMatch], text: str) -> None:
    """각 채권최고액에 공동담보목록 번호와 물건 수를 붙인다.

    목록 참조는 근저당 항목 끝에 오므로, 채권최고액 위치 뒤에 처음 나오는 참조를
    그 근저당의 것으로 본다. 참조가 없으면 단독담보(1건)다.
    """
    if not matches:
        return

    refs = [(match.group(1), match.start()) for match in _COLLATERAL_REF_RE.finditer(text)]
    if not refs:
        return
    counts = _count_collateral_properties(text)

    used: set[int] = set()
    for item in matches:
        position = text.find(item.raw_text)
        if position < 0:
            continue
        for index, (list_no, ref_start) in enumerate(refs):
            if index in used or ref_start < position:
                continue
            used.add(index)
            item.collateral_list_no = list_no
            # 목록 본문이 잘려 0건으로 세지면 배분이 무한대가 되므로 단독담보로 되돌린다.
            item.shared_property_count = max(counts.get(list_no, 1), 1)
            break
