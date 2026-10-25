import json
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

from app.database import engine, session_factory
from app.main import app
from app.models import DocumentImport, Financials, User, ApplicationSnapshot
from app.documents import router as document_router
from app.documents.extraction import extract_with_ai
from app.documents.router import read_file
from test_applications import _register_company_user, _cleanup_user, _create_draft


@pytest.mark.parametrize('suffix,content',[
    ('.txt','Выручка за 2025 год: 1 200 000 руб.'.encode()),
    ('.csv','Показатель;2025\nВыручка;1200000'.encode()),
    ('.txt','Выручка 1200000 рублей'.encode('cp1251')),
    ('.txt','Выручка 1200000 рублей'.encode('utf-16')),
    ('.xml','<Отчет Год="2025"><Выручка>1200000</Выручка></Отчет>'.encode()),
    ('.json',b'{"revenue_annual":1200000,"report_year":2025}')])
def test_reads_text_table_and_xml_formats(suffix,content):
    result=read_file(content,suffix)
    assert '1200' in result['text'].replace(' ','')
    assert result['method']=='TEXT'


def test_reads_spreadsheet_and_docx():
    from openpyxl import Workbook
    book=Workbook()
    book.active.append(['Показатель',2025])
    book.active.append(['Выручка',1200000])
    buffer=BytesIO();book.save(buffer)
    assert '1200000' in read_file(buffer.getvalue(),'.xlsx')['text']
    import zipfile
    buffer=BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:
        archive.writestr('word/document.xml','<w:document xmlns:w="test"><w:p><w:t>Выручка 1200000 руб.</w:t></w:p></w:document>')
    assert '1200000' in read_file(buffer.getvalue(),'.docx')['text']


def test_xml_entities_and_corrupt_files_are_rejected():
    with pytest.raises(ValueError):
        read_file(b'<!DOCTYPE x [<!ENTITY s SYSTEM "file:///etc/passwd">]><x>&s;</x>', '.xml')
    with pytest.raises(ValueError):
        read_file(b'not an image','.png')
    with pytest.raises(ValueError):
        read_file(b'not a spreadsheet','.xlsx')


def ai_response(monkeypatch, payload):
    from app.documents.extraction import FIELDS
    payload={"inn":None,"report_year":None,**payload}
    payload["values"]={field:payload.get("values",{}).get(field,{"value":None,"evidence":""}) for field in FIELDS}
    class Client:
        def __init__(self,**kwargs): pass
        def chat(self,**kwargs): return {'message':{'content':json.dumps(payload,ensure_ascii=False)}}
    monkeypatch.setattr('app.documents.extraction.ollama.Client',Client)


def test_ai_scales_only_evidenced_values_and_keeps_zero(monkeypatch):
    text='ИНН 7325115310. Отчет за 2025 год. Единица: тыс. руб.\nВыручка 1 250\nЧистая прибыль (25)\nСотрудники 8\nПросрочки 0'
    ai_response(monkeypatch,{'inn':'7325115310','report_year':2025,'unit':'thousand_rub','values':{
        'revenue_annual':{'value':'1 250','evidence':'Выручка 1 250'},
        'profit_annual':{'value':'(25)','evidence':'Чистая прибыль (25)'},
        'employees':{'value':'8','evidence':'Сотрудники 8'},
        'overdue_count':{'value':'0','evidence':'Просрочки 0'},
        'current_debt':{'value':'500','evidence':'invented evidence'},
    }})
    result=extract_with_ai(text,'TEXT')
    assert Decimal(result['values']['revenue_annual'])==1250000
    assert Decimal(result['values']['profit_annual'])==-25000
    assert result['values']['employees']==8
    assert result['values']['overdue_count']==0
    assert 'current_debt' not in result['values']


def test_unknown_or_invented_units_never_scale_money(monkeypatch):
    ai_response(monkeypatch,{'unit':'million_rub','values':{'revenue_annual':{'value':'1200','evidence':'Выручка 1200'}}})
    result=extract_with_ai('Отчет компании. Выручка 1200','TEXT')
    assert result['values']=={}
    assert result['warnings']


