# 国家领导人出访/到访数据库 - 月度更新管线

四个序列: 中美元首出访 (2013-) + 外国领导人访美/访华 (2013-)
基准: ASPI Thomas & Wei (2026), 编码规则对齐(每到访一国计一次; 剔除无外交活动的经停/基地访问)

## 运行
```bash
pip install lxml pandas
bash run_monthly.sh          # 每月跑一次 (crontab: 0 6 1 * * )
```

## 脚本
| 文件 | 功能 | 数据源 | 备注 |
|---|---|---|---|
| update_outbound.py | 中美元首出访 | 国务院历史办 travels 仓库 + 维基百科出访列表 | 官方为主, 维基补缺(2025+/官方漏项) |
| update_inbound_us.py | 访美 | 国务院历史办 visits 仓库 + 维基六大洲列表 | HOGS 头衔过滤 |
| update_inbound_cn.py | 访华 | 外交部 zyxw 通稿管线 | 标题筛选→正文抓取→地点判别→去重; 增量累积 |
| validate.py | 对账 | ASPI 基准(内置) | 每次更新后自动跑 |
| backfill_china_inbound.py | 访华历史回填 | Wayback 快照→现网正文 | 需环境可访问 web.archive.org |

## 已知事项
1. 访华 2013-2024 回填已完成 79% (645/819, 2026-07 v2 三通道: Wayback正文+预告文章+峰会名单, 详见 docs/backfill_report_202607.md)。重跑: python3 backfill_china_inbound.py all (约6h, 断点续传)。剩余缺口: 2013-15 早期快照稀疏、首届进博会名单待走专题官网方法链。
2. 峰会与会名单模块已落地 (data/summit_attendees.csv, 行级出处): 新增在华峰会时追加名单行, 跑 python3 backfill_china_inbound.py summits (±12天窗口去重, 幂等)。中国主场峰会名单信源优先级: 峰会专题官网档案(不滚动) > 欢迎宴会通稿(总数口径) > 峰会周双边稿批量提取 > 中文维基(须互证) > 央视抵京系列, 见报告"回填手册"节。
3. 访美 2025 维基分页更新滞后(覆盖约半), 补全需白宫日程/新闻源。
4. 新美国总统就任时: 在 update_outbound.py 的 OTH_FILES 与 WIKI_PAGES 中追加条目。
5. 全自动跑与人工校对版会有 ±2% 级别差异(维基页面变动、边界记录), 关键分析前建议抽查 flags 列。
