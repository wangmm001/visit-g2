# -*- coding: utf-8 -*-
"""访华回填·人民日报电子版通道 (2013, 可扩年份)
背景: 现网 paper.people.com.cn 已反爬 403, 但 Wayback 对 2013 版面捕获 13,099 个
(版面页 nbs.*.htm 1,434 + 文章页 nw.*.htm ~11.6k)。版面页自带全部文章标题 ->
免抓正文即可标题筛选, 只对命中者取文章正文判地点。标题/地点/去重逻辑复用主管线。
阶段: inventory / layouts / extract / merge / all
"""
import os, re, sys, subprocess, time
import pandas as pd
from datetime import datetime
from common import UA
from backfill_china_inbound import HOST, ACT, FTITLE, EXCL, CN_PLACES, PAT1, PAT2, curl

BF = 'backfill/rmrb'
LAY = f'{BF}/layout'
ART = f'{BF}/art'
for d in (LAY, ART): os.makedirs(d, exist_ok=True)
CDX = 'https://web.archive.org/cdx/search/cdx'
YEARS = ['2013']


def read_html(path):
    raw = open(path, 'rb').read()
    for enc in ('utf-8', 'gbk'):
        try: return raw.decode(enc)
        except UnicodeDecodeError: continue
    return raw.decode('utf-8', errors='ignore')


def inventory():
    """CDX 前缀查询 -> 版面清单 layouts.tsv + 文章捕获映射 articles.tsv"""
    lay, art = {}, {}
    for y in YEARS:
        fn = f'{BF}/cdx_{y}.txt'
        if not os.path.exists(fn):
            for attempt in range(4):
                code = subprocess.run(['curl', '-sG', '-A', UA, '-m', '240', CDX,
                    '--data-urlencode', f'url=paper.people.com.cn/rmrb/html/{y}',
                    '--data-urlencode', 'matchType=prefix', '--data-urlencode', 'filter=statuscode:200',
                    '--data-urlencode', 'collapse=urlkey', '--data-urlencode', 'fl=timestamp,original',
                    '-o', fn + '.part', '-w', '%{http_code}'], capture_output=True, text=True).stdout.strip()
                if code == '200':
                    os.rename(fn + '.part', fn); break
                time.sleep(10 * (attempt + 1))
            else:
                print(f'[warn] CDX 失败: {y}'); continue
        for ln in open(fn):
            p = ln.split()
            if len(p) != 2: continue
            m = re.search(r'/(nbs\.D110000renmrb_\d+)\.htm', p[1])
            if m:
                dm = re.search(r'/html/(20\d\d)-(\d\d)/(\d\d)/', p[1])
                if dm: lay[f'{dm.group(1)}-{dm.group(2)}-{dm.group(3)}_{m.group(1)}'] = (p[0], p[1])
                continue
            m = re.search(r'/(nw\.D110000renmrb_(20\d{6})_[\d\-]+)\.htm', p[1])
            if m and m.group(1) not in art: art[m.group(1)] = (p[0], p[1])
    with open(f'{BF}/layouts.tsv', 'w') as f:
        for k, (ts, u) in sorted(lay.items()): f.write(f'{k}\t{ts}\t{u}\n')
    with open(f'{BF}/articles.tsv', 'w') as f:
        for k, (ts, u) in sorted(art.items()): f.write(f'{k}\t{ts}\t{u}\n')
    days = len({k.split('_')[0] for k in lay})
    print(f'inventory: 版面 {len(lay)} 页 (覆盖 {days} 天), 文章捕获 {len(art)} 篇')


def fetch_one(out_dir, k, ts, u):
    out = f'{out_dir}/{k}.html'
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


def _fetch_list(todo, out_dir, workers=3):
    from concurrent.futures import ThreadPoolExecutor
    done = set(os.listdir(out_dir))
    todo = [t for t in todo if f'{t[0]}.html' not in done]
    print(f'fetch: 待抓 {len(todo)} (已有 {len(done)}), {workers} 并发')
    ok = fail = n = 0
    with ThreadPoolExecutor(workers) as ex:
        for good in ex.map(lambda t: fetch_one(out_dir, *t), todo):
            n += 1
            if good: ok += 1
            else: fail += 1
            if n % 200 == 0: print(f'  {n}/{len(todo)} ok={ok} fail={fail}', flush=True)
    print(f'fetch 完成: ok={ok} fail={fail}')


def layouts(max_n=None):
    todo = [ln.rstrip('\n').split('\t') for ln in open(f'{BF}/layouts.tsv')]
    if max_n: todo = todo[:max_n]
    _fetch_list(todo, LAY)


