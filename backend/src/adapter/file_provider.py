"""파일 업로드 어댑터.

이용자가 카드사에서 직접 내려받은 이용내역 파일을 읽어 정규화한다.
마이데이터 허가 없이도 실제 데이터로 서비스가 동작하는 경로다.

카드사마다 컬럼명이 달라 별칭 표를 두고 매칭한다. PDF 명세서는 카드사별
레이아웃 차이가 커서 MVP 범위에서 제외하고 CSV/Excel만 지원한다.

보안: 업로드 파일은 확장자와 크기를 검증하고, 처리 후 호출부가 즉시 삭제한다.
원본 금융 데이터를 서버에 축적하지 않는다.
"""

from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path

from src.adapter.base import (
    FinancialSnapshot,
    PaymentType,
    Transaction,
)
from src.common.exceptions import DataSourceError, UnsupportedFileFormatError
from src.common.logging import get_logger

logger = get_logger(__name__)

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_SUFFIXES = {".csv", ".tsv"}

# 카드사별 컬럼명 차이를 흡수한다. 소문자·공백제거 후 비교한다.
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "txn_date": ("이용일", "거래일자", "승인일자", "이용일자", "date"),
    "merchant": ("가맹점", "가맹점명", "이용가맹점", "적요", "merchant"),
    "amount": ("이용금액", "승인금액", "금액", "결제금액", "amount"),
    "installment": ("할부", "할부개월", "할부기간", "installment"),
    "category": ("업종", "분류", "카테고리", "category"),
}

# 업종 문자열과 가맹점명을 spend_category.code 로 매핑한다.
# 마스터에 없는 코드를 쓰면 FK 제약에 걸리므로 반드시 여기 값만 사용한다.
#
# 딕셔너리 순서가 곧 우선순위다. 앞에 있는 항목이 먼저 매칭된다.
# 예를 들어 "스타벅스"는 CAFE 와 DINING 양쪽에 걸릴 수 있으므로
# 더 구체적인 CAFE 를 앞에 둔다.
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "CAFE": (
        "카페", "커피", "cafe", "coffee",
        "스타벅스", "투썸", "메가커피", "컴포즈", "이디야", "빽다방",
        "할리스", "폴바셋",
    ),
    "DELIVERY": ("배달", "delivery", "배달의민족", "요기요", "쿠팡이츠"),
    "GROCERY": (
        "마트", "슈퍼", "식료품", "grocery",
        "이마트", "홈플러스", "롯데마트", "더프레시", "노브랜드",
    ),
    "TRANSPORT": (
        "교통", "버스", "지하철", "택시", "transport",
        "카카오t", "티머니", "코레일", "고속도로",
    ),
    "FUEL": ("주유", "충전", "fuel", "오일뱅크", "gs칼텍스"),
    "MEDICAL": (
        # '의원'은 '백종원의원조쌈밥집'처럼 다른 상호에 부분 문자열로 걸린다.
        # 접미사 형태('~의원')로만 매칭되도록 앞 글자를 붙여 구체화한다.
        "병원", "약국", "의료", "medical", "치과", "한의원", "clinic",
        "이비인후과", "정형외과", "피부과", "안과", "내과", "소아과",
    ),
    "EDUCATION": ("학원", "교육", "education", "인강", "온라인강의"),
    "CULTURE": (
        "영화", "공연", "문화", "도서",
        "cgv", "메가박스", "롯데시네마", "예스24", "교보문고", "알라딘",
    ),
    "TELECOM": ("통신", "이동통신", "telecom", "skt", "kt", "lg유플러스"),
    "UTILITY": ("공과금", "전기", "가스", "수도", "관리비"),
    "TAX": ("세금", "국세", "지방세", "tax"),
    "INSURANCE": ("보험", "insurance"),
    "GIFT_CARD": ("상품권", "기프트", "문화상품권"),
    "ONLINE": (
        "온라인", "인터넷", "쇼핑", "online", "이커머스",
        "쿠팡", "네이버페이", "11번가", "지마켓", "무신사", "옥션",
        "올리브영", "티몬", "위메프",
    ),
    # DINING 은 범위가 넓어 마지막에 둔다.
    # 앞선 카테고리에서 걸러지지 않은 음식점만 여기로 온다.
    "DINING": (
        "음식", "식당", "restaurant", "외식", "요식",
        "김밥", "분식", "국밥", "갈비", "고깃집", "치킨", "피자", "버거",
        "본죽", "한솥", "우동", "반점", "쌈밥", "도시락", "맥도날드",
        "롯데리아", "버거킹", "맘스터치",
    ),
}

