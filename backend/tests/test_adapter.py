"""데이터 소스 어댑터 테스트.

카드사마다 명세서 형식이 다르므로 파싱이 그 차이를 흡수하는지,
잘못된 행이 섞여도 전체가 실패하지 않는지 확인한다.
"""

from datetime import date, timedelta

import pytest

from src.adapter.base import (
    ExpenseType,
    FinancialSnapshot,
    FixedExpense,
    PaymentType,
    Transaction,
    TransactionProvider,
)
from src.adapter.file_provider import FileProvider
from src.common.exceptions import DataSourceError, UnsupportedFileFormatError


# ─────────────────────────────────────────────
# DTO
# ─────────────────────────────────────────────
class TestTransaction:
    def test_일시불에_할부개월이_있으면_거부한다(self):
        """DB의 chk_installment 제약과 동일한 검증이다."""
        with pytest.raises(ValueError, match="일시불"):
            Transaction(
                txn_date=date(2026, 8, 1),
                merchant="테스트",
                amount=10_000,
                category="DINING",
                payment_type=PaymentType.LUMP,
                installment_months=3,
            )

    def test_할부에_개월이_없으면_거부한다(self):
        with pytest.raises(ValueError, match="할부 개월"):
            Transaction(
                txn_date=date(2026, 8, 1),
                merchant="테스트",
                amount=10_000,
                category="ONLINE",
                payment_type=PaymentType.INSTALLMENT,
                installment_months=0,
            )

    def test_금액이_0이하면_거부한다(self):
        """amount는 항상 양수라는 불변식을 DTO 자체가 강제한다.

        환불(음수)을 이 DTO로 표현하지 않기로 했으므로(file_provider가
        어댑터 단계에서 걸러낸다), 여기서도 방어한다.
        """
        with pytest.raises(ValueError, match="양수"):
            Transaction(
                txn_date=date(2026, 8, 1),
                merchant="테스트",
                amount=0,
                category="DINING",
                payment_type=PaymentType.LUMP,
            )
        with pytest.raises(ValueError, match="양수"):
            Transaction(
                txn_date=date(2026, 8, 1),
                merchant="테스트",
                amount=-5_000,
                category="DINING",
                payment_type=PaymentType.LUMP,
            )


class TestFixedExpense:
    def test_90일_이상_미사용_구독을_의심_대상으로_본다(self):
        expense = FixedExpense(
            expense_type=ExpenseType.SUBSCRIPTION,
            label="영상 스트리밍",
            amount=17_000,
            charge_day=5,
            last_used_date=date.today() - timedelta(days=120),
        )
        assert expense.unused_suspect is True

    def test_최근_사용한_구독은_대상이_아니다(self):
        expense = FixedExpense(
            expense_type=ExpenseType.SUBSCRIPTION,
            label="음원 스트리밍",
            amount=10_900,
            charge_day=11,
            last_used_date=date.today() - timedelta(days=3),
        )
        assert expense.unused_suspect is False

    def test_할부는_미사용_판정_대상이_아니다(self):
        """할부는 사용 여부와 무관하게 계속 나간다."""
        expense = FixedExpense(
            expense_type=ExpenseType.INSTALLMENT,
            label="노트북 할부",
            amount=145_000,
            charge_day=25,
            last_used_date=None,
        )
        assert expense.unused_suspect is False


class TestFinancialSnapshot:
    def test_가용잔고는_확정지출을_뺀_금액이다(self):
        snapshot = FinancialSnapshot(
            account_balance=2_450_000,
            monthly_income=3_200_000,
            income_day=25,
            fixed_expenses=[
                FixedExpense(ExpenseType.SUBSCRIPTION, "A", 17_000, 5),
                FixedExpense(ExpenseType.LOAN, "B", 180_000, 20),
            ],
        )
        assert snapshot.fixed_total == 197_000
        assert snapshot.available_balance == 2_253_000

    def test_확정지출이_잔고를_넘으면_음수가_된다(self):
        """이미 자금이 부족한 상태를 숨기지 않는다."""
        snapshot = FinancialSnapshot(
            account_balance=100_000,
            monthly_income=3_000_000,
            income_day=25,
            fixed_expenses=[FixedExpense(ExpenseType.LOAN, "대출", 500_000, 20)],
        )
        assert snapshot.available_balance == -400_000


# ─────────────────────────────────────────────
# 파일 어댑터
# ─────────────────────────────────────────────
@pytest.fixture
def csv_file(tmp_path):
    def _make(content: str, name: str = "statement.csv"):
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    return _make


