# -*- coding: utf-8 -*-
"""访华回填·MFA 英文站(zxxx)通道 — 只补 2013-2015 缺口年
背景: 中文 zyxw 2013-15 Wayback 捕获稀疏, 英文站快照独立于中文站(mfa_eng/zxxx_662805 有
4,302 篇文章级快照, 2013-2017 捕获窗)。标题格式 "Xi Jinping Holds Talks with President X of Y",
国名走 EN->CN 映射后与 master 按 (国家, ±10天) 去重 — 不比人名(拉丁 vs 中文), 同国同周双元首
极罕见, 保守方向是少加不错加。人名保留英文原文, source 标注可辨。
阶段: inventory / fetch / extract / merge / all
"""
import os, re, sys, subprocess, time
import pandas as pd
from datetime import datetime
from common import UA
from backfill_china_inbound import curl

BF = 'backfill/mfaeng'
ART = f'{BF}/art'
os.makedirs(ART, exist_ok=True)
CDX = 'https://web.archive.org/cdx/search/cdx'
TARGETS = ['www.fmprc.gov.cn/mfa_eng/zxxx_662805/*', 'www.fmprc.gov.cn/eng/zxxx/*']

HOST_EN = r'^(?:Xi Jinping|Li Keqiang|Hu Jintao|Wen Jiabao)'
ACT_EN = r'(?:Holds? Talks with|Meets? with|Holds? (?:a )?Welcom\w* Ceremony)'
EXCL_EN = (r'Vice[ -]President|Vice[ -]Premier|Vice[ -]Chairman|Deputy|Foreign Minister|Former|'
           r'Crown Prince|Princess|Speaker|First Lady|Secretary[ -]General|Director[ -]General|'
           r'Managing Director|Special Envoy|Adviser|Advisor|Minister of|Governor|Parliament|'
           r'Video|Phone|Telephone|Madam|Chief Executive|WEF|World Economic Forum|Executive Chairman')
PAT_EN = re.compile(
    r'(President-elect|President|Prime Minister|Premier|King|Queen|Emir|Amir|Sultan|Grand Duke|'
    r'Chancellor|Chairman(?: of the Presidency)?|State Counsellor)\s+'
    r"([A-Z][A-Za-z'’\.\- ]{1,40}?)\s+of\s+(?:the\s+)?([A-Z][A-Za-z'’\.\- ()]{2,45})\s*$")
TI_CN = {'President': '总统', 'President-elect': '总统当选人', 'Prime Minister': '总理', 'Premier': '总理',
         'King': '国王', 'Queen': '女王', 'Emir': '埃米尔', 'Amir': '埃米尔', 'Sultan': '苏丹',
         'Grand Duke': '大公', 'Chancellor': '联邦总理', 'Chairman': '主席',
         'Chairman of the Presidency': '主席团轮值主席', 'State Counsellor': '国务资政'}