_DATE_FORMATS = ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y%m%d")


class FileProvider:
    """CSV/TSV 명세서를 읽는 구현체."""

    def __init__(self, account_balance: int = 0, monthly_income: int = 0) -> None:
        # 명세서에는 계좌 잔액과 소득이 없다. 이용자가 화면에서 입력한 값을 받는다.
        self._account_balance = account_balance
        self._monthly_income = monthly_income

    def fetch(self, source_key: str) -> FinancialSnapshot:
        """source_key 는 업로드된 파일 경로다."""
        path = Path(source_key)
        self._validate(path)

        transactions = self._parse(path)
        logger.info("명세서 파싱 완료 rows=%d", len(transactions))

        return FinancialSnapshot(
            account_balance=self._account_balance,
            monthly_income=self._monthly_income,
            income_day=25,
            cards=[],
            transactions=transactions,
            # 반복 결제 탐지는 rag 계층이 아니라 별도 분석 단계에서 수행한다.
            fixed_expenses=[],
        )

    # ---------- internal ----------
    @staticmethod
    def _validate(path: Path) -> None:
        if not path.exists():
            raise DataSourceError(f"파일을 찾을 수 없습니다: {path.name}")
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            raise UnsupportedFileFormatError(path.suffix)
        if path.stat().st_size > MAX_FILE_BYTES:
            raise DataSourceError("파일이 너무 큽니다 (최대 10MB)")

    def _parse(self, path: Path) -> list[Transaction]:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","

        # 카드사 명세서는 CP949 로 내려오는 경우가 많다. UTF-8 실패 시 대체한다.
        # rows/skipped 를 시도마다 새로 시작하는 이유: 잘못된 인코딩도
        # 파일 앞부분 일부는 우연히 유효하게 디코딩될 수 있다. 그 상태로
        # UnicodeDecodeError 가 나서 다음 인코딩으로 넘어가면, 앞서 잘못된
        # 인코딩으로 읽힌 행이 다음 시도의 결과에 그대로 섞여 중복 누적된다.
        for encoding in ("utf-8-sig", "cp949"):
            rows: list[Transaction] = []
            skipped = 0
            try:
                with path.open("r", encoding=encoding, newline="") as fp:
                    reader = csv.DictReader(fp, delimiter=delimiter)
                    if reader.fieldnames is None:
                        raise DataSourceError("헤더를 읽을 수 없습니다")
                    mapping = self._map_columns(reader.fieldnames)
                    for raw in reader:
                        parsed = self._to_transaction(raw, mapping)
                        if parsed is None:
                            skipped += 1
                            continue
                        rows.append(parsed)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise DataSourceError("파일 인코딩을 판별할 수 없습니다")

        if skipped:
            logger.warning("건너뛴 행 %d개 (형식 불일치)", skipped)
        if not rows:
            raise DataSourceError("읽을 수 있는 거래 내역이 없습니다")
        return rows

    @staticmethod
    def _map_columns(fieldnames: list[str]) -> dict[str, str]:
        """실제 컬럼명을 표준 키에 매핑한다."""
        normalized = {re.sub(r"\s+", "", f).lower(): f for f in fieldnames}
        mapping: dict[str, str] = {}

        for key, aliases in _COLUMN_ALIASES.items():
            for alias in aliases:
                if alias.lower() in normalized:
                    mapping[key] = normalized[alias.lower()]
                    break

        required = {"txn_date", "merchant", "amount"}
        missing = required - mapping.keys()
        if missing:
            raise DataSourceError(
                f"필수 컬럼을 찾을 수 없습니다: {', '.join(sorted(missing))}"
            )
        return mapping

    def _to_transaction(
        self, raw: dict[str, str | None], mapping: dict[str, str]
    ) -> Transaction | None:
        """한 행을 변환한다. 변환 불가하면 None 을 반환해 호출부가 건너뛴다.

        예외를 던지지 않는 이유는 명세서에 합계 행이나 빈 행이 섞여 있는 것이
        정상이기 때문이다. 한 행 때문에 전체 파싱이 실패하면 안 된다.
        """
        try:
            txn_date = self._parse_date(raw.get(mapping["txn_date"]))
            amount = self._parse_amount(raw.get(mapping["amount"]))
            merchant = (raw.get(mapping["merchant"]) or "").strip()
        except (ValueError, TypeError):
            return None

        # amount <= 0 은 환불·취소(음수)와 0원 거래를 함께 걸러낸다.
        # 환불을 별도 DTO로 다루지 않고 필터링하는 이유는 _parse_amount 의
        # docstring 참고 — amount는 지출만 표현하는 게 이 서비스의 불변식이다.
        if txn_date is None or amount is None or amount <= 0 or not merchant:
            return None

        months, interest_free = self._parse_installment(
            raw.get(mapping.get("installment", ""))
        )
        if months == 0:
            payment_type = PaymentType.LUMP
        elif interest_free:
            payment_type = PaymentType.INTEREST_FREE
        else:
            payment_type = PaymentType.INSTALLMENT

        return Transaction(
            txn_date=txn_date,
            merchant=merchant,
            amount=amount,
            category=self.classify_category(
                merchant, raw.get(mapping.get("category", ""))
            ),
            payment_type=payment_type,
            installment_months=months,
        )

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value:
            return None
        text = value.strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_amount(value: str | None) -> int | None:
        """금액 문자열을 정수로 변환한다.

        부호를 그대로 유지한다. 카드사 명세서에서 음수는 환불·취소 거래를
        뜻하는데, abs()로 뒤집으면 환불이 지출로 계산되어 실적·잔고가
        부풀려진다. Transaction.amount는 "지출은 양수"가 이 서비스 전체의
        불변식이므로(Transaction.__post_init__, schema.sql의 transaction.amount
        주석 참고) 음수를 DTO에 그대로 담지 않는다 — 호출부(_to_transaction)의
        amount <= 0 필터가 환불 거래를 걸러낸다. 여기서 abs()로 부호를
        지우면 그 필터가 절대 걸리지 않는 죽은 코드가 된다.
        """
        if not value:
            return None
        # 콤마, 원 표기, 공백을 제거한다.
        cleaned = re.sub(r"[^\d\-]", "", value)
        if not cleaned or cleaned == "-":
            return None
        return int(cleaned)

    @staticmethod
    def _parse_installment(value: str | None) -> tuple[int, bool]:
        """할부 개월과 무이자 여부를 반환한다.

        무이자 구분이 중요한 이유는 대부분의 카드가 무이자 할부를
        전월실적에서 제외하기 때문이다. 일반 할부로 잘못 인식하면
        실적이 과대 계산되어 혜택 판정이 틀린다.
        """
        if not value:
            return 0, False

        text = value.strip()
        interest_free = "무이자" in text or "무 이자" in text

        digits = re.sub(r"[^\d]", "", text)
        if not digits:
            # '무이자'만 적히고 개월 수가 없는 경우가 있다.
            # 개월 수를 모르면 할부로 처리할 수 없으므로 일시불로 둔다.
            return 0, False

        months = int(digits)
        # 일시불을 '00' 또는 '1'로 표기하는 카드사가 있다.
        if months <= 1:
            return 0, False
        return months, interest_free

    @staticmethod
    def classify_category(merchant: str, hint: str | None = None) -> str:
        """가맹점명과 업종 문자열로 카테고리를 판별한다.

        반환값은 반드시 spend_category.code 에 존재하는 값이어야 한다.
        판별 실패 시 ETC 로 떨어뜨린다. 임의의 새 코드를 만들면 FK 제약에 걸린다.
        """
        haystack = f"{merchant} {hint or ''}".lower()
        for code, keywords in _CATEGORY_KEYWORDS.items():
            if any(kw.lower() in haystack for kw in keywords):
                return code
        return "ETC"