@pytest.mark.asyncio
async def test_import_preview_does_not_write_financials_confirmation_is_manual_and_private(monkeypatch):
    monkeypatch.setattr(document_router,'extract_with_ai',lambda text,method:{'values':{'revenue_annual':'1250000'},
        'evidence':{'revenue_annual':'Выручка 1250000'},'inn':None,'report_year':2025,'unit':'rub','method':'TEXT + QWEN','warnings':[],'text_excerpt':text})
    email=other_email=''
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            email,headers=await _register_company_user(client)
            previous=(await client.get('/api/v1/company/financials',headers=headers)).json()
            preview=await client.post('/api/v1/company/documents/preview?filename=report.txt',headers=headers,content='Выручка 1250000 руб. за 2025 год'.encode())
            assert preview.status_code==201,preview.text
            draft=preview.json();import_id=draft['id']
            unchanged=(await client.get('/api/v1/company/financials',headers=headers)).json()
            assert unchanged==previous
            other_email,other_headers=await _register_company_user(client)
            payload={'accepted':True,'financials':{'revenue_annual':1350000,'report_year':2025}}
            assert (await client.post(f'/api/v1/company/documents/{import_id}/confirm',headers=other_headers,json=payload)).status_code==404
            assert (await client.post(f'/api/v1/company/documents/{import_id}/confirm',headers=headers,json={**payload,'accepted':False})).status_code==422
            saved=await client.post(f'/api/v1/company/documents/{import_id}/confirm',headers=headers,json=payload)
            assert saved.status_code==200,saved.text
            assert (await client.post(f'/api/v1/company/documents/{import_id}/confirm',headers=headers,json=payload)).status_code==409
            current=(await client.get('/api/v1/company/financials',headers=headers)).json()
            assert current['revenue_annual']==1350000
            assert current['source']=='DOCUMENT_USER_CONFIRMED'
            assert current['field_sources']['revenue_annual']['corrected'] is True
            from app.company.data_quality import manual_fields, FINANCIAL_FIELDS
            async with session_factory() as session:
                user=await session.scalar(select(User).where(User.email==email))
                financial=await session.get(Financials,user.company_id)
                assert 'revenue_annual' in manual_fields(financial,FINANCIAL_FIELDS)
    finally:
        for address in [email,other_email]:
            if address:
                async with session_factory() as session:
                    user=await session.scalar(select(User).where(User.email==address))
                    if user:
                        await session.execute(delete(DocumentImport).where(DocumentImport.user_id==user.id));await session.commit()
                await _cleanup_user(address)
        await engine.dispose()


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_empty_oversized_and_mismatched_company(monkeypatch):
    email=''
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            email,headers=await _register_company_user(client)
            base='/api/v1/company/documents/preview?filename='
            assert (await client.post(base+'x.txt',content=b'text')).status_code==401
            assert (await client.post(base+'x.exe',headers=headers,content=b'bad')).status_code==415
            assert (await client.post(base+'x.txt',headers=headers,content=b'')).status_code==400
            assert (await client.post(base+'x.txt',headers=headers,content=b'a'*(10*1024*1024+1))).status_code==413
            monkeypatch.setattr(document_router,'extract_with_ai',lambda text,method:{'values':{},'evidence':{},'inn':'0000000000','report_year':None,'unit':'unknown','method':'TEXT','warnings':[],'text_excerpt':text})
            preview=await client.post(base+'x.txt',headers=headers,content=b'Company financial report 2025')
            assert preview.status_code==201
            assert preview.json()['company_mismatch'] is True
            response=await client.post(f"/api/v1/company/documents/{preview.json()['id']}/confirm",headers=headers,json={'accepted':True,'financials':{'revenue_annual':1}})
            assert response.status_code==409
    finally:
        if email:
            async with session_factory() as session:
                user=await session.scalar(select(User).where(User.email==email))
                if user:
                    await session.execute(delete(DocumentImport).where(DocumentImport.user_id==user.id));await session.commit()
            await _cleanup_user(email)
        await engine.dispose()


def text_pdf():
    content=b'BT /F1 18 Tf 60 700 Td (Revenue 1200000 RUB 2025) Tj ET'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream']
    output=b'%PDF-1.4\n';offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(output));output+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(output)
    output+=b'xref\n0 6\n0000000000 65535 f \n'
    for offset in offsets[1:]:output+=f'{offset:010} 00000 n \n'.encode()
    return output+b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF'


