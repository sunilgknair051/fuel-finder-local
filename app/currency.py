"""Decimal-based display currency conversion."""

from decimal import Decimal, ROUND_HALF_UP


def convert_price(eur_price: Decimal, rate: Decimal) -> Decimal:
    return (eur_price * rate).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
