# -*- coding: utf-8 -*-
"""访华回填·gov.cn 领导活动(ldhd)通道 (2013-2014)
背景: MFA zyxw 2013-14 Wayback 捕获稀疏(2013 覆盖仅 29%), 而 gov.cn/ldhd 栏目 2013 年内容页
快照密集(2,008 篇, 2014 迁栏后仅 255 篇, 2015 起为 0 — 后续年份该走 /xinwen 或 MFA /eng/)。
URL 自带日期(/ldhd/2013-03/22/content_NNN.htm), 无 MFA 流水号之痛; 正文同为新华社通稿,
标题筛选/地点判别/去重逻辑全部复用 backfill_china_inbound。
阶段: inventory / fetch / extract / merge / all
用法: python3 backfill_govcn_ldhd.py all
"""
import os, re, sys, subprocess, time
import pandas as pd
from datetime import datetime
from common import UA
from backfill_china_inbound import HOST, ACT, FTITLE, EXCL, CN_PLACES, PAT1, PAT2, curl

BF = 'backfill/govcn'
ART = f'{BF}/art'
os.makedirs(ART, exist_ok=True)
CDX = 'https://web.archive.org/cdx/search/cdx'
TARGETS = ['www.gov.cn/ldhd/2013', 'www.gov.cn/ldhd/2014']
KEY = re.compile(r'/ldhd/(20\d\d)-(\d\d)/(\d\d)/(content_\d+)\.htm')


def inventory():
    rows = {}
    for tg in TARGETS:
        fn = f"{BF}/cdx_{tg.rsplit('/', 1)[-1]}.txt"
        if not os.path.exists(fn):
            for attempt in range(4):
                code = subprocess.run(['curl', '-sG', '-A', UA, '-m', '240', CDX,
                    '--data-urlencode', f'url={tg}', '--data-urlencode', 'matchType=prefix',
                    '--data-urlencode', 'filter=statuscode:200',
                    '--data-urlencode', 'collapse=urlkey', '--data-urlencode', 'fl=timestamp,original',
                    '-o', fn + '.part', '-w', '%{http_code}'], capture_output=True, text=True).stdout.strip()
                if code == '200':
                    os.rename(fn + '.part', fn); break
                time.sleep(10 * (attempt + 1))
            else:
                print(f'[warn] CDX 失败: {tg}'); continue
            time.sleep(2)
        for ln in open(fn):
            p = ln.split()
            if len(p) != 2: continue
            m = KEY.search(p[1])
            if not m: continue
            k = m.group(4)
            if k not in rows:
                rows[k] = (p[0], p[1], f'{m.group(1)}-{m.group(2)}-{m.group(3)}')
    with open(f'{BF}/inventory.tsv', 'w') as f:
        for k, (ts, u, d) in sorted(rows.items()):
            f.write(f'{k}\t{ts}\t{u}\t{d}\n')
    yc = {}
    for _, (_, _, d) in rows.items(): yc[d[:4]] = yc.get(d[:4], 0) + 1
    print(f'inventory: {len(rows)} 篇唯一文章 -> {BF}/inventory.tsv')
    for y in sorted(yc): print(f'  {y}: {yc[y]}')
    return rows


def fetch_one(k, ts, u, d):
    out = f'{ART}/{k}.html'
    code, backoff = None, 30
    for attempt in range(5):
        code = curl(f'https://web.archive.org/web/{ts}id_/{u}', out, timeout=60)
        if code == '200': return True
        if code in ('429', '503', '000'):
            time.sleep(backoff); backoff = min(backoff * 2, 300)
        else: break
    if os.path.exists(out): os.remove(out)
    with open(f'{BF}/fetch_fail.log', 'a') as f: f.write(f'{k}\t{ts}\t{u}\t{code}\n')
    return False


def fetch_all(max_n=None, workers=3):  # Wayback 按 IP 限并发, >4 反而全线变慢
    from concurrent.futures import ThreadPoolExecutor
    todo = [ln.rstrip('\n').split('\t') for ln in open(f'{BF}/inventory.tsv')]
    done = set(os.listdir(ART))
    todo = [t for t in todo if f'{t[0]}.html' not in done]
    if max_n: todo = todo[:max_n]
    print(f'fetch: 待抓 {len(todo)} 篇 (已有 {len(done)}), {workers} 并发')
    ok = fail = n = 0
    with ThreadPoolExecutor(workers) as ex:
        for good in ex.map(lambda t: fetch_one(*t), todo):
            n += 1
            if good: ok += 1
            else: fail += 1
            if n % 100 == 0: print(f'  {n}/{len(todo)} ok={ok} fail={fail}', flush=True)
    print(f'fetch 完成: ok={ok} fail={fail}')


