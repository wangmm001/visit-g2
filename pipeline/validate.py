# -*- coding: utf-8 -*-
"""对账: 与 ASPI 基准(Thomas & Wei 2026)逐年比较, 基准数据内置到2025年"""
import pandas as pd, sys

ASPI_OUT = {2013:(15,12),2014:(20,18),2015:(15,11),2016:(16,16),2017:(8,14),2018:(13,8),2019:(13,11),
            2020:(1,2),2021:(0,6),2022:(5,13),2023:(4,13),2024:(10,7),2025:(6,15)}   # (中国,美国) 出访
ASPI_IN  = {2013:(73,34),2014:(95,75),2015:(92,37),2016:(69,62),2017:(69,35),2018:(121,27),2019:(79,35),
            2020:(5,11),2021:(0,15),2022:(28,97),2023:(79,74),2024:(109,67),2025:(75,50)}  # 到访

def report():
    print('='*72)
    print('对账报告 vs ASPI 基准 (2026-05 发布, 覆盖 2013-2025)')
    print('='*72)
    try:
        ob = pd.read_csv('out/outbound_trips.csv')
        obc = ob[ob['aspi_comparable']]
        print('\n【出访】(ASPI口径: 剔除无外交活动的经停/基地访问)')
        print(f"{'年份':>5} {'中国':>5} {'基准':>5} {'差':>4} | {'美国':>5} {'基准':>5} {'差':>4}")
        for y,(ac,au) in ASPI_OUT.items():
            c = len(obc[(obc.country_leader=='China')&(obc.year==y)])
            u = len(obc[(obc.country_leader=='United States')&(obc.year==y)])
            print(f"{y:>5} {c:>5} {ac:>5} {c-ac:>+4} | {u:>5} {au:>5} {u-au:>+4}")
        tc, tu = sum(a for a,_ in ASPI_OUT.values()), sum(b for _,b in ASPI_OUT.values())
        mc = len(obc[obc.country_leader=='China']); mu = len(obc[obc.country_leader=='United States'])
        print(f"{'合计':>5} {mc:>5} {tc:>5} {mc-tc:>+4} | {mu:>5} {tu:>5} {mu-tu:>+4}")
    except FileNotFoundError: print('\n[skip] out/outbound_trips.csv 不存在')
    try:
        iu = pd.read_csv('out/inbound_us.csv')
        print('\n【访美】(HOGS口径)')
        for y,(_,au) in ASPI_IN.items():
            u = len(iu[iu.year==y])
            note = ' (当年不完整)' if y >= 2025 else ''
            print(f"{y:>5} {u:>5} {au:>5} {u-au:>+4}{note}")
    except FileNotFoundError: print('\n[skip] out/inbound_us.csv 不存在')
    try:
        ic = pd.read_csv('out/inbound_cn_master.csv')
        ic['year'] = ic['first'].str[:4].astype(int)
        print('\n【访华】(管线累积, 历史回填未完成年份仅供参考)')
        for y,(ac,_) in ASPI_IN.items():
            c = len(ic[ic.year==y])
            if c: print(f"{y:>5} {c:>5} {ac:>5} {c-ac:>+4}")
    except FileNotFoundError: print('\n[skip] out/inbound_cn_master.csv 不存在')

if __name__ == '__main__':
    report()
