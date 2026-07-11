# -*- coding: utf-8 -*-
"""共享工具: 维基表格解析(rowspan展开)、日期解析、HOGS判定"""
import re, json, subprocess, time
from lxml import html as LH

UA = 'Mozilla/5.0 (LeaderVisitsPipeline/1.0; research)'
MONTHS = {m:i+1 for i,m in enumerate(['January','February','March','April','May','June',
          'July','August','September','October','November','December'])}

def fetch(url, out, timeout=20):
    r = subprocess.run(['curl','-sL','-A',UA,'-m',str(timeout),'-w','%{http_code}',url,'-o',out],
                       capture_output=True, text=True)
    return r.stdout.strip() == '200'

def wiki_page(title, out):
    import urllib.parse
    url = 'https://en.wikipedia.org/api/rest_v1/page/html/' + urllib.parse.quote(title, safe='')
    return fetch(url, out)

def expand_table(tbl):
    """rowspan/colspan 展开为规整网格"""
    grid, pending = [], {}
    for tr in tbl.xpath('.//tr'):
        row, col, ci = [], 0, 0
        cells = tr.xpath('./th|./td')
        while ci < len(cells) or col in pending:
            if col in pending:
                rem, txt = pending[col]; row.append(txt)
                pending[col] = (rem-1, txt)
                if rem-1 <= 0: del pending[col]
                col += 1; continue
            if ci >= len(cells): break
            c = cells[ci]; ci += 1
            txt = re.sub(r'\[[^\]]*\]','', c.text_content()).strip()
            rs, cs = int(c.get('rowspan') or 1), int(c.get('colspan') or 1)
            for _ in range(cs):
                row.append(txt)
                if rs > 1: pending[col] = (rs-1, txt)
                col += 1
        grid.append(row)
    return grid

def parse_dates_any(s, year):
    """兼容 '22–24 March' 与 'April 25–26' 两种维基日期风格"""
    s = re.sub(r'\s+',' ', str(s).replace('\u2013','-').replace('–','-')).strip()
    pats = [
        (r'(\w+) (\d{1,2}) ?- ?(\w+) (\d{1,2})$', lambda m:(MONTHS.get(m.group(1)),int(m.group(2)),MONTHS.get(m.group(3)),int(m.group(4)))),
        (r'(\w+) (\d{1,2}) ?- ?(\d{1,2})$',       lambda m:(MONTHS.get(m.group(1)),int(m.group(2)),MONTHS.get(m.group(1)),int(m.group(3)))),
        (r'(\w+) (\d{1,2})$',                      lambda m:(MONTHS.get(m.group(1)),int(m.group(2)),MONTHS.get(m.group(1)),int(m.group(2)))),
        (r'(\d{1,2}) (\w+) ?- ?(\d{1,2}) (\w+)$', lambda m:(MONTHS.get(m.group(2)),int(m.group(1)),MONTHS.get(m.group(4)),int(m.group(3)))),
        (r'(\d{1,2}) ?- ?(\d{1,2}) (\w+)$',       lambda m:(MONTHS.get(m.group(3)),int(m.group(1)),MONTHS.get(m.group(3)),int(m.group(2)))),
        (r'(\d{1,2}) (\w+)$',                      lambda m:(MONTHS.get(m.group(2)),int(m.group(1)),MONTHS.get(m.group(2)),int(m.group(1)))),
    ]
    for pat, fn in pats:
        m = re.match(pat, s)
        if m:
            m1,d1,m2,d2 = fn(m)
            if m1 and m2:
                y2 = year+1 if m2<m1 else year
                try: return f"{year}-{m1:02d}-{d1:02d}", f"{y2}-{m2:02d}-{d2:02d}"
                except: pass
    return None, None

# ASPI 编码规则: 有外交活动的经停/基地访问仍计数
ENGAGE = re.compile(r'met with (president|prime minister|king|queen|emperor|chancellor|emir|sheikh|sultan|taoiseach|his majesty|chairman|premier|kim jong)|bilateral|attended the .*(summit|funeral|ceremony|meeting)|held talks|state visit|official visit|audience with pope|lying in state', re.I)
STOP = re.compile(r'refuel|stopped (en route|while|during|overnight|at)|briefly stopped|brief stop|\btransit', re.I)
MIL  = re.compile(r'military base|bagram|al[- ]asad|air base|raf mildenhall|toured the joint operating center|visited (wounded )?u\.s\. military personnel|(visited|met) with (u\.s\.|united states) (military|armed forces|troops)', re.I)

def classify_trip(details):
    d = str(details or '')
    is_stop, is_mil, eng = bool(STOP.search(d)), bool(MIL.search(d)), bool(ENGAGE.search(d))
    flags = [x for x,c in [('stopover',is_stop),('military_base',is_mil),
             ('private','private trip' in d.lower() or 'golf resort' in d.lower()),
             ('diplomatic_engagement',eng)] if c]
    return ';'.join(flags), eng or not (is_stop or is_mil)

# 访美 HOGS 头衔判定
HOGS_T = re.compile(r'^(Interim |Acting |Transitional )?(President|Prime Minister|Taoiseach|(Federal )?Chancellor|King|Queen|Emperor|Sultan|Amir|Emir|Grand Duke|Pope|Premier|State Counsellor|Captain[s]? Regent|General Secretary|Chairman)', re.I)
NON_T  = re.compile(r'^(Vice |Deputy |Crown Prince|First Lady|Foreign Minister|Minister|Secretary[- ]General|NATO|UN )', re.I)
def is_hogs(visitor):
    v = str(visitor or '')
    return bool(HOGS_T.match(v)) and not bool(NON_T.match(v))
