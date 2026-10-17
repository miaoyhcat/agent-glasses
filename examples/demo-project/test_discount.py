import unittest
from decimal import Decimal
from discount import discounted_price


class DiscountAcceptance(unittest.TestCase):
    def test_discount_reduces_price(self):
        self.assertEqual(discounted_price('100','0.10'),Decimal('90.00'))

    def test_zero_discount(self):
        self.assertEqual(discounted_price('42','0'),Decimal('42'))