def test_reads_pdf_text_and_ocr_images_and_scans():
    assert '1200000' in read_file(text_pdf(),'.pdf')['text']
    from PIL import Image, ImageDraw, ImageFont
    image=Image.new('RGB',(1400,400),'white')
    ImageDraw.Draw(image).text((70,140),'REVENUE 1200000 RUB',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',54),fill='black')
    for format,suffix in [('PNG','.png'),('PDF','.pdf')]:
        buffer=BytesIO();image.save(buffer,format=format)
        result=read_file(buffer.getvalue(),suffix)
        assert result['method']=='OCR'
        assert '1200000' in result['text'].replace(' ','')


def test_original_18_page_report_preserves_all_nine_measures_even_if_model_omits_values(monkeypatch):
    from app.documents.facts import document_units,report_year,focused_text
    raw=Path(__file__).with_name('fixtures').joinpath('noisy-financial-report.pdf').read_bytes()
    text=read_file(raw,'.pdf')['text']
    assert document_units(text)=='thousand_rub'
    assert report_year(text)==2025
    context=focused_text(text)
    for needle in ['54 320','49 555','4 765','8 420','Активные кредиты','Закрытые кредиты','135']:
        assert needle in context
    assert len(context)<5000
    ai_response(monkeypatch,{'inn':'7710140679','report_year':2025,'unit':'unknown','values':{}})
    result=extract_with_ai(text,'TEXT')
    expected={'revenue_annual':54320000,'profit_annual':4765000,'expenses_annual':49555000,
        'employees':37,'current_debt':8420000,'active_credits':3,'closed_credits':7,'overdue_count':1,'overdue_amount':135000}
    assert result['unit']=='thousand_rub'
    assert set(result['values'])==set(expected)
    for field,value in expected.items():
        assert Decimal(str(result['values'][field]))==Decimal(value),field
        assert result['evidence'][field]


def test_unit_mentions_about_destination_do_not_override_source_unit():
    from app.documents.facts import document_units
    assert document_units('Единицы измерения: тыс. руб.\nПоля кабинета ожидают рубли.')=='thousand_rub'
    assert document_units('Все денежные суммы — в тыс. руб.; счётчики — в единицах.\nЗначения переводятся в рубли.')=='thousand_rub'
    assert document_units('Единицы измерения: рубли\nДругая секция: единицы измерения: млн. руб.')=='unknown'


def test_table_uses_the_requested_year_column_not_the_last_number():
    from app.documents.facts import explicit_readings
    text='Показатель    Код    2025    2024    2023\nВыручка за год    2110    900    800    700\nЧистая прибыль за 2024 год: 80'
    result=explicit_readings(text,2025)
    assert result['revenue_annual']['value']=='900'
    assert 'profit_annual' not in result


def test_conflicting_source_rows_are_not_resolved_by_rules():
    from app.documents.facts import explicit_readings
    assert explicit_readings('Выручка за год: 100\nВыручка за год: 200',2025)=={}


def test_delimited_metadata_year_and_units_and_decimal_commas():
    from app.documents.facts import document_units,report_year,explicit_readings
    text='Отчётный год | 2025\nЕдиницы измерения | млн. руб.\nПоказатель | 2025 | 2024 | Единица\nВыручка за год | 8.125 | 7.8 | млн. руб.'
    assert document_units(text)=='million_rub'
    assert report_year(text)==2025
    assert explicit_readings(text,2025)['revenue_annual']['value']=='8.125'
    raw='ИНН;7710140679\nОтчётный год;2023\nЕдиницы измерения;тыс. руб.\nПоказатель;Значение;Единица\nВыручка за год;9876,54;тыс. руб.\nРасходы за год;9753,09;тыс. руб.'
    parsed=read_file(raw.encode('cp1251'),'.csv')['text']
    assert '9876,54' in parsed
    assert explicit_readings(parsed,2023)['revenue_annual']['value']=='9876,54'


def test_json_machine_fields_and_explicit_inn_are_preserved():
    from app.documents.facts import document_units,report_year,declared_inn
    raw=json.dumps({'company':{'inn':'0000000000'},'report_year':2025,'unit':'rub','financials':{'revenue_annual':'2345678.91','employees':0,'current_debt':None}}).encode()
    text=read_file(raw,'.json')['text']
    assert document_units(text)=='rub'
    assert report_year(text)==2025
    assert declared_inn(text)=='0000000000'
    assert 'Выручка за год: 2345678.91' in text
    assert 'Сотрудники: 0' in text
    assert 'Текущий долг по кредитам: Нет данных' in text