def candidates():
    """版面页 -> 标题筛选 -> 候选文章 (key, date, title)"""
    cand = {}
    for fn in sorted(os.listdir(LAY)):
        txt = read_html(f'{LAY}/{fn}')
        dm = re.match(r'(20\d\d-\d\d-\d\d)_', fn)
        if not dm: continue
        d = dm.group(1)
        # 目录锚点两种形态: <a href=nw...?div=-1><script>document.write(view("题"))</script></a>
        #                与 <a href=nw...><div id=mp_...>题</div></a>; href 无引号
        pairs = re.findall(r'href=["\']?[^"\'>\s]*?(nw\.D110000renmrb_\d+_[\d\-]+)\.htm[^>]*>\s*'
                           r'<script>document\.write\(view\("([^"]+)"\)', txt)
        pairs += re.findall(r'href=["\']?[^"\'>\s]*?(nw\.D110000renmrb_\d+_[\d\-]+)\.htm[^>]*>\s*'
                            r'<div[^>]*>([^<]+)</div>', txt)
        for k, t in pairs:
            t = re.sub(r'<[^>]+>', '', t).strip()  # 标题内嵌 <BR/>
            if not (re.search(HOST, t) and re.search(ACT, t) and re.search(FTITLE, t)) or re.search(EXCL, t):
                continue
            cand[k] = (d, t)
    return cand


def extract():
    cand = candidates()
    print(f'版面标题命中 {len(cand)} 篇')
    artmap = {}
    for ln in open(f'{BF}/articles.tsv'):
        k, ts, u = ln.rstrip('\n').split('\t')
        artmap[k] = (ts, u)
    # 抓候选正文: 优先文章捕获映射; 无捕获则用 Wayback 就近重定向(去掉 id_ 的时间戳容错)
    todo = []
    for k, (d, t) in sorted(cand.items()):
        if k in artmap: ts, u = artmap[k]
        else:
            ts = d.replace('-', '') + '120000'
            u = f"http://paper.people.com.cn/rmrb/html/{d[:4]}-{d[5:7]}/{d[8:]}/{k}.htm"
        todo.append((k, ts, u))
    _fetch_list(todo, ART)
    recs = []
    for k, (d, t) in sorted(cand.items()):
        p = f'{ART}/{k}.html'
        if not os.path.exists(p): continue
        txt = read_html(p)
        body = ' '.join(re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>', ' ', txt).split())
        m = re.search(r'\d{1,2}月\d{1,2}日[^，。]{0,10}，', body)
        seg = body[m.start():m.start() + 1500] if m else body[-3000:]
        if re.search(r'视频|通电话|云会见', seg[:250]): continue
        lm = re.search(r'在([^，。]{1,20}?)(?:会见|同|与|为|举行|出席|亲切)', seg[:250])
        loc = lm.group(1) if lm else ''
        in_cn = any(pl in loc for pl in CN_PLACES) if loc else bool(
            re.search(r'来华|访华|欢迎.{0,20}访问|抵达北京', seg[:250]))
        if not in_cn: continue
        vm = re.search(r'(国事访问|正式访问|工作访问|来华出席)', seg)
        # 报纸标题常省略人名("习近平会见津巴布韦总统") -> 标题抓不到时从事件句兜底
        recs.append({'date': d, 'title': t, 'seg': seg[:400], 'visit_type': vm.group(1) if vm else ''})
    print(f'判定在华 {len(recs)}')
    visits = {}
    for r in sorted(recs, key=lambda x: x['date']):
        m = PAT1.search(r['title']) or PAT1.search(r['seg'])
        if m: country, title, name = m.groups()
        else:
            m2 = PAT2.search(r['title']) or PAT2.search(r['seg'])
            if not m2: continue
            country, name = m2.groups(); title = '国家主席/总书记'
        name = re.sub(r'(时指出.*|时强调.*|时表示.*|宣布.*|指出.*|强调.*|表示.*|会谈.*|举行.*|共同.*|并.*|夫妇.*|和太后.*|和欧盟委员会.*)$', '', name).strip()
        if not name: continue
        # 正文兜底绕过了标题级 EXCL -> 对提取结果再筛一遍
        if re.search(EXCL, country + title + name): continue
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
    out.to_csv(f'{BF}/inbound_cn_rmrb.csv', index=False)
    if len(out):
        print(f'去重后访华 {len(out)} 次 -> {BF}/inbound_cn_rmrb.csv')
        for y, c in out['first'].str[:4].value_counts().sort_index().items(): print(f'  {y}: {c}')
    return out


def merge():
    master_fn = 'out/inbound_cn_master.csv'
    master = pd.read_csv(master_fn)
    bf = pd.read_csv(f'{BF}/inbound_cn_rmrb.csv')
    bf['source'] = '人民日报 rmrb wayback backfill'
    # 报纸见报日 = 事件日+1, 月键会在月末漏判 -> 用 ±12 天窗 (同 summits 阶段)
    md = [(r['country'][:2], str(r['name'])[:2], datetime.fromisoformat(str(r['first'])))
          for _, r in master.iterrows()]
    keep = []
    for _, r in bf.iterrows():
        d = datetime.fromisoformat(r['first'])
        if any(c == r['country'][:2] and n == str(r['name'])[:2] and abs((d - t).days) <= 12
               for c, n, t in md): continue
        keep.append(r)
    bf = pd.DataFrame(keep)
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
    if stage in ('layouts', 'all'): layouts(max_n)
    if stage in ('extract', 'all'): extract()
    if stage in ('merge', 'all'): merge()