CTY_CN = {
 'Russia': '俄罗斯', 'the Russian Federation': '俄罗斯', 'France': '法国', 'Germany': '德国', 'the United Kingdom': '英国',
 'the UK': '英国', 'Britain': '英国', 'the United States': '美国', 'the USA': '美国', 'Italy': '意大利',
 'Spain': '西班牙', 'Portugal': '葡萄牙', 'Greece': '希腊', 'the Netherlands': '荷兰', 'Holland': '荷兰',
 'Belgium': '比利时', 'Luxembourg': '卢森堡', 'Switzerland': '瑞士', 'Austria': '奥地利', 'Sweden': '瑞典',
 'Norway': '挪威', 'Denmark': '丹麦', 'Finland': '芬兰', 'Iceland': '冰岛', 'Ireland': '爱尔兰',
 'Poland': '波兰', 'the Czech Republic': '捷克', 'Slovakia': '斯洛伐克', 'Hungary': '匈牙利',
 'Romania': '罗马尼亚', 'Bulgaria': '保加利亚', 'Serbia': '塞尔维亚', 'Croatia': '克罗地亚',
 'Slovenia': '斯洛文尼亚', 'Bosnia and Herzegovina': '波黑', 'Montenegro': '黑山', 'Albania': '阿尔巴尼亚',
 'Macedonia': '马其顿', 'North Macedonia': '北马其顿', 'Kosovo': '科索沃', 'Malta': '马耳他', 'Cyprus': '塞浦路斯',
 'Estonia': '爱沙尼亚', 'Latvia': '拉脱维亚', 'Lithuania': '立陶宛', 'Belarus': '白俄罗斯', 'Ukraine': '乌克兰',
 'Moldova': '摩尔多瓦', 'Georgia': '格鲁吉亚', 'Armenia': '亚美尼亚', 'Azerbaijan': '阿塞拜疆',
 'Kazakhstan': '哈萨克斯坦', 'Uzbekistan': '乌兹别克斯坦', 'Turkmenistan': '土库曼斯坦',
 'Kyrgyzstan': '吉尔吉斯斯坦', 'the Kyrgyz Republic': '吉尔吉斯斯坦', 'Tajikistan': '塔吉克斯坦',
 'Turkey': '土耳其', 'Japan': '日本', 'the Republic of Korea': '韩国', 'South Korea': '韩国', 'ROK': '韩国',
 'the DPRK': '朝鲜', 'Mongolia': '蒙古国', 'Vietnam': '越南', 'Viet Nam': '越南', 'Laos': '老挝',
 'the Lao PDR': '老挝', 'Cambodia': '柬埔寨', 'Thailand': '泰国', 'Myanmar': '缅甸', 'Malaysia': '马来西亚',
 'Singapore': '新加坡', 'Indonesia': '印度尼西亚', 'the Philippines': '菲律宾', 'Brunei': '文莱',
 'Brunei Darussalam': '文莱', 'East Timor': '东帝汶', 'Timor-Leste': '东帝汶', 'India': '印度',
 'Pakistan': '巴基斯坦', 'Bangladesh': '孟加拉国', 'Sri Lanka': '斯里兰卡', 'Nepal': '尼泊尔',
 'Bhutan': '不丹', 'the Maldives': '马尔代夫', 'Maldives': '马尔代夫', 'Afghanistan': '阿富汗',
 'Iran': '伊朗', 'Iraq': '伊拉克', 'Syria': '叙利亚', 'Lebanon': '黎巴嫩', 'Jordan': '约旦',
 'Israel': '以色列', 'Palestine': '巴勒斯坦', 'Saudi Arabia': '沙特阿拉伯', 'the UAE': '阿联酋',
 'the United Arab Emirates': '阿联酋', 'Qatar': '卡塔尔', 'Kuwait': '科威特', 'Bahrain': '巴林',
 'Oman': '阿曼', 'Yemen': '也门', 'Egypt': '埃及', 'Libya': '利比亚', 'Tunisia': '突尼斯',
 'Algeria': '阿尔及利亚', 'Morocco': '摩洛哥', 'Sudan': '苏丹', 'South Sudan': '南苏丹',
 'Ethiopia': '埃塞俄比亚', 'Kenya': '肯尼亚', 'Tanzania': '坦桑尼亚', 'Uganda': '乌干达',
 'Rwanda': '卢旺达', 'Burundi': '布隆迪', 'Somalia': '索马里', 'Djibouti': '吉布提', 'Eritrea': '厄立特里亚',
 'Nigeria': '尼日利亚', 'Ghana': '加纳', 'Senegal': '塞内加尔', 'Mali': '马里', 'Niger': '尼日尔',
 'Chad': '乍得', 'Cameroon': '喀麦隆', 'Gabon': '加蓬', 'the Republic of Congo': '刚果共和国',
 'Congo': '刚果共和国', 'the Democratic Republic of the Congo': '刚果民主共和国', 'the DRC': '刚果民主共和国',
 'Angola': '安哥拉', 'Zambia': '赞比亚', 'Zimbabwe': '津巴布韦', 'Mozambique': '莫桑比克',
 'Malawi': '马拉维', 'Madagascar': '马达加斯加', 'Mauritius': '毛里求斯', 'the Seychelles': '塞舌尔',
 'Seychelles': '塞舌尔', 'the Comoros': '科摩罗', 'Namibia': '纳米比亚', 'Botswana': '博茨瓦纳',
 'South Africa': '南非', 'Lesotho': '莱索托', 'Swaziland': '斯威士兰', 'Benin': '贝宁', 'Togo': '多哥',
 "Cote d'Ivoire": '科特迪瓦', 'Ivory Coast': '科特迪瓦', 'Burkina Faso': '布基纳法索', 'Guinea': '几内亚',
 'Guinea-Bissau': '几内亚比绍', 'Equatorial Guinea': '赤道几内亚', 'Sierra Leone': '塞拉利昂',
 'Liberia': '利比里亚', 'the Gambia': '冈比亚', 'Gambia': '冈比亚', 'Mauritania': '毛里塔尼亚',
 'Cape Verde': '佛得角', 'Cabo Verde': '佛得角', 'Sao Tome and Principe': '圣多美和普林西比',
 'the Central African Republic': '中非共和国', 'Canada': '加拿大', 'Mexico': '墨西哥', 'Cuba': '古巴',
 'Jamaica': '牙买加', 'Haiti': '海地', 'the Dominican Republic': '多米尼加', 'Dominica': '多米尼克',
 'the Bahamas': '巴哈马', 'Barbados': '巴巴多斯', 'Trinidad and Tobago': '特立尼达和多巴哥',
 'Grenada': '格林纳达', 'Antigua and Barbuda': '安提瓜和巴布达', 'Guatemala': '危地马拉',
 'Honduras': '洪都拉斯', 'El Salvador': '萨尔瓦多', 'Nicaragua': '尼加拉瓜', 'Costa Rica': '哥斯达黎加',
 'Panama': '巴拿马', 'Colombia': '哥伦比亚', 'Venezuela': '委内瑞拉', 'Ecuador': '厄瓜多尔',
 'Peru': '秘鲁', 'Brazil': '巴西', 'Bolivia': '玻利维亚', 'Paraguay': '巴拉圭', 'Uruguay': '乌拉圭',
 'Chile': '智利', 'Argentina': '阿根廷', 'Guyana': '圭亚那', 'Suriname': '苏里南',
 'Australia': '澳大利亚', 'New Zealand': '新西兰', 'Papua New Guinea': '巴布亚新几内亚',
 'Fiji': '斐济', 'Samoa': '萨摩亚', 'Tonga': '汤加', 'Vanuatu': '瓦努阿图', 'Micronesia': '密克罗尼西亚联邦',
 'the Federated States of Micronesia': '密克罗尼西亚联邦', 'Serbia and Montenegro': '塞尔维亚',
 'the Solomon Islands': '所罗门群岛', 'Kiribati': '基里巴斯', 'the Cook Islands': '库克群岛',
 'US': '美国', 'the US': '美国', 'Republic of Korea (ROK)': '韩国', 'the ROK': '韩国',
 'Democratic Republic of Congo': '刚果民主共和国'}
