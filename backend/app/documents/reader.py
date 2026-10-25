"""Bounded document-to-text worker, invoked in a disposable subprocess."""
import csv
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

MAX_TEXT = 120_000
MAX_PAGES = 20


def command(args, timeout=15):
    result = subprocess.run(args, capture_output=True, timeout=timeout, check=False, env={**os.environ,"OMP_THREAD_LIMIT":"1"})
    if result.returncode:
        raise ValueError("Файл повреждён, защищён паролем или не читается.")
    return result.stdout.decode("utf-8", errors="replace")


def decode(data):
    encodings = ("utf-16",) if data.startswith((b"\xff\xfe",b"\xfe\xff")) else ("utf-8-sig", "cp1251")
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeError:
            continue
    raise ValueError("Не удалось прочитать кодировку текста.")


def check_zip(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 2000 or sum(e.file_size for e in entries) > 40 * 1024 * 1024:
            raise ValueError("Документ слишком большой после распаковки.")
        if any(e.flag_bits & 1 for e in entries):
            raise ValueError("Сначала снимите пароль с документа.")


def ocr(path, folder):
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 18_000_000
    with Image.open(path) as image:
        if image.width * image.height > 18_000_000:
            raise ValueError("Изображение слишком большое: максимум 18 мегапикселей.")
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((2400, 3200))
        safe = folder / "ocr.png"
        image.save(safe)
    return command(["tesseract", str(safe), "stdout", "-l", "rus+eng", "--psm", "3"], timeout=20)


def read_document(path):
    suffix = path.suffix.lower()
    warnings = []
    method = "TEXT"
    if suffix == ".pdf":
        info = command(["pdfinfo", str(path)])
        match = re.search(r"^Pages:\s+(\d+)", info, re.M)
        if not match or int(match[1]) > MAX_PAGES:
            raise ValueError("Можно загрузить PDF максимум на 20 страниц. Разделите документ.")
        pages = []
        for number in range(1, int(match[1]) + 1):
            text = command(["pdftotext", "-layout", "-f", str(number), "-l", str(number), str(path), "-"])
            fallback_used = False
            if len(re.sub(r"\s", "", text)) < 40:
                # Poppler can omit text from malformed but still readable PDFs.
                # Try a second parser before rendering the page for OCR.
                try:
                    from pypdf import PdfReader
                    from pypdf.errors import PdfReadError
                    fallback = PdfReader(str(path), strict=False).pages[number - 1].extract_text() or ""
                    if fallback:
                        text = fallback
                        fallback_used = True
                except (OSError, ValueError, PdfReadError):
                    pass
            if len(re.sub(r"\s", "", text)) < 40 and not fallback_used:
                prefix = path.parent / "page"
                command(["pdftoppm", "-f", str(number), "-l", str(number), "-r", "120", "-scale-to", "2600", "-singlefile", "-png", str(path), str(prefix)], timeout=20)
                text = ocr(prefix.with_suffix(".png"), path.parent)
                method = "OCR"
            pages.append(f"Страница {number}\n{text}")
            if sum(map(len,pages)) > MAX_TEXT:
                raise ValueError("В документе слишком много текста. Загрузите только нужные страницы.")
        text = "\n\n".join(pages)
    elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}:
        from PIL import Image
        with Image.open(path) as image:
            if getattr(image, "n_frames", 1) > 1:
                raise ValueError("Многостраничное изображение преобразуйте в PDF или отдельные картинки.")
        text, method = ocr(path, path.parent), "OCR"
    elif suffix == ".xlsx":
        check_zip(path)
        from openpyxl import load_workbook
        book = load_workbook(path, read_only=True, data_only=True, keep_links=False)
        lines, count = [], 0
        try:
            if len(book.worksheets) > 20:
                raise ValueError("В книге больше 20 листов. Оставьте листы с отчётностью.")
            for sheet in book.worksheets:
                lines.append("Лист: " + sheet.title)
                for row in sheet.iter_rows():
                    count += len(row)
                    if count > 50_000:
                        raise ValueError("В таблице больше 50 000 ячеек. Оставьте нужные строки.")
                    values = [str(v.value) if v.value is not None else "" for v in row]
                    if any(values):
                        lines.append(" | ".join(values))
            text = "\n".join(lines)
            warnings.append("Формулы XLSX читаются по сохранённым значениям. Пересчитайте и сохраните книгу перед загрузкой.")
        finally:
            book.close()
    elif suffix == ".docx":
        check_zip(path)
        from defusedxml.ElementTree import fromstring
        with zipfile.ZipFile(path) as archive:
            tree = fromstring(archive.read("word/document.xml"))
            text = "\n".join(" ".join(p.itertext()) for p in tree.iter() if p.tag.endswith("}p"))
    elif suffix == ".xml":
        from defusedxml.ElementTree import fromstring
        tree = fromstring(path.read_bytes())
        text = "\n".join(f"{e.tag.split('}')[-1]}: " + " | ".join([f"{k}={v}" for k,v in e.attrib.items()] + ([e.text.strip()] if e.text and e.text.strip() else [])) for e in tree.iter())
    elif suffix in {".csv", ".tsv"}:
        raw = decode(path.read_bytes())
        from collections import Counter
        delimiter = "\t" if suffix == ".tsv" else ","
        if suffix == ".csv":
            candidates = []
            for separator in (";", "\t", ","):
                sample = list(csv.reader(io.StringIO(raw[:16000]), delimiter=separator))[:100]
                widths = Counter(len(row) for row in sample if any(row) and len(row)>1)
                score = max(widths.values(),default=0) / max(1,len(sample))
                candidates.append((score, separator))
            delimiter = max(candidates,key=lambda pair:pair[0])[1]
        text = "\n".join(" | ".join(row) for row in csv.reader(io.StringIO(raw),delimiter=delimiter))
    elif suffix == ".json":
        from decimal import Decimal
        data = json.loads(decode(path.read_bytes()), parse_float=Decimal)
        names = {"inn":"ИНН","report_year":"Отчётный год","unit":"Единицы измерения",
            "revenue_annual":"Выручка за год","profit_annual":"Чистая прибыль за год",
            "expenses_annual":"Расходы за год","employees":"Сотрудники",
            "current_debt":"Текущий долг по кредитам","active_credits":"Активные кредиты",
            "closed_credits":"Закрытые кредиты","overdue_count":"Количество просрочек","overdue_amount":"Сумма просрочек"}
        output = []
        def flatten(value,depth=0):
            if depth>30:raise ValueError("JSON содержит слишком много уровней вложенности.")
            if isinstance(value,dict):
                for key,item in value.items():
                    if isinstance(item,(dict,list)):
                        output.append(str(key)+":");flatten(item,depth+1)
                    else:
                        if key=="unit":item={"rub":"рубли","thousand_rub":"тыс. руб.","million_rub":"млн. руб."}.get(item,item)
                        output.append(names.get(key,key)+": "+("Нет данных" if item is None else str(item)))
            elif isinstance(value,list):
                for item in value:flatten(item,depth+1)
            else:output.append(str(value))
        flatten(data)
        text = "\n".join(output)
    elif suffix == ".txt":
        text = decode(path.read_bytes())
    else:
        raise ValueError("Формат не поддерживается. Сохраните файл как PDF, XLSX, DOCX, CSV, XML, TXT, JSON или изображение.")
    if len(text) > MAX_TEXT:
        raise ValueError("В документе слишком много текста. Загрузите только нужную часть.")
    text = text.replace("\x00", "")
    if len(text.strip()) < 10:
        raise ValueError("Не удалось прочитать текст. Загрузите более чёткий скан или другой файл.")
    if method == "OCR":
        warnings.append("Текст распознан со скана: особенно внимательно проверьте цифры, знаки и единицы измерения.")
    return {"text":text,"method":method,"warnings":warnings}


if __name__ == "__main__":
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (320 * 1024 * 1024, 320 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (50, 50))
    try:
        result = read_document(Path(sys.argv[1]))
    except Exception as error:
        result = {"error": str(error) if isinstance(error, ValueError) else "Документ не удалось прочитать. Проверьте формат, пароль и содержимое."}
    print(json.dumps(result, ensure_ascii=False))
