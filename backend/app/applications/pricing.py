"""Versioned demonstration pricing; never a real bank credit policy."""
from decimal import Decimal, ROUND_HALF_UP

RULES_VERSION = 'demo-v1'


def product_kind(product):
    name = product.name.lower()
    if 'экспресс' in name:
        return 'urgent'
    if 'оборот' in name:
        return 'working_capital'
    if 'развит' in name or 'инвест' in name:
        return 'investment'
    return 'other'


def calculate_quote(products, amount: Decimal, months: int, category: str, *, automatic=True):
    eligible = [p for p in products if p.min_amount <= amount <= p.max_amount and p.min_term_months <= months <= p.max_term_months]
    if not eligible:
        return None
    preferred = [p for p in eligible if product_kind(p) == category] if category != 'other' else []
    candidates = preferred or eligible
    amount_extra = Decimal('0') if amount <= 1_000_000 else Decimal('0.5') if amount <= 5_000_000 else Decimal('1')
    term_extra = Decimal('0') if months <= 12 else Decimal('0.5') if months <= 36 else Decimal('1')
    product = min(candidates, key=lambda p: (p.interest_rate + amount_extra + term_extra, str(p.id)))
    rate = (product.interest_rate + amount_extra + term_extra).quantize(Decimal('.01'))
    monthly = rate / Decimal('1200')
    payment = amount / months if monthly == 0 else amount * monthly / (1 - (1 + monthly) ** (-months))
    total = payment * months
    cash = lambda value: str(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    reason = 'Продукт соответствует цели, сумме и сроку заявки.' if preferred else 'Выбран доступный продукт с минимальной расчётной ставкой для этой суммы и срока.'
    if category != 'other' and not preferred:
        reason += ' Продукт выбранной категории не подходит по сумме или сроку; предложена альтернатива.'
    return product, {
        'rules_version': RULES_VERSION, 'selection_mode': 'AUTO' if automatic else 'EXPLICIT',
        'product_id': str(product.id), 'product_name': product.name,
        'purpose_category': category, 'annual_rate': str(rate), 'base_rate': str(product.interest_rate),
        'amount_adjustment': str(amount_extra), 'term_adjustment': str(term_extra),
        'requested_amount': str(amount), 'term_months': months,
        'monthly_payment': cash(payment), 'total_interest': cash(total - amount), 'total_repayment': cash(total),
        'selection_reason': reason,
        'disclaimer': 'Предварительный расчёт по демоправилам, не банковское предложение. Без комиссий, страховок и дополнительных услуг.',
    }