# 风格2: 形容词国名前置 "Zimbabwean President Mugabe" / "Kazakhstan President Nazarbayev"
PAT_EN2 = re.compile(
    r"(?:Holds? Talks with|Meets? with)\s+(?:the\s+)?([A-Z][A-Za-z'’\- ]+?)\s+"
    r'(President-elect|President|Prime Minister|Premier|King|Queen|Emir|Amir|Sultan|Grand Duke|'
    r"Chancellor|State Counsellor)\s+([A-Z][A-Za-z'’\.\- ]{1,40})\s*$")
DEMONYM_CN = {
 'Russian': '俄罗斯', 'French': '法国', 'German': '德国', 'British': '英国', 'Italian': '意大利',
 'Spanish': '西班牙', 'Portuguese': '葡萄牙', 'Greek': '希腊', 'Dutch': '荷兰', 'Belgian': '比利时',
 'Swiss': '瑞士', 'Austrian': '奥地利', 'Swedish': '瑞典', 'Norwegian': '挪威', 'Danish': '丹麦',
 'Finnish': '芬兰', 'Icelandic': '冰岛', 'Irish': '爱尔兰', 'Polish': '波兰', 'Czech': '捷克',
 'Slovak': '斯洛伐克', 'Hungarian': '匈牙利', 'Romanian': '罗马尼亚', 'Bulgarian': '保加利亚',
 'Serbian': '塞尔维亚', 'Croatian': '克罗地亚', 'Slovenian': '斯洛文尼亚', 'Montenegrin': '黑山',
 'Albanian': '阿尔巴尼亚', 'Macedonian': '马其顿', 'Maltese': '马耳他', 'Cypriot': '塞浦路斯',
 'Estonian': '爱沙尼亚', 'Latvian': '拉脱维亚', 'Lithuanian': '立陶宛', 'Belarusian': '白俄罗斯',
 'Ukrainian': '乌克兰', 'Moldovan': '摩尔多瓦', 'Georgian': '格鲁吉亚', 'Armenian': '亚美尼亚',
 'Azerbaijani': '阿塞拜疆', 'Kazakh': '哈萨克斯坦', 'Kazakhstani': '哈萨克斯坦', 'Uzbek': '乌兹别克斯坦',
 'Turkmen': '土库曼斯坦', 'Kyrgyz': '吉尔吉斯斯坦', 'Tajik': '塔吉克斯坦', 'Turkish': '土耳其',
 'Japanese': '日本', 'Mongolian': '蒙古国', 'Vietnamese': '越南', 'Lao': '老挝', 'Laotian': '老挝',
 'Cambodian': '柬埔寨', 'Thai': '泰国', 'Malaysian': '马来西亚', 'Singaporean': '新加坡',
 'Singapore': '新加坡', 'Indonesian': '印度尼西亚', 'Philippine': '菲律宾', 'Bruneian': '文莱',
 'Indian': '印度', 'Pakistani': '巴基斯坦', 'Bangladeshi': '孟加拉国', 'Sri Lankan': '斯里兰卡',
 'Nepali': '尼泊尔', 'Nepalese': '尼泊尔', 'Maldivian': '马尔代夫', 'Afghan': '阿富汗',
 'Iranian': '伊朗', 'Iraqi': '伊拉克', 'Syrian': '叙利亚', 'Lebanese': '黎巴嫩', 'Jordanian': '约旦',
 'Israeli': '以色列', 'Palestinian': '巴勒斯坦', 'Saudi': '沙特阿拉伯', 'Saudi Arabian': '沙特阿拉伯',
 'Qatari': '卡塔尔', 'Kuwaiti': '科威特', 'Bahraini': '巴林', 'Omani': '阿曼', 'Yemeni': '也门',
 'Egyptian': '埃及', 'Libyan': '利比亚', 'Tunisian': '突尼斯', 'Algerian': '阿尔及利亚',
 'Moroccan': '摩洛哥', 'Sudanese': '苏丹', 'South Sudanese': '南苏丹', 'Ethiopian': '埃塞俄比亚',
 'Kenyan': '肯尼亚', 'Tanzanian': '坦桑尼亚', 'Ugandan': '乌干达', 'Rwandan': '卢旺达',
 'Burundian': '布隆迪', 'Somali': '索马里', 'Djiboutian': '吉布提', 'Eritrean': '厄立特里亚',
 'Nigerian': '尼日利亚', 'Ghanaian': '加纳', 'Senegalese': '塞内加尔', 'Malian': '马里',
 'Nigerien': '尼日尔', 'Chadian': '乍得', 'Cameroonian': '喀麦隆', 'Gabonese': '加蓬',
 'Angolan': '安哥拉', 'Zambian': '赞比亚', 'Zimbabwean': '津巴布韦', 'Mozambican': '莫桑比克',
 'Malawian': '马拉维', 'Malagasy': '马达加斯加', 'Mauritian': '毛里求斯', 'Namibian': '纳米比亚',
 'South African': '南非', 'Beninese': '贝宁', 'Togolese': '多哥', 'Ivorian': '科特迪瓦',
 'Guinean': '几内亚', 'Sierra Leonean': '塞拉利昂', 'Liberian': '利比里亚', 'Gambian': '冈比亚',
 'Mauritanian': '毛里塔尼亚', 'Central African': '中非共和国', 'Canadian': '加拿大',
 'Mexican': '墨西哥', 'Cuban': '古巴', 'Jamaican': '牙买加', 'Haitian': '海地', 'Bahamian': '巴哈马',
 'Barbadian': '巴巴多斯', 'Grenadian': '格林纳达', 'Guatemalan': '危地马拉', 'Honduran': '洪都拉斯',
 'Salvadoran': '萨尔瓦多', 'Nicaraguan': '尼加拉瓜', 'Costa Rican': '哥斯达黎加',
 'Panamanian': '巴拿马', 'Colombian': '哥伦比亚', 'Venezuelan': '委内瑞拉', 'Ecuadorian': '厄瓜多尔',
 'Ecuadorean': '厄瓜多尔', 'Peruvian': '秘鲁', 'Brazilian': '巴西', 'Bolivian': '玻利维亚',
 'Paraguayan': '巴拉圭', 'Uruguayan': '乌拉圭', 'Chilean': '智利', 'Argentine': '阿根廷',
 'Argentinian': '阿根廷', 'Guyanese': '圭亚那', 'Surinamese': '苏里南', 'Australian': '澳大利亚',
 'New Zealand': '新西兰', 'Papua New Guinean': '巴布亚新几内亚', 'Fijian': '斐济', 'Samoan': '萨摩亚',
 'Tongan': '汤加', 'Vanuatuan': '瓦努阿图', 'Micronesian': '密克罗尼西亚联邦', 'Myanmar': '缅甸'}
