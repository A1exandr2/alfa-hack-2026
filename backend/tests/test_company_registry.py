import httpx
import pytest
from app.integrations.company import DadataCompanyProvider, CompanyNotFoundError, CompanyProviderError

@pytest.mark.asyncio
async def test_registry_maps_available_company_fields():
    def respond(request):
        assert request.headers['Authorization'] == 'Token test-key'
        return httpx.Response(200, json={'suggestions':[{'value':'ООО Тест','data':{
            'inn':'7701234567','ogrn':'1234567890123','kpp':'770101001',
            'name':{'full_with_opf':'Общество с ограниченной ответственностью Тест'},
            'address':{'value':'Москва'},'management':{'name':'Иванов И.И.'},
            'state':{'status':'ACTIVE','registration_date':1546300800000},'okved':'62.01'
        }}]})
    provider=DadataCompanyProvider('test-key', transport=httpx.MockTransport(respond))
    data=await provider.get_by_inn('7701234567')
    assert data.address=='Москва'
    assert data.kpp=='770101001'
    assert data.director_name=='Иванов И.И.'
    assert data.registration_date.isoformat()=='2019-01-01'
    assert data.data_source=='DADATA'

@pytest.mark.asyncio
async def test_registry_empty_result_does_not_invent_company():
    provider=DadataCompanyProvider('test-key', transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'suggestions':[]})))
    with pytest.raises(CompanyNotFoundError):
        await provider.get_by_inn('7701234567')

@pytest.mark.asyncio
async def test_registry_outage_does_not_fall_back_to_demo():
    provider=DadataCompanyProvider('test-key', transport=httpx.MockTransport(lambda r:httpx.Response(503)))
    with pytest.raises(CompanyProviderError):
        await provider.get_by_inn('7701234567')
