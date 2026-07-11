# -*- coding: utf-8 -*-
"""访华历史回填 (2013-2024, 约819次)
架构: Wayback Machine 快照收割历史列表页 -> 提取文章URL+标题 -> 外交部现网抓正文 -> 复用 update_inbound_cn 的抽取管线
注意: 需要环境能访问 web.archive.org (当前沙箱出口策略拦截, 在本地/服务器运行即可)"""
import json, re, subprocess, time, sys, os
from common import UA, fetch

CDX = ('https://web.archive.org/cdx/search/cdx?url={target}&from={y}0101&to={y}1231'
       '&output=json&collapse=timestamp:8&filter=statuscode:200')
TARGETS = ['www.fmprc.gov.cn/web/zyxw/','www.mfa.gov.cn/web/zyxw/',
           'www.fmprc.gov.cn/mfa_chn/zyxw_602251/']  # 域名/栏目随年代变化

def snapshots(year):
    snaps = []
    for tg in TARGETS:
        r = subprocess.run(['curl','-sL','-A',UA,'-m','60', CDX.format(target=tg, y=year)],
                           capture_output=True, text=True)
        try: rows = json.loads(r.stdout)
        except: continue
        snaps += [(row[1], row[2]) for row in rows[1:]]
        time.sleep(1)
    return snaps  # [(timestamp, original_url)]

def harvest_year(year, outdir='backfill'):
    os.makedirs(outdir, exist_ok=True)
    seen, items = set(), []
    for ts, orig in snapshots(year):
        wb_url = f'https://web.archive.org/web/{ts}/{orig}'
        fn = f'{outdir}/snap_{ts}.html'
        if not os.path.exists(fn) and not fetch(wb_url, fn, timeout=60): continue
        txt = open(fn, encoding='utf-8', errors='ignore').read()
        for m in re.finditer(r'href="([^"]*t20\d{6}[^"]*?\.shtml)"[^>]*>([^<]{4,80})', txt):
            h, t = m.groups()
            if h in seen: continue
            seen.add(h); items.append({'href':h, 'title':t.strip(), 'snap':ts})
        time.sleep(2)  # 尊重 wayback 限速
    json.dump(items, open(f'{outdir}/titles_{year}.json','w'), ensure_ascii=False)
    print(f'{year}: 收割 {len(items)} 篇文章标题 -> {outdir}/titles_{year}.json')
    print('下一步: 将标题送入 update_inbound_cn.extract_visits 流程(正文从 mfa.gov.cn 现网抓取,'
          '若 404 再回退 wayback 正文快照)')
    return items

if __name__ == '__main__':
    years = [int(y) for y in sys.argv[1:]] or list(range(2013, 2025))
    for y in years:
        harvest_year(y)
