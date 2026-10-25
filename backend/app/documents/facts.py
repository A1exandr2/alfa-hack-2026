"""Conservative extraction of explicit labels, units and year columns.

No inference of missing measures, no arithmetic totals, no sample-specific values.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

PATTERNS = {
    'revenue_annual': r'^\s*выручк[а-я]*(?:\s+за\s+(?:год|\d{4}\s*год[а-я]*))?\b',
    'profit_annual': r'^\s*чист[а-я]*\s+прибыл[а-я]*(?:\s+за\s+(?:год|\d{4}\s*год[а-я]*))?\b',
    'expenses_annual': r'^\s*расход[а-я]*(?:\s+за\s+(?:год|\d{4}\s*год[а-я]*))?\b',
    'employees': r'^\s*(?:(?:среднесписочн[а-я]*|средн[а-я]*)\s+численност[а-я]*\s+(?:сотрудник[а-я]*|работник[а-я]*)|сотрудник[а-я]*)\b',
    'current_debt': r'^\s*текущ[а-я]*\s+(?:задолженност[а-я]*|долг)\s+по\s+кредит[а-я]*\b',
    'active_credits': r'^\s*активн[а-я]*\s+кредит[а-я]*\b',
    'closed_credits': r'^\s*закрыт[а-я]*\s+кредит[а-я]*\b',
    'overdue_count': r'^\s*количеств[а-я]*\s+просроч[а-я]*\b',
    'overdue_amount': r'^\s*сумм[а-я]*\s+просроч[а-я]*\b',
}
NUMBERS = re.compile(r'(?<![\w])(?:[-−]?\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?|\(\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?\))(?![\w])')
THOUSANDS = r'(?:тыс[.\s]*руб[а-я.]*|тысяч[а-я]*\s+руб[а-я.]*)'
MILLIONS = r'(?:млн[.\s]*руб[а-я.]*|миллион[а-я]*\s+руб[а-я.]*)'


def line_units(line):
    lower=line.casefold()
    found=set()
    if re.search(THOUSANDS,lower): found.add('thousand_rub')
    if re.search(MILLIONS,lower): found.add('million_rub')
    rest=re.sub(THOUSANDS+'|'+MILLIONS,'',lower)
    if re.search(r'\bруб(?:л[а-я]*)?\.?|₽',rest): found.add('rub')
    for code in re.findall(r'(?:океи|едизм)\s*[:=]?\s*["\']?(384|385)\b',lower):
        found.add('thousand_rub' if code=='384' else 'million_rub')
    return found


def document_units(text):
    declared=set()
    for line in text.splitlines():
        # Only explicit document declarations. A sentence about output fields is not a unit declaration.
        if re.search(r'единиц[а-я]*\s*(?:измерени[а-я]*)?\s*[:=|;]|денежные\s+суммы\s*[-—–:=]|все\s+суммы|океи|едизм',line,re.I):
            declared.update(line_units(line))
    if len(declared)==1:
        return next(iter(declared))
    if declared:
        return 'unknown'
    # Short reports often attach the same unit to each measured row.
    measured=set()
    for line in text.splitlines():
        if any(re.search(pattern,line,re.I) for pattern in PATTERNS.values()):
            measured.update(line_units(line))
    return next(iter(measured)) if len(measured)==1 else 'unknown'


def report_year(text):
    years=set()
    for match in re.finditer(r'отч[её]тн[а-я]*\s+(?:период|год)\s*[:=|;—-]?\s*((?:19|20)\d{2})',text,re.I):
        year=int(match[1])
        if 1900<=year<=date.today().year:years.add(year)
    return next(iter(years)) if len(years)==1 else None


def year_header(lines, index):
    for line in reversed(lines[max(0,index-12):index]):
        if not re.search(r'показатель|\bкод\b|\bгод\b',line,re.I):continue
        years=[int(v) for v in re.findall(r'\b(?:19|20)\d{2}\b',line)]
        if len(years)>=2 and len(set(years))==len(years) and all(v<=date.today().year for v in years):
            return line,years,bool(re.search(r'\bкод\b',line,re.I))
    return None


def explicit_readings(text, year):
    lines=text.splitlines()
    candidates={key:[] for key in PATTERNS}
    for i,line in enumerate(lines):
        for key,pattern in PATTERNS.items():
            match=re.search(pattern,line,re.I)
            if not match:continue
            row_years={int(v) for v in re.findall(r"\b((?:19|20)\d{2})\s*год[а-я]*\b",line,re.I)}
            if year is not None and row_years and year not in row_years:
                continue
            rest=line[match.end():].strip()
            # A prose explanation mentioning a metric is not a data row.
            if rest and not re.match(r'[:=|;\d(−-]|[a-zа-я]{1,4}-\d|на\s+конец\s+\d{4}',rest,re.I):continue
            rest=re.sub(r'\b(?:на\s+конец\s+|за\s+)?(?:19|20)\d{2}\s*год[а-я]*\b','',rest,flags=re.I)
            tokens=NUMBERS.findall(rest)
            header=year_header(lines,i)
            value=None
            if header and year in header[1] and len(tokens)==len(header[1])+int(header[2]):
                value=tokens[-len(header[1]):][header[1].index(year)]
            elif len(tokens)==1:
                value=tokens[0]
            if value is None:continue
            candidates[key].append({'value':value,'evidence':line.strip()})
    result={}
    for key,items in candidates.items():
        def number(item):
            v=re.sub(r'\s','',item['value']).replace(',','.').replace('−','-')
            if v.startswith('('):v='-'+v[1:-1]
            try:return Decimal(v)
            except InvalidOperation:return None
        distinct={number(item) for item in items}
        # Conflicting explicit rows are never silently resolved.
        if len(distinct)==1 and None not in distinct:
            result[key]=items[0]
    return result


def focused_text(text):
    lines=text.splitlines()
    metadata=[];blocks=[]
    seen=set()
    for line in lines:
        if re.search(r'\bинн\b|отч[её]тн[а-я]*\s+(?:период|год)|единиц[а-я]*\s+измерени[а-я]*|денежные\s+суммы|океи',line,re.I):
            clean=line.strip()
            if clean and clean not in seen:
                metadata.append(clean);seen.add(clean)
    for key,pattern in PATTERNS.items():
        for i,line in enumerate(lines):
            if not re.search(pattern,line,re.I):continue
            header=year_header(lines,i)
            block=(header[0]+'\n' if header else '')+'\n'.join(lines[i:min(len(lines),i+3)]).strip()
            if block and block not in seen:
                blocks.append(block);seen.add(block)
    # Prioritize measured sections over boilerplate, keeping one metadata section.
    context='\n'.join(metadata[:18])+'\n\n'+'\n\n'.join(blocks)
    return context[:14000] if blocks else text[:16000]


def declared_inn(text):
    values=set(re.findall(r'\bинн\b\s*[:=|;]?\s*(\d{10}(?:\d{2})?)\b',text,re.I))
    return next(iter(values)) if len(values)==1 else None