def parse_article(path):
    try: txt = open(path, encoding='utf-8', errors='ignore').read()
    except OSError: return None
    tm = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', txt) or re.search(r'<title>([^<]*)</title>', txt)
    if not tm: return None
    title = re.sub(r'<[^>]+>', '', tm.group(1)).strip()
    title = re.sub(r'[_—－-]*(中央政府门户网站|中国政府网|政府信息公开专栏).*$', '', title).strip()
    if not title: return None
    body = ' '.join(re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>', ' ', txt).split())
    return title, body


def extract():
    dates = {ln.split('\t')[0]: ln.rstrip('\n').split('\t')[3] for ln in open(f'{BF}/inventory.tsv')}
    recs = []
    n_all = n_cand = 0
    for fn in sorted(os.listdir(ART)):
        k = fn[:-5]
        if k not in dates: continue
        p = parse_article(f'{ART}/{fn}')
        if not p: continue
        t, body = p
        d = dates[k]
        n_all += 1
        if not (re.search(HOST, t) and re.search(ACT, t) and re.search(FTITLE, t)) or re.search(EXCL, t):
            continue
        n_cand += 1
        m = re.search(r'\d{1,2}月\d{1,2}日[^，。]{0,10}，', body)
        seg = body[m.start():m.start() + 1500] if m else body[-3000:]
        if re.search(r'视频|通电话|云会见', seg[:250]): continue
        lm = re.search(r'在([^，。]{1,20}?)(?:会见|同|与|为|举行|出席|亲切)', seg[:250])
        loc = lm.group(1) if lm else ''
        in_cn = any(pl in loc for pl in CN_PLACES) if loc else bool(
            re.search(r'来华|访华|欢迎.{0,20}访问|抵达北京', seg[:250]))
        if not in_cn: continue
        vm = re.search(r'(国事访问|正式访问|工作访问|来华出席)', seg)
        recs.append({'date': d, 'title': t, 'visit_type': vm.group(1) if vm else ''})
    print(f'解析 {n_all} 篇, 标题候选 {n_cand}, 判定在华 {len(recs)}')
    visits = {}
    for r in sorted(recs, key=lambda x: x['date']):
        m = PAT1.search(r['title'])
        if m: country, title, name = m.groups()
        else:
            m2 = PAT2.search(r['title'])
            if not m2: continue
            country, name = m2.groups(); title = '国家主席/总书记'
        name = re.sub(r'(时指出.*|时强调.*|时表示.*|宣布.*|指出.*|强调.*|表示.*|会谈.*|举行.*|共同.*|并.*|夫妇.*|和太后.*|和欧盟委员会.*)$', '', name).strip()
        if not name: continue
        d = datetime.fromisoformat(r['date']); merged = False
        for v in visits.values():
            if v['country'] == country and (v['name'][:3] == name[:3] or name in v['name'] or v['name'] in name) \
               and abs((d - datetime.fromisoformat(v['first'])).days) <= 10:
                v['last'] = max(v['last'], r['date']); v['n_articles'] += 1
                if r['visit_type'] and v['visit_type'] in ('', '来华出席'): v['visit_type'] = r['visit_type']
                merged = True; break
        if not merged:
            visits[(country, name, r['date'])] = {'country': country, 'leader_title': title, 'name': name,
                'first': r['date'], 'last': r['date'], 'visit_type': r['visit_type'] or '会见/会谈(双边)', 'n_articles': 1}
    out = pd.DataFrame(sorted(visits.values(), key=lambda v: v['first']))
    out.to_csv(f'{BF}/inbound_cn_govcn.csv', index=False)
    if len(out):
        print(f'去重后访华 {len(out)} 次 -> {BF}/inbound_cn_govcn.csv')
        for y, c in out['first'].str[:4].value_counts().sort_index().items(): print(f'  {y}: {c}')
    return out


def merge():
    """与 master 去重并入: 键同主管线 (country+名字前2字+月)。"""
    master_fn = 'out/inbound_cn_master.csv'
    master = pd.read_csv(master_fn)
    fn = f'{BF}/inbound_cn_govcn.csv'
    bf = pd.read_csv(fn)
    bf['source'] = 'gov.cn ldhd wayback backfill'
    key = set(master['country'] + master['name'].str[:2] + master['first'].astype(str).str[:7])
    bf = bf[~(bf['country'] + bf['name'].str[:2] + bf['first'].str[:7]).isin(key)]
    master = pd.concat([master, bf], ignore_index=True).sort_values('first')
    master.to_csv(master_fn, index=False)
    print(f'merge: 新增 {len(bf)} 条, master 累计 {len(master)} 条')
    if len(bf):
        for y, c in bf['first'].str[:4].value_counts().sort_index().items(): print(f'  {y}: +{c}')
    return master


if __name__ == '__main__':
    stage = sys.argv[1] if len(sys.argv) > 1 else 'all'
    max_n = None
    if '--max' in sys.argv: max_n = int(sys.argv[sys.argv.index('--max') + 1])
    if stage in ('inventory', 'all'): inventory()
    if stage in ('fetch', 'all'): fetch_all(max_n)
    if stage in ('extract', 'all'): extract()
    if stage in ('merge', 'all'): merge()
