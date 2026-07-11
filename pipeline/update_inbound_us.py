# -*- coding: utf-8 -*-
"""月度更新 - 访美方向
数据源: (1) 国务院历史办 visits 仓库(官方, 年度更新)
       (2) 维基百科六大洲访美列表(补当年增量)
输出: out/inbound_us.csv"""
import re, os, json, subprocess, sys
import xml.etree.ElementTree as ET
import pandas as pd
from lxml import html as LH
from datetime import datetime
from common import wiki_page, expand_table, is_hogs, MONTHS

OUT='out'; os.makedirs(OUT, exist_ok=True)
CUR_YEAR = datetime.now().year
CONTINENTS = ['Africa','Asia','Europe','South America','Oceania','North America and the Caribbean']

def load_oth():
    if not os.path.exists('visits'):
        subprocess.run(['git','clone','--depth','1','https://github.com/HistoryAtState/visits.git'], check=True)
    else:
        subprocess.run(['git','-C','visits','pull','--ff-only'], check=False)
    rows=[]
    for f in ['2010','2020']:
        tree = ET.parse(f'visits/data/{f}.xml')
        for v in tree.getroot().findall('visit'):
            st = v.findtext('start-date')
            if not st or st < '2013': continue
            rows.append({'start':st,'end':v.findtext('end-date'),
                'visitor':' '.join((v.findtext('visitor') or '').split()),
                'from_country':v.findtext('from'),
                'description':' '.join((v.findtext('description') or '').split()),
                'source':'US State Dept Office of the Historian'})
    return pd.DataFrame(rows)

def pdate(s):
    m = re.match(r'(\w+) (\d{1,2}),? (\d{4})', str(s).strip())
    return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}" if m and m.group(1) in MONTHS else None

def parse_continental(after_date):
    recs=[]
    for p in CONTINENTS:
        fn = f"{OUT}/us_inb_{p.split()[0]}.html"
        if not wiki_page(f"List of diplomatic visits to the United States from {p}", fn):
            print(f'  [warn] fail {p}', file=sys.stderr); continue
        doc = LH.parse(fn)
        for s in doc.xpath('//section'):
            hs = s.xpath('./*[self::h2 or self::h3]')
            if not hs: continue
            country = hs[0].text_content().strip()
            if country in ('See also','References','External links','Notes'): continue
            for t in s.xpath('./table'):
                grid = expand_table(t)
                if not grid or 'Start' not in grid[0]: continue
                ci = {h:i for i,h in enumerate(grid[0])}
                for row in grid[1:]:
                    def g(n): return row[ci[n]] if n in ci and ci[n]<len(row) else ''
                    st = pdate(g('Start'))
                    if not st or st <= after_date: continue
                    recs.append({'start':st,'end':pdate(g('End')) or st,
                        'visitor':f"{g('Title')} {g('Guest')}".strip(),
                        'from_country':re.sub(r'\s*\(.*\)$','',country),
                        'description':' '.join(g('Reason').split())[:300],
                        'source':'Wikipedia continental lists (supplement)'})
    return recs

def main():
    oth = load_oth()
    latest = oth['start'].max()
    print(f'官方(OTH): {len(oth)} 条, 截至 {latest}')
    sup = parse_continental(latest)
    print(f'维基补充 {latest} 之后: {len(sup)} 条')
    df = pd.concat([oth, pd.DataFrame(sup)], ignore_index=True) if sup else oth
    df['year'] = df['start'].str[:4].astype(int)
    df['is_hogs'] = df['visitor'].apply(is_hogs)
    df = df[df['is_hogs']].sort_values('start').reset_index(drop=True)
    df['visit_id'] = [f'USIN-{i+1:04d}' for i in range(len(df))]
    df.to_csv(f'{OUT}/inbound_us.csv', index=False)
    print(f'=> {OUT}/inbound_us.csv: {len(df)} 条 (HOGS 口径)')
    return df

if __name__ == '__main__':
    main()
