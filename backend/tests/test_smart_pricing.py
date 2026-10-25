from decimal import Decimal
from types import SimpleNamespace
import pytest
from app.applications.pricing import calculate_quote


def products():
    def p(id,name,minimum,maximum,low,high,rate):
        return SimpleNamespace(id=id,name=name,min_amount=Decimal(minimum),max_amount=Decimal(maximum),min_term_months=low,max_term_months=high,interest_rate=Decimal(rate))
    return [p('dev','Кредит на развитие бизнеса','500000','20000000',12,60,'16.5'),p('turn','Оборотный кредит','100000','5000000',6,36,'18.9'),p('fast','Экспресс-кредит','50000','1000000',3,12,'21.5')]

@pytest.mark.parametrize('amount,months,category,chosen,rate',[
    ('500000',12,'investment','dev','16.50'),
    ('15000000',21,'other','dev','18.00'),
    ('4500000',24,'investment','dev','17.50'),
    ('10000000',48,'investment','dev','18.50'),
    ('500000',12,'working_capital','turn','18.90'),
    ('500000',12,'urgent','fast','21.50'),
    ('500000',12,'other','dev','16.50'),
    ('2000000',24,'urgent','dev','17.50'),
])
def test_product_selection_and_rate(amount,months,category,chosen,rate):
    product,quote=calculate_quote(products(),Decimal(amount),months,category)
    assert product.id==chosen
    assert quote['annual_rate']==rate
    assert quote['rules_version']=='demo-v1'
    assert Decimal(quote['total_repayment']) > Decimal(amount)

def test_boundaries_and_no_eligible_product():
    assert calculate_quote(products(),Decimal('20000001'),60,'other') is None
    assert calculate_quote(products(),Decimal('500000'),61,'other') is None
    assert calculate_quote(products(),Decimal('49999'),3,'other') is None
    _,low=calculate_quote(products(),Decimal('1000000'),12,'investment')
    _,high=calculate_quote(products(),Decimal('1000000.01'),12,'investment')
    assert Decimal(high['annual_rate'])-Decimal(low['annual_rate'])==Decimal('.5')

def test_annuity_matches_independent_known_result():
    _,quote=calculate_quote(products(),Decimal('500000'),12,'investment')
    assert quote['monthly_payment']=='45483.82'
    assert quote['total_interest']=='45805.82'
    assert quote['total_repayment']=='545805.82'
