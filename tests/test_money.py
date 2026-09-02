import pytest

from app.domain.money import (
    MoneyError,
    format_minor,
    major_to_minor,
    normalize_currency,
    validate_amount_minor,
)


def test_major_to_minor_basic():
    amount_minor, currency = major_to_minor("79.99", "inr")

    assert amount_minor == 7999
    assert currency == "INR"


def test_major_to_minor_decimal_string():
    amount_minor, currency = major_to_minor("0.10", "INR")

    assert amount_minor == 10
    assert currency == "INR"


def test_negative_minor_amount_rejected():
    with pytest.raises(MoneyError):
        validate_amount_minor(-1)


def test_boolean_is_not_valid_money():
    with pytest.raises(MoneyError):
        validate_amount_minor(True)


def test_invalid_currency_rejected():
    with pytest.raises(MoneyError):
        normalize_currency("IN")


def test_format_minor():
    assert format_minor(7999, "INR") == "79.99 INR"
