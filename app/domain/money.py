from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Tuple, Union


class MoneyError(ValueError):
    pass


def normalize_currency(currency: str) -> str:
    if not isinstance(currency, str):
        raise MoneyError("currency must be a string")

    normalized = currency.strip().upper()

    if len(normalized) != 3:
        raise MoneyError("currency must be exactly 3 characters")

    if not normalized.isalpha():
        raise MoneyError("currency must contain only letters")

    return normalized


def validate_amount_minor(amount_minor: int) -> int:
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int):
        raise MoneyError("amount_minor must be an integer")

    if amount_minor < 0:
        raise MoneyError("amount_minor cannot be negative")

    return amount_minor


def major_to_minor(
    amount_major: Union[Decimal, str, int],
    currency: str,
) -> Tuple[int, str]:
    normalized_currency = normalize_currency(currency)

    try:
        amount = Decimal(str(amount_major))
    except InvalidOperation as exc:
        raise MoneyError("invalid amount") from exc

    if amount < 0:
        raise MoneyError("amount cannot be negative")

    minor = int(
        (amount * Decimal("100")).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )

    return validate_amount_minor(minor), normalized_currency


def format_minor(amount_minor: int, currency: str) -> str:
    validated_amount = validate_amount_minor(amount_minor)
    normalized_currency = normalize_currency(currency)

    major = Decimal(validated_amount) / Decimal("100")

    return f"{major:.2f} {normalized_currency}"