class TestFileProvider:
    def test_표준_컬럼을_파싱한다(self, csv_file):
        path = csv_file(
            "이용일,가맹점,이용금액,할부\n"
            "2026-08-01,스타벅스,5500,일시불\n"
            "2026-08-03,쿠팡,120000,3개월\n"
        )
        snapshot = FileProvider().fetch(str(path))

        assert len(snapshot.transactions) == 2
        assert snapshot.transactions[0].amount == 5_500
        assert snapshot.transactions[1].installment_months == 3
        assert snapshot.transactions[1].payment_type is PaymentType.INSTALLMENT

    def test_다른_카드사_컬럼명도_처리한다(self, csv_file):
        """별칭 표가 카드사별 차이를 흡수하는지 확인한다."""
        path = csv_file(
            "승인일자,이용가맹점,승인금액\n2026-08-05,이마트,45000\n"
        )
        snapshot = FileProvider().fetch(str(path))
        assert snapshot.transactions[0].merchant == "이마트"
        assert snapshot.transactions[0].category == "GROCERY"

    def test_금액_콤마와_원_표기를_제거한다(self, csv_file):
        path = csv_file("이용일,가맹점,이용금액\n2026-08-01,이마트,\"45,000원\"\n")
        snapshot = FileProvider().fetch(str(path))
        assert snapshot.transactions[0].amount == 45_000

    def test_여러_날짜_형식을_지원한다(self, csv_file):
        path = csv_file(
            "이용일,가맹점,이용금액\n"
            "2026.08.01,A식당,10000\n"
            "2026/08/02,B카페,5000\n"
            "20260803,C마트,30000\n"
        )
        snapshot = FileProvider().fetch(str(path))
        assert len(snapshot.transactions) == 3

    def test_잘못된_행은_건너뛰고_나머지는_살린다(self, csv_file):
        """명세서에는 합계 행이나 빈 행이 섞여 있는 것이 정상이다."""
        path = csv_file(
            "이용일,가맹점,이용금액\n"
            "2026-08-01,스타벅스,5500\n"
            ",합계,999999\n"
            "잘못된날짜,이상한행,abc\n"
            "2026-08-03,이마트,45000\n"
        )
        snapshot = FileProvider().fetch(str(path))
        assert len(snapshot.transactions) == 2

    def test_필수_컬럼이_없으면_거부한다(self, csv_file):
        path = csv_file("날짜없음,금액없음\n1,2\n")
        with pytest.raises(DataSourceError, match="필수 컬럼"):
            FileProvider().fetch(str(path))

    def test_지원하지_않는_확장자를_거부한다(self, tmp_path):
        path = tmp_path / "statement.exe"
        path.write_text("악성", encoding="utf-8")
        with pytest.raises(UnsupportedFileFormatError):
            FileProvider().fetch(str(path))

    def test_읽을_수_있는_행이_없으면_거부한다(self, csv_file):
        path = csv_file("이용일,가맹점,이용금액\n,,\n")
        with pytest.raises(DataSourceError, match="거래 내역이 없습니다"):
            FileProvider().fetch(str(path))

    def test_음수_금액은_환불로_보고_필터링한다(self, csv_file):
        """실제 사고 재현: abs()로 부호를 지우면 환불이 지출로 뒤집혀
        실적·잔고 계산에 그대로 섞여 들어갔다. 지금은 필터링돼야 한다.
        """
        path = csv_file(
            "이용일,가맹점,이용금액\n"
            "2026-08-01,스타벅스,5000\n"
            "2026-08-02,이마트,-30000\n"  # 환불
            "2026-08-03,쿠팡,12000\n"
        )
        snapshot = FileProvider().fetch(str(path))

        assert len(snapshot.transactions) == 2
        dates = [t.txn_date.isoformat() for t in snapshot.transactions]
        # 환불 거래가 abs()로 뒤집혀 30000 지출로 남으면 안 된다.
        assert "2026-08-02" not in dates
        assert all(t.amount > 0 for t in snapshot.transactions)

    def test_인코딩_재시도_시_이전_시도의_행이_섞이지_않는다(self, tmp_path):
        """실제 사고 재현.

        utf-8-sig로 열면 파일 앞부분(내부 버퍼 크기 이내)은 우연히
        디코딩에 성공해 rows에 먼저 담긴다. 그러다 한글이 CP949 바이트로
        나오는 지점에서 UnicodeDecodeError가 나 cp949로 재시도한다.
        rows를 시도마다 리셋하지 않으면, 실패한 utf-8-sig 시도에서 이미
        담긴 행이 성공한 cp949 결과에 중복으로 섞인다.

        버퍼 경계를 확실히 넘기기 위해 순수 ASCII 행을 충분히 채운 뒤
        마지막에 한글 행을 하나 둔다(직접 확인: 400행 정도면 utf-8-sig가
        약 295행까지 성공적으로 디코딩한 뒤에야 실패한다).
        """
        lines = ["date,merchant,amount"]
        for i in range(400):
            lines.append(f"2026-08-01,TestShop{i},{1000 + i}")
        lines.append("2026-08-02,스타벅스,4500")
        content = "\n".join(lines) + "\n"

        path = tmp_path / "statement.csv"
        path.write_bytes(content.encode("cp949"))

        snapshot = FileProvider().fetch(str(path))

        # ASCII 400건 + 한글 1건. 리셋이 안 되면 실패한 utf-8-sig 시도에서
        # 담긴 앞부분 행이 cp949 재시도 결과에 겹쳐 더 많이 나온다.
        assert len(snapshot.transactions) == 401
        merchants = [t.merchant for t in snapshot.transactions]
        assert merchants.count("TestShop0") == 1
        assert merchants.count("스타벅스") == 1


