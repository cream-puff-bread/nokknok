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

# 최상위 조항 경계. '제N조' 구조가 있는 문서는 이것만 분할 기준으로 쓴다.
# 조 안의 호 번호("1. 2. 3.")는 조의 내부 구조이지 새 조항의 시작이 아니다.
# 예전에는 이 구분이 없어서, 제N조 안에서 호 번호가 줄바꿈 직후에 오면
# _BULLET_HEAD 패턴이 그 줄을 새 조항으로 오인해 한 조를 여러 조각으로
# 쪼갰다(뒤쪽 조각이 MIN_CLAUSE_LENGTH 미달로 유실되는 사고로 이어졌다).
_ARTICLE_HEAD = re.compile(r"^\s*제\s*\d+\s*조", re.MULTILINE)

# '제N조' 구조가 없는 문서에서만 쓰는 폴백 분할 기준.
# 문서 전체가 글머리 기호나 번호 목록으로만 구성된 경우를 위한 것이다.
_BULLET_HEAD = re.compile(
    r"^\s*("
    r"[■●○◆▶]\s*\S"         # 불릿 기호
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
    """페이지 텍스트를 조항 단위로 자른다.

    계층을 인식한다. '제N조' 마커가 있으면 그것만 분할 경계로 쓰고, 조
    내부의 호 번호("1. 2. 3.")는 분할하지 않는다. '제N조' 구조가 아예
    없는 문서(글머리 기호·번호 목록만으로 된 유의사항 등)에서만 그 목록
    자체를 조항 경계로 쓴다.
    """
    normalized = _normalize(text)
    if not normalized:
        return []

    article_positions = [m.start() for m in _ARTICLE_HEAD.finditer(normalized)]
    positions = article_positions or [
        m.start() for m in _BULLET_HEAD.finditer(normalized)
    ]

    if not positions:
        # 머리 패턴이 없으면 문단 단위로 자른다.
        pieces = [p.strip() for p in re.split(r"\n{2,}", normalized) if p.strip()]
    else:
        if positions[0] > 0:
            positions.insert(0, 0)
        pieces = [
            normalized[start:end].strip()
            for start, end in zip(positions, positions[1:] + [len(normalized)])
        ]
        pieces = [p for p in pieces if p]

    result: list[str] = []
    for piece in _merge_short_pieces(pieces):
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
def _merge_short_pieces(pieces: list[str]) -> list[str]:
    """MIN_CLAUSE_LENGTH 미달 조각을 버리지 않고 직전 조각에 합친다.

    예전에는 짧은 조각을 그냥 건너뛰었다. 분할 경계를 잘못 잡아 한 조항이
    쪼개지면(예: 호 번호 앞 줄바꿈을 새 조항 시작으로 오인) 뒤쪽 조각이
    이 길이 미달로 조용히 사라졌고, 그 안의 호(예: 카드 C 제6조 5·6호)가
    LLM에 아예 전달되지 않는 사고로 이어졌다. 텍스트가 사라지는 경로를
    없애기 위해 짧은 조각은 인접 조각에 흡수시킨다.

    맨 앞 조각부터 짧으면(합칠 이전 조각이 없음) 그대로 둔다 — 버리는
    것보다는 짧은 채로 남기는 편이 낫고, 어차피 규칙 키워드가 없으면
    filter_rule_candidates 에서 자연히 걸러진다.
    """
    merged: list[str] = []
    for piece in pieces:
        if merged and len(piece) < MIN_CLAUSE_LENGTH:
            merged[-1] = f"{merged[-1]} {piece}".strip()
        else:
            merged.append(piece)
    return merged


def _normalize(text: str) -> str:
    """PDF 추출 텍스트의 잡음을 정리한다."""
    # 단어 중간에 들어간 줄바꿈을 없앤다. PDF는 줄 끝마다 개행이 들어간다.
    text = re.sub(r"(?<=[가-힣a-zA-Z0-9,])\n(?=[가-힣a-zA-Z0-9])", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_long(piece: str) -> list[str]:
    """너무 긴 조각을 문장 경계에서 자른다.

    마지막 문장이 혼자 남아 MIN_CLAUSE_LENGTH 미달이 되는 경우가 있다.
    여기서도 버리지 않고 직전 조각에 합친다 — split_into_clauses와 같은
    원칙이다.
    """
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
    return _merge_short_pieces(chunks)