ADJ_CN = dict(DEMONYM_CN)
ADJ_CN.update({k[4:] if k.startswith('the ') else k: v for k, v in CTY_CN.items()})
IN_CN_EN = re.compile(r'in Beijing|at the Great Hall of the People|Zhongnanhai|Diaoyutai|'
                      r'(?:state|official|working) visit to China|visit(?:ing)? China|arriv\w+ in (?:Beijing|China)|'
                      r'in (?:Shanghai|Hangzhou|Boao|Sanya|Tianjin|Xi\'an|Chengdu|Qingdao)', re.I)
NOT_CN_EN = re.compile(r'local time|via video|video link|by telephone|over the phone', re.I)


def art_key(url):
    m = re.search(r'/(t\d+)\.shtml', url)
    return m.group(1) if m else None


def inventory():
    rows = {}
    for tg in TARGETS:
        slug = re.sub(r'[^a-z0-9]+', '_', tg)
        for y in range(2013, 2019):  # 英文站捕获集中 2013-2018; 2013-15 文章后期也可能被再捕
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
    print(f'inventory: {len(rows)} 篇唯一文章 -> {BF}/inventory.tsv')
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


def fetch_all(max_n=None, workers=3):
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
            if n % 200 == 0: print(f'  {n}/{len(todo)} ok={ok} fail={fail}', flush=True)
    print(f'fetch 完成: ok={ok} fail={fail}')


