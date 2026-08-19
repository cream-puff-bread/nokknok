"""약관 PDF 파싱과 조항 분할.

카드사 상품 안내장에서 텍스트를 뽑아 조항 단위로 자른다.
조항 단위로 자르는 이유는 1단계 파이프라인 때문이다. 조항 하나를 읽고
그 자리에서 규칙을 뽑으면, 규칙과 근거 조항의 대응이 자동으로 확정된다.

문서 전체를 한 번에 LLM에 넣으면 어떤 규칙이 어느 조항에서 나왔는지
알 수 없어 나중에 다시 매칭해야 한다. 그 매칭이 바로 우리가 피하려는 작업이다.
"""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from src.common.exceptions import ClausePipelineError
from src.common.logging import get_logger
from src.rag.models import Clause

logger = get_logger(__name__)

# 조항 시작을 나타내는 패턴. 카드사 문서에서 흔한 형태를 모았다.
_CLAUSE_HEAD = re.compile(
    r"^\s*("
    r"제\s*\d+\s*조"          # 제1조
    r"|[■●○◆▶]\s*\S"         # 불릿 기호
    r"|\d+\.\s*\S"            # 1. 항목
    r"|\(\d+\)\s*\S"          # (1) 항목
    r"|[가-힣]\.\s*\S"        # 가. 항목
    r")",
    re.MULTILINE,
)

# 너무 짧은 조각은 규칙을 담을 수 없다. LLM 호출만 낭비된다.
MIN_CLAUSE_LENGTH = 30
# 너무 긴 조각은 여러 규칙이 섞여 근거 대응이 흐려진다.
MAX_CLAUSE_LENGTH = 1_500

# 혜택 규칙이 있을 법한 조항만 걸러내기 위한 키워드.
# 전체 조항을 LLM에 넣으면 비용과 시간이 몇 배로 늘어난다.
RULE_KEYWORDS: tuple[str, ...] = (
    "실적",
    "할인",
    "적립",
    "제외",
    "한도",
    "이용금액",
    "전월",
    "청구",
    "무이자",
    "혜택",
)


def extract_clauses(pdf_path: Path | str) -> list[Clause]:
    """PDF에서 조항 목록을 추출한다."""
    path = Path(pdf_path)
    if not path.exists():
        raise ClausePipelineError(f"약관 파일을 찾을 수 없습니다: {path.name}")
    if path.suffix.lower() != ".pdf":
        raise ClausePipelineError(f"PDF 파일이 아닙니다: {path.suffix}")

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pypdf 는 다양한 예외를 던진다
        raise ClausePipelineError(f"PDF를 열 수 없습니다: {path.name}") from exc

    clauses: list[Clause] = []
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            # 한 페이지가 깨져도 나머지는 처리한다.
            logger.warning("페이지 %d 텍스트 추출 실패, 건너뜁니다", page_no)
            continue

        for chunk in split_into_clauses(text):
            clauses.append(
                Clause(doc_name=path.name, page_no=page_no, content=chunk)
            )

    if not clauses:
        raise ClausePipelineError(
            f"조항을 추출하지 못했습니다: {path.name} "
            "(스캔 이미지 PDF일 수 있습니다)"
        )

    logger.info("조항 추출 완료 file=%s clauses=%d", path.name, len(clauses))
    return clauses


def split_into_clauses(text: str) -> list[str]:
    """페이지 텍스트를 조항 단위로 자른다."""
    normalized = _normalize(text)
    if not normalized:
        return []

    # 조항 머리 위치를 찾아 그 앞에서 자른다.
    positions = [m.start() for m in _CLAUSE_HEAD.finditer(normalized)]
    if not positions:
        # 머리 패턴이 없으면 문단 단위로 자른다.
        pieces = [p.strip() for p in re.split(r"\n{2,}", normalized)]
    else:
        if positions[0] > 0:
            positions.insert(0, 0)
        pieces = [
            normalized[start:end].strip()
            for start, end in zip(positions, positions[1:] + [len(normalized)])
        ]

    result: list[str] = []
    for piece in pieces:
        if len(piece) < MIN_CLAUSE_LENGTH:
            continue
        result.extend(_split_long(piece))
    return result


def filter_rule_candidates(clauses: list[Clause]) -> list[Clause]:
    """혜택 규칙이 있을 법한 조항만 남긴다.

    약관 대부분은 분실 신고 절차나 개인정보 처리 방침이라 규칙이 없다.
    전부 LLM에 넣으면 비용과 시간이 크게 늘고 429도 나기 쉽다.

    키워드 필터는 재현율을 우선한다. 놓치는 것보다 몇 개 더 넣는 편이 낫다.
    """
    filtered = [c for c in clauses if any(k in c.content for k in RULE_KEYWORDS)]
    logger.info(
        "규칙 후보 필터 %d → %d (%.0f%% 감소)",
        len(clauses),
        len(filtered),
        (1 - len(filtered) / len(clauses)) * 100 if clauses else 0,
    )
    return filtered


# ---------- internal ----------
def _normalize(text: str) -> str:
    """PDF 추출 텍스트의 잡음을 정리한다."""
    # 단어 중간에 들어간 줄바꿈을 없앤다. PDF는 줄 끝마다 개행이 들어간다.
    text = re.sub(r"(?<=[가-힣a-zA-Z0-9,])\n(?=[가-힣a-zA-Z0-9])", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_long(piece: str) -> list[str]:
    """너무 긴 조각을 문장 경계에서 자른다."""
    if len(piece) <= MAX_CLAUSE_LENGTH:
        return [piece]

    sentences = re.split(r"(?<=[.。])\s+", piece)
    chunks: list[str] = []
    buffer = ""

    for sentence in sentences:
        if len(buffer) + len(sentence) > MAX_CLAUSE_LENGTH and buffer:
            chunks.append(buffer.strip())
            buffer = sentence
        else:
            buffer = f"{buffer} {sentence}".strip()

    if buffer:
        chunks.append(buffer.strip())
    return [c for c in chunks if len(c) >= MIN_CLAUSE_LENGTH]
