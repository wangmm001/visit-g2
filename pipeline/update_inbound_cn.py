# -*- coding: utf-8 -*-
"""月度更新 - 访华方向 (管线 v0)
数据源: 外交部"重要新闻" (mfa.gov.cn/web/zyxw, 滚动窗口约15个月)
流程: 翻页收标题 -> 标题筛候选 -> 抓正文判地点 -> 领导人+时间窗去重
输出: out/inbound_cn.csv (增量并入历史累积文件 out/inbound_cn_master.csv)"""
import re, os, json, subprocess, time, sys
import pandas as pd
from lxml import html as LH
from datetime import datetime, timedelta
from common import UA, fetch

OUT='out'; os.makedirs(OUT, exist_ok=True); os.makedirs(f'{OUT}/mfa_art', exist_ok=True)
HOST=r'(习近平|李强)'; ACT=r'(会见|会谈|举行欢迎仪式|共同会见记者)'
FTITLE=r'(总统|总理|首相|国王|国家元首|埃米尔|苏丹|大公|亲王|委员长|临时总统|总统当选人|内阁总理|联邦总理|国家主席|联邦主席|主席)'
EXCL=r'外长|外交大臣|副总理|副总统|王储|国家杜马|国际奥委会|议长|前总统|前总理|夫人|特使|特别代表|国会主席|大呼拉尔|参议院|众议院|国民议会|人民院|联邦院|基金会|副首相|第一副主席|副主席|世界经济论坛|国际商会|非盟|联邦委员会|国际篮联|红十字|非洲联盟|国民党|参谋长联席会议|国家安全事务助理|祖国阵线|桑给巴尔|友协'
CN_PLACES=['北京','人民大会堂','钓鱼台','中南海','天津','上海','杭州','成都','广州','深圳','西安','哈尔滨','三亚','博鳌','厦门','青岛','郑州','南京','武汉','重庆']
PAT1 = re.compile(r'(?:会见|同)([\u4e00-\u9fa5]{2,12}?)(总统|总理|国王|首相|国家元首|埃米尔|苏丹|大公|亲王|委员长|临时总统|总统当选人|内阁总理|联邦总理|国家主席|联邦主席|主席)([\u4e00-\u9fa5·]{1,15})')
PAT2 = re.compile(r'(?:会见|同)([\u4e00-\u9fa5]{2,5})[\u4e00-\u9fa5、党中央委员会总书记第一记劳动]{0,28}(?:国家主席|国务委员长|国家元首)([\u4e00-\u9fa5·\-]{1,12})')

def harvest_titles(since):
    """翻页收集要闻标题, 直到 since 日期"""
    items, seen, i = [], set(), 0
    while i < 120:
        url = 'https://www.mfa.gov.cn/web/zyxw/' if i==0 else f'https://www.mfa.gov.cn/web/zyxw/index_{i}.shtml'
        fn = f'{OUT}/mfa_list_{i}.html'
        if not fetch(url, fn): break
        try: doc = LH.parse(fn)
        except: break
        new = []
        for a in doc.xpath('//a[@href]'):
            h = a.get('href') or ''
            m = re.search(r'（(20\d\d-\d\d-\d\d)）', a.text_content() or '')
            if 't20' in h and m and h not in seen:
                new.append((m.group(1), a.text_content().strip(), h)); seen.add(h)
        if not new: break
        items += new; i += 1
        if min(d for d,_,_ in new) < since: break
        time.sleep(0.3)
    return items

def extract_visits(items, since):
    cands = [(d,t,h) for d,t,h in items if d >= since
             and re.search(HOST,t) and re.search(ACT,t) and re.search(FTITLE,t) and not re.search(EXCL,t)]
    print(f'候选文章: {len(cands)}')
    recs=[]
    for idx,(d,t,h) in enumerate(cands):
        fn = f'{OUT}/mfa_art/{re.sub(r"[^a-z0-9]","_",h)}.html'
        if not os.path.exists(fn):
            fetch('https://www.mfa.gov.cn/web/zyxw/'+h.lstrip('./'), fn); time.sleep(0.15)
        try: txt = open(fn, encoding='utf-8', errors='ignore').read()
        except: continue
        body = ' '.join(re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>',' ',txt).split())
        m = re.search(r'\d{1,2}月\d{1,2}日[^，。]{0,10}，', body)
        seg = body[m.start():m.start()+1500] if m else body[-3000:]
        lm = re.search(r'在([^，。]{1,20}?)(?:会见|同|与|为|举行|出席|亲切)', seg[:250])
        loc = lm.group(1) if lm else ''
        in_cn = any(p in loc for p in CN_PLACES) if loc else bool(re.search(r'来华|访华|欢迎.{0,20}访问|抵达北京', seg[:250]))
        if not in_cn: continue
        vm = re.search(r'(国事访问|正式访问|工作访问|来华出席)', seg)
        recs.append({'date':d,'title':re.sub(r'（20.*$','',t),'visit_type':vm.group(1) if vm else ''})
    # 去重
    visits={}
    for r in sorted(recs, key=lambda x:x['date']):
        m = PAT1.search(r['title'])
        if m: country, title, name = m.groups()
        else:
            m2 = PAT2.search(r['title'])
            if not m2: continue
            country, name = m2.groups(); title='国家主席/总书记'
        # 尾巴修辞可能层叠(如"举行会谈"), 用 .* 一次削到底, 单词交替+$ 只会削掉最后一节
        name = re.sub(r'(会谈.*|举行.*|共同.*|并.*|夫妇.*|和太后.*)$','',name).strip()
        d = datetime.fromisoformat(r['date']); merged=False
        for v in visits.values():
            if v['country']==country and (v['name'][:3]==name[:3] or name in v['name'] or v['name'] in name) \
               and abs((d-datetime.fromisoformat(v['first'])).days) <= 10:
                v['last']=max(v['last'],r['date']); v['n_articles']+=1
                if r['visit_type'] and v['visit_type'] in ('','来华出席'): v['visit_type']=r['visit_type']
                merged=True; break
        if not merged:
            visits[(country,name,r['date'])] = {'country':country,'leader_title':title,'name':name,
                'first':r['date'],'last':r['date'],'visit_type':r['visit_type'] or '会见/会谈(双边)','n_articles':1}
    return sorted(visits.values(), key=lambda v:v['first'])

def main(since=None):
    master_fn = f'{OUT}/inbound_cn_master.csv'
    master = pd.read_csv(master_fn) if os.path.exists(master_fn) else pd.DataFrame()
    if since is None:
        since = (max(master['first']) if len(master) else
                 (datetime.now()-timedelta(days=430)).strftime('%Y-%m-%d'))
    print(f'抓取窗口: {since} 之后')
    items = harvest_titles(since)
    print(f'要闻条目: {len(items)}')
    vs = extract_visits(items, since)
    new = pd.DataFrame(vs)
    if len(master) and len(new):
        key = master['country']+master['name']+master['first'].astype(str).str[:7]
        new = new[~(new['country']+new['name']+new['first'].str[:7]).isin(set(key))]
    out = pd.concat([master,new],ignore_index=True).sort_values('first') if len(master) else new
    out['source']='PRC MFA zyxw pipeline'
    out.to_csv(master_fn, index=False)
    print(f'=> 新增 {len(new)} 条, 累计 {len(out)} 条 ({master_fn})')
    return out

if __name__ == '__main__':
    import sys
    main(sys.argv[1] if len(sys.argv)>1 else None)
