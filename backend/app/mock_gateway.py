from dataclasses import dataclass


@dataclass(frozen=True)
class CompanyData:
    name: str
    inn: str
    ogrn: str | None = None
    director_name: str | None = None
    okved: str | None = None


async def lookup_company(inn: str) -> CompanyData:
    """Return deterministic local company data for the MVP.

    This boundary will later be replaced by a separate Mock Gateway client.
    """
    return CompanyData(
        name=f"Компания с ИНН {inn}",
        inn=inn,
        director_name="Тестовый руководитель",
        okved="62.01",
    )