def parse_article(path):
    try: txt = open(path, encoding='utf-8', errors='ignore').read()
    except OSError: return None
    tm = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', txt) or re.search(r'<title>([^<]*)</title>', txt)
    if not tm: return None
    title = re.sub(r'<[^>]+>', '', tm.group(1)).strip()
    title = re.sub(r'\s*[_—-]*\s*(Ministry of Foreign Affairs|MFA).*$', '', title).strip()
    if not title: return None
    body = ' '.join(re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>', ' ', txt).split())
    m = re.search(r'(20\d\d)[/\-](\d{1,2})[/\-](\d{1,2})', body)
    d = f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}' if m else None
    return d, title, body


def extract(y_lo='2013', y_hi='2015'):
    recs, unmapped = [], {}
    n_all = n_cand = 0
    for fn in sorted(os.listdir(ART)):
        p = parse_article(f'{ART}/{fn}')
        if not p: continue
        d, t, body = p
        if not d: continue
        n_all += 1
        if not (y_lo <= d[:4] <= y_hi): continue
        if not (re.search(HOST_EN, t) and re.search(ACT_EN, t)) or re.search(EXCL_EN, t): continue
        m = PAT_EN.search(t)
        if m:
            ti, name, cty = m.groups()
        else:
            m2 = PAT_EN2.search(t)
            if not m2: continue
            cty, ti, name = m2.groups()
        n_cand += 1
        # 定位正文起点: 英文页开头是导航/多语种噪声, 事件句以 "On <Month> <Day>" 起
        sm = re.search(r'On (?:January|February|March|April|May|June|July|August|September|October|'
                       r'November|December) \d{1,2}', body)
        seg = body[sm.start():sm.start() + 2500] if sm else body[:2500]
        # 排除境外场合(local time/视频/电话), 除非明说 visit to China
        if NOT_CN_EN.search(seg[:400]) and not re.search(r'visit to China', seg[:400], re.I): continue
        if not IN_CN_EN.search(seg[:700]): continue
        cty = cty.strip()
        cn = CTY_CN.get(cty) or CTY_CN.get('the ' + cty) or ADJ_CN.get(cty)
        if not cn:
            unmapped[cty] = unmapped.get(cty, 0) + 1; continue
        vm = re.search(r'(state visit|official visit|working visit)', seg, re.I)
        vt = {'state visit': '国事访问', 'official visit': '正式访问', 'working visit': '工作访问'}.get(
            vm.group(1).lower() if vm else '', '会见/会谈(双边)')
        recs.append({'date': d, 'country': cn, 'leader_title': TI_CN.get(ti, ti), 'name': name, 'visit_type': vt})
    print(f'解析 {n_all} 篇, 标题命中 {n_cand}, 判定在华 {len(recs)}')
    if unmapped: print('  未映射国名:', dict(sorted(unmapped.items(), key=lambda x: -x[1])[:15]))
    visits = {}
    for r in sorted(recs, key=lambda x: x['date']):
        d = datetime.fromisoformat(r['date']); merged = False
        for v in visits.values():
            if v['country'] == r['country'] and abs((d - datetime.fromisoformat(v['first'])).days) <= 10:
                v['last'] = max(v['last'], r['date']); v['n_articles'] += 1
                if r['visit_type'] != '会见/会谈(双边)' and v['visit_type'] == '会见/会谈(双边)':
                    v['visit_type'] = r['visit_type']
                merged = True; break
        if not merged:
            visits[(r['country'], r['date'])] = {'country': r['country'], 'leader_title': r['leader_title'],
                'name': r['name'], 'first': r['date'], 'last': r['date'],
                'visit_type': r['visit_type'], 'n_articles': 1}
    out = pd.DataFrame(sorted(visits.values(), key=lambda v: v['first']))
    out.to_csv(f'{BF}/inbound_cn_mfaeng.csv', index=False)
    if len(out):
        print(f'去重后访华 {len(out)} 次 -> {BF}/inbound_cn_mfaeng.csv')
        for y, c in out['first'].str[:4].value_counts().sort_index().items(): print(f'  {y}: {c}')
    return out


