"""Intentionally defective acceptance fixture, NOT used by the bridge runtime."""
from decimal import Decimal


def discounted_price(amount: str, discount_fraction: str) -> Decimal:
    """Exercise: a 10% discount on 100 should produce 90, not 110."""
    return Decimal(amount) * (1 + Decimal(discount_fraction))
