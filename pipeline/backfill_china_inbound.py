# -*- coding: utf-8 -*-
"""访华历史回填 v2 (2013-2025Q1, ASPI 口径约819次)
架构: Wayback CDX 前缀查询枚举文章快照 -> 逐篇抓原始正文(id_模式) -> 标题筛选+地点判别 -> 去重出访华记录
v1 教训: 老站文章是流水号 t\\d+.shtml 而非 t20\\d{6} 日期式; 现网老文章已成"系统维护"壳页, 正文只能取快照。
阶段: inventory / fetch / extract / merge / all  (fetch 可断点续传, 全量约 1 万篇 / 4-6h)
用法: python3 backfill_china_inbound.py all
      python3 backfill_china_inbound.py extract --years 2013   # 试点单年
"""
import json, re, os, sys, subprocess, time
import pandas as pd
from datetime import datetime
from common import UA

BF = 'backfill'
ART = f'{BF}/art'
os.makedirs(ART, exist_ok=True)

# 栏目 URL 随年代迁移: 老站(2013-2015) -> 中期(2015-2021) -> 新站(2021-, 且回挂了全部历史)
TARGETS = ['www.fmprc.gov.cn/mfa_chn/zyxw_602251/*',
           'www.fmprc.gov.cn/web/zyxw/*',
           'www.mfa.gov.cn/web/zyxw/*']
CDX = 'https://web.archive.org/cdx/search/cdx'

# ---- 抽取规则 (在 update_inbound_cn 基础上扩主人名单: 2013Q1 胡温, 2013-2023 总理李克强) ----
HOST = r'(习近平|李强|李克强|胡锦涛|温家宝)'
ACT = r'(会见|会谈|举行欢迎仪式|共同会见记者)'
FTITLE = r'(总统|总理|首相|国王|国家元首|埃米尔|苏丹|大公|亲王|委员长|临时总统|总统当选人|内阁总理|联邦总理|主席)'
EXCL = r'外长|外交大臣|副总理|副总统|王储|国家杜马|国际奥委会|议长|前总统|前总理|夫人|特使|特别代表|国会主席|大呼拉尔|参议院|众议院|国民议会|人民院|联邦院|基金会|副首相|第一副主席|副主席|世界经济论坛|国际商会|非盟|联邦委员会|国际篮联|红十字'
CN_PLACES = ['北京','人民大会堂','钓鱼台','中南海','天津','上海','杭州','成都','广州','深圳','西安','哈尔滨','三亚','博鳌','厦门','青岛','郑州','南京','武汉','重庆','南海']
PAT1 = re.compile(r'(?:会见|同|与)([一-龥]{2,12}?)(总统|总理|国王|首相|国家元首|埃米尔|苏丹|大公|亲王|委员长|临时总统|总统当选人|内阁总理|联邦总理|主席)([一-龥·]{1,15})')
PAT2 = re.compile(r'(?:会见|同|与)([一-龥]{2,5})[一-龥、党中央委员会总书记第一记劳动]{0,28}(?:国家主席|国务委员长|国家元首)([一-龥·\-]{1,12})')


def curl(url, out=None, timeout=90):
    args = ['curl', '-sL', '-A', UA, '-m', str(timeout), '-w', '%{http_code}', url]
    if out: args += ['-o', out]
    else: args += ['-o', '/dev/null']
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout.strip()[-3:]


def art_key(url):
    """文章去重键: 老/中期共享流水号空间, 新站日期_ID"""
    m = re.search(r'/(t20\d{6}_\d+|t\d+)\.shtml', url)
    return m.group(1) if m else None


def inventory():
    """CDX 枚举三个栏目前缀下全部 200 快照, 按年分片重试, 合并去重 -> backfill/inventory.tsv"""
    rows = {}
    for tg in TARGETS:
        slug = re.sub(r'[^a-z0-9]+', '_', tg)
        for y in range(2013, 2026):
            fn = f'{BF}/cdx_{slug}{y}.txt'
            if not os.path.exists(fn):
                for attempt in range(4):
                    code = subprocess.run(['curl', '-sG', '-A', UA, '-m', '240', CDX,
                        '--data-urlencode', f'url={tg}', '--data-urlencode', f'from={y}0101',
                        '--data-urlencode', f'to={y}1231', '--data-urlencode', 'filter=statuscode:200',
                        '--data-urlencode', 'collapse=urlkey', '--data-urlencode', 'fl=timestamp,original',
                        '-o', fn + '.part', '-w', '%{http_code}'], capture_output=True, text=True).stdout.strip()
                    if code == '200':
                        os.rename(fn + '.part', fn); break
                    time.sleep(10 * (attempt + 1))
                else:
                    print(f'[warn] CDX 失败: {tg} {y}'); continue
                time.sleep(2)
            for ln in open(fn):
                p = ln.split()
                if len(p) != 2: continue
                k = art_key(p[1])
                if k and k not in rows: rows[k] = (p[0], p[1])
    with open(f'{BF}/inventory.tsv', 'w') as f:
        for k, (ts, u) in sorted(rows.items()):
            f.write(f'{k}\t{ts}\t{u}\n')
    yrs = {}
    for k in rows:
        y = k[1:5] if re.match(r't20\d{6}_', k) else '流水号(待抓)'
        yrs[y] = yrs.get(y, 0) + 1
    print(f'inventory: {len(rows)} 篇唯一文章 -> {BF}/inventory.tsv')
    for y in sorted(yrs): print(f'  {y}: {yrs[y]}')
    return rows


