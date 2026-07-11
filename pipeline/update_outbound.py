# -*- coding: utf-8 -*-
"""月度更新 - 出访方向(中美元首)
数据源: (1) 国务院历史办 travels 仓库(美国官方, 年度更新)
       (2) 维基百科出访列表(习近平全序列 + 美国现任总统补充)
输出: out/outbound_trips.csv"""
import re, os, json, subprocess, sys
import xml.etree.ElementTree as ET
import pandas as pd
from lxml import html as LH
from datetime import datetime
from common import wiki_page, expand_table, parse_dates_any, classify_trip, fetch

OUT = 'out'; os.makedirs(OUT, exist_ok=True)
CUR_YEAR = datetime.now().year

WIKI_PAGES = {  # 领导人 -> (维基页面, 起始年)
    'Xi Jinping': ('List of international presidential trips made by Xi Jinping', 2013),
    'Barack Obama': ('List of international presidential trips made by Barack Obama', 2013),
    'Donald J. Trump': ('List of international presidential trips made by Donald Trump', 2017),
    'Joseph R. Biden': ('List of international presidential trips made by Joe Biden', 2021),
}
OTH_FILES = ['obama-barack','trump-donald-j','biden-joseph-r']  # 新总统上任时在此追加

def load_oth():
    """克隆/更新官方仓库并解析"""
    if not os.path.exists('travels'):
        subprocess.run(['git','clone','--depth','1','https://github.com/HistoryAtState/travels.git'], check=True)
    else:
        subprocess.run(['git','-C','travels','pull','--ff-only'], check=False)
    rows = []
    for f in OTH_FILES:
        tree = ET.parse(f'travels/president-travels/{f}.xml')
        for t in tree.getroot().findall('trip'):
            st = t.findtext('start-date')
            if not st or int(st[:4]) < 2013: continue
            rows.append({'leader':t.findtext('name'),'start_date':st,'end_date':t.findtext('end-date'),
                'destination_country':t.findtext('country'),'locale':(t.findtext('locale') or '').strip(),
                'details':' '.join((t.findtext('remarks') or '').split()),
                'source':'US State Dept Office of the Historian'})
    return pd.DataFrame(rows)

def parse_wiki(leader, title, y0):
    fn = f'{OUT}/wiki_{leader.split()[0].lower()}.html'
    if not wiki_page(title, fn):
        print(f'  [warn] 维基页面获取失败: {title}', file=sys.stderr); return []
    doc = LH.parse(fn); trips = []
    for s in doc.xpath('//section'):
        hs = s.xpath('./*[self::h2 or self::h3]')
        if not hs: continue
        tt = hs[0].text_content().strip()
        if not re.fullmatch(r'20\d\d', tt): continue
        if any('Future' in (a.text_content() or '') for a in s.xpath('ancestor::section/*[self::h2 or self::h3]')): continue
        year = int(tt)
        if not (y0 <= year <= CUR_YEAR): continue
        for t in s.xpath('.//table'):
            grid = expand_table(t)
            if not grid or 'Country' not in grid[0]: continue
            ci = {h:i for i,h in enumerate(grid[0])}
            def g(row,*ns):
                for n in ns:
                    if n in ci and ci[n] < len(row): return row[ci[n]]
                return ''
            for row in grid[1:]:
                dates, country = g(row,'Dates','Date(s)'), g(row,'Country')
                if not country or not dates: continue
                st, en = parse_dates_any(dates, year)
                if not st: continue
                trips.append({'leader':leader,'start_date':st,'end_date':en,
                    'destination_country':country,'locale':g(row,'Locations','Areas visited'),
                    'details':' '.join(g(row,'Details').split())[:400],'source':'Wikipedia'})
    return trips

CNORM = {'South Korea':'KOR','Korea, South':'KOR','Korea, Republic of':'KOR',
 'China':'CHN',"China, People's Republic of":'CHN','China, People\u2019s Republic of':'CHN',
 'United Kingdom':'GBR','United Kingdom (Northern Ireland)':'GBR','United Kingdom (Wales)':'GBR',
 'Burma':'MMR','Myanmar':'MMR','Myanmar (Burma)':'MMR','Vatican City':'VAT','Vatican City State':'VAT',
 'Palestinian Authority':'PSE','West Bank':'PSE','Palestinian Authority (West Bank)':'PSE'}
def cnorm(c): return CNORM.get(re.sub(r'\s+',' ',str(c)).strip(), re.sub(r'\s+',' ',str(c)).strip())

def main():
    oth = load_oth()
    print(f'官方(OTH): {len(oth)} 条')
    all_wiki = []
    for leader,(title,y0) in WIKI_PAGES.items():
        w = parse_wiki(leader, title, y0)
        print(f'维基 {leader}: {len(w)} 条')
        all_wiki += w
    # 并集: 中国全用维基; 美国以 OTH 为主, 维基仅补 OTH 缺失(同国 ±5 天)
    cn = [t for t in all_wiki if t['leader']=='Xi Jinping']
    us_wiki = [t for t in all_wiki if t['leader']!='Xi Jinping']
    sup = []
    for t in us_wiki:
        ws = datetime.fromisoformat(t['start_date'])
        m = oth[(oth['destination_country'].apply(cnorm)==cnorm(t['destination_country']))]
        hit = any(abs((ws-datetime.fromisoformat(r)).days)<=5 for r in m['start_date'])
        if not hit:
            t['source'] = 'Wikipedia (supplement)'
            sup.append(t)
    print(f'维基补充美国缺失: {len(sup)} 条')
    df = pd.concat([pd.DataFrame(cn).assign(country_leader='China'),
                    oth.assign(country_leader='United States'),
                    pd.DataFrame(sup).assign(country_leader='United States')], ignore_index=True)
    df['year'] = df['start_date'].str[:4].astype(int)
    res = df['details'].apply(classify_trip)
    df['flags'] = [r[0] for r in res]; df['aspi_comparable'] = [r[1] for r in res]
    df = df.sort_values(['country_leader','start_date']).reset_index(drop=True)
    df.to_csv(f'{OUT}/outbound_trips.csv', index=False)
    print(f'\n=> {OUT}/outbound_trips.csv: {len(df)} 条 '
          f'(中国 {len(df[df.country_leader=="China"])}, 美国 {len(df[df.country_leader=="United States"])})')
    return df

if __name__ == '__main__':
    main()