def merge():
    """与 master 按 (国家, ±10天) 去重 — 英文人名无法比中文名, 用国家+时间窗。"""
    master_fn = 'out/inbound_cn_master.csv'
    master = pd.read_csv(master_fn)
    bf = pd.read_csv(f'{BF}/inbound_cn_mfaeng.csv')
    bf['source'] = 'PRC MFA /eng/ wayback backfill'
    md = [(r['country'], datetime.fromisoformat(str(r['first']))) for _, r in master.iterrows()]
    keep = []
    for _, r in bf.iterrows():
        d = datetime.fromisoformat(r['first'])
        if any(c == r['country'] and abs((d - t).days) <= 10 for c, t in md): continue
        keep.append(r)
    add = pd.DataFrame(keep)
    master = pd.concat([master, add], ignore_index=True).sort_values('first')
    master.to_csv(master_fn, index=False)
    print(f'merge: 新增 {len(add)} 条, master 累计 {len(master)} 条')
    if len(add):
        for y, c in add['first'].str[:4].value_counts().sort_index().items(): print(f'  {y}: +{c}')
    return master


if __name__ == '__main__':
    stage = sys.argv[1] if len(sys.argv) > 1 else 'all'
    max_n = None
    if '--max' in sys.argv: max_n = int(sys.argv[sys.argv.index('--max') + 1])
    if stage in ('inventory', 'all'): inventory()
    if stage in ('fetch', 'all'): fetch_all(max_n)
    if stage in ('extract', 'all'): extract()
    if stage in ('merge', 'all'): merge()
