"""
Генератор синтетических данных для демонстрации кейса.
Создаёт: компании (ЕГРЮЛ mock), финансы (ФНС mock),
кредитные истории (БКИ mock) и заявки с risk_score.
"""
import csv
import os
import random
import uuid

from faker import Faker

fake = Faker("ru_RU")
random.seed(42)

OKVEDS = ["62.01", "47.11", "56.10", "41.20", "62.02", "49.41"]
REGIONS = ["Москва", "Санкт-Петербург", "Нижний Новгород", "Казань", "Екатеринбург", "Краснодар"]
PURPOSES = ["Оборотный", "Инвестиционный", "Рефинансирование"]
STATUSES = ["ACTIVE", "LIQUIDATING", "BANKRUPT"]


def generate_inn() -> str:
    length = random.choice([10, 12])
    return "".join(str(random.randint(0, 9)) for _ in range(length))


def generate_company() -> dict:
    age = random.choices(
        [0.5, 1, 2, 3, 5, 10, 15],
        weights=[5, 10, 20, 25, 20, 15, 5],
    )[0]
    revenue = int(random.lognormvariate(14, 1.5))
    revenue = max(500_000, min(200_000_000, revenue))

    return {
        "company_id": str(uuid.uuid4()),
        "inn": generate_inn(),
        "name": f'ООО "{fake.company()}"',
        "company_age": age, 
        "okved": random.choice(OKVEDS), 
        "region": random.choice(REGIONS),
        "status": random.choices(STATUSES, weights=[90, 7, 3])[0],
        "revenue": revenue,
    }


def generate_financials(company: dict) -> dict:
    margin = max(-0.2, min(0.4, random.gauss(0.08, 0.1)))
    return {
        "company_id": company["company_id"],
        "revenue": company["revenue"],
        "profit_margin": round(margin, 3),
        "profit": int(company["revenue"] * margin),
        "assets": int(company["revenue"] * random.uniform(0.3, 2.0)),
    }


def generate_credit_history(company: dict) -> dict:
    age_factor = min(company["company_age"] / 5, 1.0)
    n_credits = max(0, int(random.gauss(age_factor * 2, 1)))
    overdue_prob = 0.3 if company["company_age"] < 2 else 0.1
    has_overdue = 1 if random.random() < overdue_prob else 0
    debt_load = round(random.uniform(0, 1.5) * (1 + has_overdue * 0.5), 2)

    return {
        "company_id": company["company_id"],
        "n_credits": n_credits,
        "has_overdue": has_overdue,
        "debt_load": debt_load,
    }


def calculate_risk_score(company: dict, financials: dict, credit: dict) -> int:
    """Дублирует логику ml/risk_scoring.py для генерации"""
    score = 50
    if company["company_age"] < 1:
        score += 20
    elif company["company_age"] < 2:
        score += 10
    elif company["company_age"] > 5:
        score -= 15
    if credit["has_overdue"]:
        score += 25
    if credit["debt_load"] > 1.0:
        score += 15
    elif credit["debt_load"] > 0.5:
        score += 5
    if financials["profit_margin"] < 0:
        score += 15
    elif financials["profit_margin"] > 0.15:
        score -= 10
    return max(0, min(100, score))


def generate_application(company: dict, financials: dict, credit: dict) -> dict:
    loan_amount = random.choice([300_000, 500_000, 1_000_000, 2_000_000, 5_000_000])
    return {
        "application_id": str(uuid.uuid4()),
        "company_id": company["company_id"],
        "loan_amount": loan_amount,
        "loan_term": random.choice([6, 12, 18, 24, 36]),
        "purpose": random.choice(PURPOSES),
        "risk_score": calculate_risk_score(company, financials, credit),
    }


def main(n_companies: int = 500) -> None:
    companies, financials, credits, applications = [], [], [], []

    for _ in range(n_companies):
        c = generate_company()
        f = generate_financials(c)
        cr = generate_credit_history(c)
        app = generate_application(c, f, cr)
        companies.append(c)
        financials.append(f)
        credits.append(cr)
        applications.append(app)

    def save_csv(filename, rows):
        if not rows:
            return
        with open(f"data/{filename}", "w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"{filename}: {len(rows)} rows")

    save_csv("companies.csv", companies)
    save_csv("financials.csv", financials)
    save_csv("credit_history.csv", credits)
    save_csv("applications.csv", applications)

    dist = {"Low (0-30)": 0, "Medium (31-60)": 0, "High (61-100)": 0}
    for app in applications:
        s = app["risk_score"]
        if s <= 30:
            dist["Low (0-30)"] += 1
        elif s <= 60:
            dist["Medium (31-60)"] += 1
        else:
            dist["High (61-100)"] += 1

    print("\nRisk distribution:")
    for k, v in dist.items():
        print(f" {k}: {v} ({v / n_companies * 100:.1f}%)")


if __name__ == "__main__":
    main()