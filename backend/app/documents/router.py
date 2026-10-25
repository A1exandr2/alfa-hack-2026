import asyncio
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import get_current_user
from app.company.data_quality import FINANCIAL_FIELDS, CREDIT_FIELDS
from app.company.schemas import FinancialsUpdateRequest, CreditHistoryUpdateRequest
from app.database import get_db_session
from app.documents.extraction import extract_with_ai
from app.models import User, Company, Financials, CreditHistory, DocumentImport

router = APIRouter(prefix="/api/v1/company/documents", tags=["documents"])
MAX_BYTES = 10 * 1024 * 1024
EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".xlsx", ".csv", ".tsv", ".xml", ".txt", ".json", ".docx"}
processing = asyncio.Semaphore(1)


def read_file(data, suffix):
    with tempfile.TemporaryDirectory(prefix="credit-document-") as folder:
        path = Path(folder) / ("input" + suffix)
        path.write_bytes(data)
        try:
            response = subprocess.run([sys.executable, "-m", "app.documents.reader", str(path)],
                capture_output=True, timeout=65, check=False)
            result = json.loads(response.stdout)
        except (subprocess.TimeoutExpired, ValueError):
            raise ValueError("Чтение документа заняло слишком много времени. Разделите его на меньшие файлы.")
        if response.returncode or result.get("error"):
            raise ValueError(result.get("error", "Не удалось прочитать документ."))
        return result


class ConfirmImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: bool
    financials: FinancialsUpdateRequest | None = None
    credit_history: CreditHistoryUpdateRequest | None = None


@router.post("/preview", status_code=201)
async def preview(request: Request, filename: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    if not user.company_id:
        raise HTTPException(409,"Сначала привяжите компанию по ИНН.")
    name = Path(filename.replace("\\", "/")).name[:255]
    suffix = Path(name).suffix.lower()
    if suffix not in EXTENSIONS:
        raise HTTPException(415,"Этот формат пока не поддерживается. Используйте PDF, изображение, XLSX, DOCX, CSV, XML, TXT или JSON.")
    if processing.locked():
        raise HTTPException(429,"Сейчас разбирается другой документ. Попробуйте немного позже.")
    async with processing:
        data = bytearray()
        try:
            async with asyncio.timeout(45):
                async for chunk in request.stream():
                    if len(data) + len(chunk) > MAX_BYTES:
                        raise HTTPException(413,"Файл слишком большой. Максимальный размер — 10 МБ.")
                    data.extend(chunk)
        except TimeoutError:
            raise HTTPException(408,"Загрузка заняла слишком много времени. Повторите попытку.")
        if not data:
            raise HTTPException(400,"Выбран пустой файл.")
        try:
            parsed = await run_in_threadpool(read_file, data, suffix)
        except ValueError as error:
            raise HTTPException(422,str(error)) from error
        extracted = await run_in_threadpool(extract_with_ai, parsed["text"], parsed["method"])
        extracted["warnings"] = parsed["warnings"] + extracted["warnings"]
        company = await session.get(Company, user.company_id)
        extracted["company_mismatch"] = bool(extracted["inn"] and extracted["inn"] != company.inn)
        if extracted["company_mismatch"]:
            extracted["warnings"].insert(0,"В документе другой ИНН. Сохранение заблокировано: загрузите документ вашей компании.")
        record = DocumentImport(user_id=user.id,company_id=user.company_id,filename=name,
            sha256=hashlib.sha256(data).hexdigest(),extracted=extracted)
        session.add(record)
        await session.commit()
        return {"id":str(record.id),"filename":name,**extracted}


@router.post("/{import_id}/confirm")
async def confirm(import_id: UUID, payload: ConfirmImport, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    record = await session.get(DocumentImport,import_id,with_for_update=True)
    if not record or record.user_id != user.id or record.company_id != user.company_id:
        raise HTTPException(404,"Предварительный разбор не найден для этой компании.")
    if record.confirmed_at:
        raise HTTPException(409,"Этот документ уже сохранён. Показатели можно изменить во вкладке компании.")
    if record.extracted.get("company_mismatch"):
        raise HTTPException(409,"ИНН документа не совпадает с компанией. Загрузите другой файл.")
    if not payload.accepted or (payload.financials is None and payload.credit_history is None):
        raise HTTPException(422,"Проверьте показатели и подтвердите сохранение хотя бы одного поля.")
    now = datetime.now(timezone.utc)
    accepted = {}
    for kind, model, fields, changes in (
        ("financials",Financials,FINANCIAL_FIELDS,payload.financials),
        ("credit_history",CreditHistory,CREDIT_FIELDS,payload.credit_history),
    ):
        if changes is None:
            continue
        target = await session.get(model,user.company_id,with_for_update=True)
        if target is None:
            target = model(company_id=user.company_id,source="DOCUMENT_USER_CONFIRMED",field_sources={})
            session.add(target)
        metadata = dict(target.field_sources or {})
        accepted[kind] = changes.model_dump(mode="json",exclude_unset=True)
        for field in changes.model_fields_set:
            previous_value = getattr(target,field)
            previous_meta = metadata.get(field)
            setattr(target,field,getattr(changes,field))
            extracted_value = record.extracted.get("report_year") if field == "report_year" else record.extracted.get("values",{}).get(field)
            metadata[field] = {"source":"DOCUMENT_USER_CONFIRMED","document_id":str(record.id),
                "filename":record.filename,"sha256":record.sha256,"entered_by":str(user.id),
                "report_year":getattr(changes,"report_year",None) or record.extracted.get("report_year"),
                "fetched_at":now.isoformat(),"evidence":record.extracted.get("evidence",{}).get(field),
                "corrected":extracted_value is None or Decimal(str(getattr(changes,field))) != Decimal(str(extracted_value)),
                "previous_value":str(previous_value) if previous_value is not None else None,
                "previous_source":previous_meta.get("source") if isinstance(previous_meta,dict) else previous_meta,
                "registry":({**previous_meta,"value":str(previous_value)} if isinstance(previous_meta,dict) and previous_meta.get("source") not in {"USER_INPUT","USER_VERIFIED","DOCUMENT_USER_CONFIRMED"} else (previous_meta or {}).get("registry"))}
        target.field_sources = metadata
        target.source = "DOCUMENT_USER_CONFIRMED"
        target.updated_at = now
    record.confirmed_at, record.accepted_values = now, accepted
    await session.commit()
    return {"saved":True,"message":"Данные сохранены как проверенные пользователем. Для кредитования они требуют проверки специалистом."}


@router.delete("/{import_id}", status_code=204)
async def discard(import_id: UUID, user: User = Depends(get_current_user),session: AsyncSession = Depends(get_db_session)):
    record = await session.get(DocumentImport,import_id,with_for_update=True)
    if not record or record.user_id != user.id or record.company_id != user.company_id:
        raise HTTPException(404,"Предварительный разбор не найден.")
    if record.confirmed_at:
        raise HTTPException(409,"Подтверждённый импорт сохраняется в истории происхождения данных.")
    await session.delete(record)
    await session.commit()