class TestCategoryClassification:
    """분류 결과는 반드시 spend_category 마스터에 있는 코드여야 한다."""

    VALID = {
        "ALL", "DINING", "CAFE", "DELIVERY", "GROCERY", "ONLINE", "TRANSPORT",
        "FUEL", "MEDICAL", "EDUCATION", "CULTURE", "TELECOM", "UTILITY",
        "TAX", "INSURANCE", "GIFT_CARD", "SUBSCRIPTION", "ETC",
    }

    @pytest.mark.parametrize(
        "merchant,expected",
        [
            ("스타벅스 강남점", "CAFE"),
            ("이마트 성수점", "GROCERY"),
            ("김밥천국", "DINING"),
            ("카카오T 택시", "TRANSPORT"),
            ("쿠팡 온라인주문", "ONLINE"),
            ("알수없는가맹점XYZ", "ETC"),
        ],
    )
    def test_가맹점명으로_분류한다(self, merchant, expected):
        assert FileProvider.classify_category(merchant) == expected

    def test_어떤_입력이든_마스터_코드를_반환한다(self):
        """임의 코드를 만들면 FK 제약에 걸린다."""
        for merchant in ["", "!!!", "12345", "한글만", "MixedCase123"]:
            assert FileProvider.classify_category(merchant) in self.VALID


# ─────────────────────────────────────────────
# 프로토콜
# ─────────────────────────────────────────────
def test_구현체가_프로토콜을_만족한다():
    """상위 계층이 구현체를 구분하지 않아도 되는지 확인한다."""
    assert isinstance(FileProvider(), TransactionProvider)


class TestCategoryFalsePositives:
    """부분 문자열 매칭의 오탐을 방지한다.

    실제로 '백종원의원조쌈밥집'이 '의원' 때문에 MEDICAL 로 분류되는
    버그가 있었다. 키워드를 추가할 때 이 케이스가 깨지지 않는지 확인한다.
    """

    @pytest.mark.parametrize(
        "merchant,expected",
        [
            ("백종원의원조쌈밥집", "DINING"),
            ("연세이비인후과", "MEDICAL"),
            ("미소치과", "MEDICAL"),
            ("온누리약국", "MEDICAL"),
            ("역전우동", "DINING"),
            ("홍콩반점", "DINING"),
            ("교통카드 충전", "TRANSPORT"),
        ],
    )
    def test_유사_문자열에_오분류되지_않는다(self, merchant, expected):
        assert FileProvider.classify_category(merchant) == expected


class TestInterestFreeDetection:
    """무이자 할부는 대부분의 카드에서 전월실적에 잡히지 않는다.

    일반 할부로 잘못 인식하면 실적이 과대 계산되어 혜택 판정이 틀린다.
    """

    @pytest.mark.parametrize(
        "raw,months,ptype",
        [
            ("일시불", 0, PaymentType.LUMP),
            ("3개월", 3, PaymentType.INSTALLMENT),
            ("무이자 3개월", 3, PaymentType.INTEREST_FREE),
            ("3개월무이자", 3, PaymentType.INTEREST_FREE),
            ("00", 0, PaymentType.LUMP),
            ("1", 0, PaymentType.LUMP),
            ("", 0, PaymentType.LUMP),
        ],
    )
    def test_할부_표기를_해석한다(self, csv_file, raw, months, ptype):
        path = csv_file(
            f"이용일,가맹점,이용금액,할부\n2026-08-01,쿠팡,120000,{raw}\n"
        )
        txn = FileProvider().fetch(str(path)).transactions[0]
        assert txn.installment_months == months
        assert txn.payment_type is ptype
