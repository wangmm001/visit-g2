# 国家领导人出访/到访数据库 - 月度更新管线

四个序列: 中美元首出访 (2013-) + 外国领导人访美/访华 (2013-)
基准: ASPI Thomas & Wei (2026), 编码规则对齐(每到访一国计一次; 剔除无外交活动的经停/基地访问)

## 运行
```bash
pip install -r requirements.txt
bash run_monthly.sh          # 每月跑一次 (crontab: 0 6 1 * * )
```
已接入 GitHub Actions 每日数据流 (.github/workflows/daily-update.yml):
每日 23:45 UTC 自动跑全管线 (2026-07 起并入 global-pulse 每日数据流), 数据有变更则由 github-actions[bot] 直接 commit 回 master,
validate 报告存 out/validation_YYYYMM.txt 并上传为 run artifact (留 90 天)。手动触发: gh workflow run daily-update。

## 脚本
| 文件 | 功能 | 数据源 | 备注 |
|---|---|---|---|
| update_outbound.py | 中美元首出访 | 国务院历史办 travels 仓库 + 维基百科出访列表 | 官方为主, 维基补缺(2025+/官方漏项) |
| update_inbound_us.py | 访美 | 国务院历史办 visits 仓库 + 维基六大洲列表 | HOGS 头衔过滤 |
| update_inbound_cn.py | 访华 | 外交部 zyxw 通稿管线 | 标题筛选→正文抓取→地点判别→去重; 增量累积 |
| validate.py | 对账 | ASPI 基准(内置) | 每次更新后自动跑 |
| backfill_china_inbound.py | 访华历史回填(主) | 外交部 zyxw Wayback 快照 | 需环境可访问 web.archive.org |
| backfill_govcn_ldhd.py | 访华回填·gov.cn 领导活动 | gov.cn/ldhd 2013-14 Wayback | 2013 缺口主力 (+23) |
| backfill_mfa_eng.py | 访华回填·MFA 英文站 | /eng/ Wayback (独立快照池) | EN→CN 映射, 只补 2013-15 |
| backfill_rmrb.py | 访华回填·人民日报 | 版面页 Wayback (2013 全年) | 版面目录=标题索引 |

## 已知事项
1. 访华 2013-2024 回填已完成 83% (682/819, 2026-07 六通道: zyxw正文+预告+峰会名单+gov.cn ldhd+MFA英文站+人民日报, 详见 docs/backfill_report_202607.md; 含 HOGS 口径净化与跨语言去重)。重跑: 各 backfill_*.py all (断点续传)。剩余缺口: 2013(-25)已三通道榨干, 2014/15(-15/-15)残余出路是 gov.cn/xinwen 全年抓取(~12h, 低密度)。
2. 峰会与会名单模块已落地 (data/summit_attendees.csv, 行级出处): 新增在华峰会时追加名单行, 跑 python3 backfill_china_inbound.py summits (±12天窗口去重, 幂等)。中国主场峰会名单信源优先级: 峰会专题官网档案(不滚动) > 欢迎宴会通稿(总数口径) > 峰会周双边稿批量提取 > 中文维基(须互证) > 央视抵京系列, 见报告"回填手册"节。
3. 访美 2025 维基分页更新滞后(覆盖约半), 补全需白宫日程/新闻源。
4. 新美国总统就任时: 在 update_outbound.py 的 OTH_FILES 与 WIKI_PAGES 中追加条目。
5. 全自动跑与人工校对版会有 ±2% 级别差异(维基页面变动、边界记录), 关键分析前建议抽查 flags 列。