def fetch_one(k, ts, u):
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
    """抓 Wayback 原始正文(id_模式), 小并发+429退避, 断点续传"""
    from concurrent.futures import ThreadPoolExecutor
    todo = [ln.rstrip('\n').split('\t') for ln in open(f'{BF}/inventory.tsv')]
    # 日期式 URL 直接暴露发布年, 2013 前的不在回填范围; 流水号无从判断只能全抓
    todo = [t for t in todo if not (re.match(r't20\d{6}_', t[0]) and t[0][1:5] < '2013')]
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


def parse_article(k, path):
    """-> (date, title, body) 或 None"""
    try: txt = open(path, encoding='utf-8', errors='ignore').read()
    except OSError: return None
    tm = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', txt) or re.search(r'<title>([^<]*)</title>', txt)
    if not tm: return None
    title = re.sub(r'<[^>]+>', '', tm.group(1)).strip()
    title = re.sub(r'[_—-]*(中华人民共和国外交部|外交部网站).*$', '', title).strip()
    if not title or title in ('重要新闻', '系统维护'): return None
    body = ' '.join(re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>', ' ', txt).split())
    d = None
    m = re.match(r't(20\d\d)(\d\d)(\d\d)_', k)
    if m: d = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'
    else:
        m = re.search(r'(20\d\d)[/\-年](\d{1,2})[/\-月](\d{1,2})', txt)
        if m: d = f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    if not d: return None
    return d, title, body


def extract(years=None):
    """标题筛候选 -> 正文判地点 -> 领导人+时间窗去重 -> backfill/inbound_cn_backfill.csv"""
    recs = []
    n_all = n_cand = 0
    for fn in sorted(os.listdir(ART)):
        p = parse_article(fn[:-5], f'{ART}/{fn}')
        if not p: continue
        d, t, body = p
        n_all += 1
        if years and int(d[:4]) not in years: continue
        if not (re.search(HOST, t) and re.search(ACT, t) and re.search(FTITLE, t)) or re.search(EXCL, t):
            continue
        n_cand += 1
        # 地点判别: 正文事件段开头找 "在XX" 或 来华/访华 线索
        m = re.search(r'\d{1,2}月\d{1,2}日[^，。]{0,10}，', body)
        seg = body[m.start():m.start() + 1500] if m else body[-3000:]
        # 视频峰会/通话: 正文写"在北京以视频方式会见", 地点判别会误报为在华到访
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
        # 老站标题无（日期）后缀且常带演讲从句, 人名需在修辞词处截断
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
    out.to_csv(f'{BF}/inbound_cn_backfill.csv', index=False)
    if len(out):
        yc = out['first'].str[:4].value_counts().sort_index()
        print(f'去重后访华 {len(out)} 次 -> {BF}/inbound_cn_backfill.csv')
        for y, c in yc.items(): print(f'  {y}: {c}')
    return out


CN_OFFICIALS = r'李源潮|张德江|刘延东|汪洋|王岐山|韩正|杨洁篪|王毅|栗战书|赵乐际|丁薛祥|王沪宁|胡春华|孙春兰|张高丽|国家副主席|全国人大|全国政协'
PAT_A = re.compile(r'^([一-龥]{2,15}?)(总统|总理|首相|国王|国家元首|埃米尔|苏丹|大公|亲王|委员长|内阁总理|联邦总理|主席)([一-龥·\-]{1,15}?)将')


def announce():
    """预告类文章 ("XX总统YY将访华/将出席...峰会"): 主抽取只认会见/会谈标题, 这批全漏.
    访问窗口取正文"将于X月X日至X日", 无窗口或无在华线索则弃 -> backfill/inbound_cn_announce.csv"""
    recs = []
    for fn in sorted(os.listdir(ART)):
        p = parse_article(fn[:-5], f'{ART}/{fn}')
        if not p: continue
        d, t, body = p
        if not re.search(r'将(对中华人民共和国|对中国|来华|访华|出席|访问中国|对我国)', t): continue
        if re.search(EXCL, t) or re.search(HOST, t) or re.search(CN_OFFICIALS, t): continue
        m = PAT_A.match(t)
        if not m: continue
        country, title, name = m.groups()
        i = body.find(t[:12])
        seg = body[i:i + 800] if i >= 0 else body[-2500:]
        if not re.search(r'来华|访华|对中国进行|对中华人民共和国进行|访问中国', seg): continue
        w = re.search(r'于(\d{1,2})月(\d{1,2})日(?:至(?:(\d{1,2})月)?(\d{1,2})日)?', seg)
        if not w: continue
        y, pm = int(d[:4]), int(d[5:7])
        m1 = int(w.group(1)); y1 = y + 1 if m1 < pm - 6 else y
        m2 = int(w.group(3)) if w.group(3) else m1
        d2 = int(w.group(4)) if w.group(4) else int(w.group(2))
        y2 = y1 + 1 if m2 < m1 else y1
        vm = re.search(r'(国事访问|正式访问|工作访问)', seg)
        vt = vm.group(1) if vm else ('来华出席' if '出席' in t else '会见/会谈(双边)')
        try:
            first = f'{y1}-{m1:02d}-{int(w.group(2)):02d}'; last = f'{y2}-{m2:02d}-{d2:02d}'
        except ValueError: continue
        recs.append({'country': country, 'leader_title': title, 'name': name,
                     'first': first, 'last': last, 'visit_type': vt, 'n_articles': 1})
    # 同一访问多次预告去重 (国家+名字前2字+月)
    seen, out = set(), []
    for r in sorted(recs, key=lambda x: x['first']):
        if r['first'] < '2013': continue  # 数据集口径 2013 起
        k = (r['country'], r['name'][:2], r['first'][:7])
        if k in seen: continue
        seen.add(k); out.append(r)
    df = pd.DataFrame(out)
    df.to_csv(f'{BF}/inbound_cn_announce.csv', index=False)
    print(f'announce: 预告记录 {len(df)} 条 -> {BF}/inbound_cn_announce.csv')
    if len(df):
        for y, c in df['first'].str[:4].value_counts().sort_index().items(): print(f'  {y}: {c}')
    return df


def summits():
    """峰会与会名单补充 (data/summit_attendees.csv, 行级标注出处):
    纯参会/双边通稿未被快照捕获的领导人。与 master 按 (国家前2字, 名字前2字, ±12天) 去重 —
    峰会周双边常跨月(如 FOCAC 前的 08-31 会见), 月度键会漏判。"""
    fn = 'data/summit_attendees.csv'
    master_fn = 'out/inbound_cn_master.csv'
    sa = pd.read_csv(fn)
    master = pd.read_csv(master_fn)
    md = [(r['country'][:2], str(r['name'])[:2], datetime.fromisoformat(str(r['first'])))
          for _, r in master.iterrows()]
    add = []
    for _, r in sa.iterrows():
        d = datetime.fromisoformat(r['first'])
        if any(c == r['country'][:2] and n == r['name'][:2] and abs((d - t).days) <= 12
               for c, n, t in md): continue
        add.append({'country': r['country'], 'leader_title': r['leader_title'], 'name': r['name'],
                    'first': r['first'], 'last': r['last'], 'visit_type': '来华出席',
                    'n_articles': 0, 'source': f"summit supplement ({r['summit']})"})
    out = pd.concat([master, pd.DataFrame(add)], ignore_index=True).sort_values('first')
    out.to_csv(master_fn, index=False)
    print(f'summits: 名单 {len(sa)} 行, 与 master 去重后新增 {len(add)} 条, 累计 {len(out)} 条')
    return out


def merge():
    """回填/预告并入 out/inbound_cn_master.csv (已有记录优先, country+名字前2字+月 去重)"""
    master_fn = 'out/inbound_cn_master.csv'
    master = pd.read_csv(master_fn) if os.path.exists(master_fn) else pd.DataFrame()
    srcs = [(f'{BF}/inbound_cn_backfill.csv', 'PRC MFA zyxw wayback backfill'),
            (f'{BF}/inbound_cn_announce.csv', 'PRC MFA zyxw wayback backfill (预告)')]
    for fn, tag in srcs:
        if not os.path.exists(fn): continue
        bf = pd.read_csv(fn)
        bf['source'] = tag
        if len(master):
            key = set(master['country'] + master['name'].str[:2] + master['first'].astype(str).str[:7])
            bf = bf[~(bf['country'] + bf['name'].str[:2] + bf['first'].str[:7]).isin(key)]
        master = pd.concat([master, bf], ignore_index=True).sort_values('first')
        print(f'merge: {os.path.basename(fn)} 新增 {len(bf)} 条')
    master.to_csv(master_fn, index=False)
    print(f'master 累计 {len(master)} 条')
    return master


if __name__ == '__main__':
    stage = sys.argv[1] if len(sys.argv) > 1 else 'all'
    years = None
    if '--years' in sys.argv:
        ys = sys.argv[sys.argv.index('--years') + 1]
        years = set(range(int(ys.split('-')[0]), int(ys.split('-')[-1]) + 1))
    if stage in ('inventory', 'all'): inventory()
    if stage in ('fetch', 'all'): fetch_all()
    if stage in ('extract', 'all'): extract(years)
    if stage in ('announce', 'all'): announce()
    if stage in ('merge', 'all'): merge()
    if stage in ('summits', 'all'): summits()
