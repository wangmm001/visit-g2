#!/bin/bash
# 月度更新入口: 每月1日运行 (crontab: 0 6 1 * * bash run_monthly.sh)
set -e
cd "$(dirname "$0")"
echo "=== 领导人出访数据库月度更新 $(date +%F) ==="
python3 update_outbound.py
python3 update_inbound_us.py
python3 update_inbound_cn.py
python3 validate.py | tee out/validation_$(date +%Y%m).txt
cp out/inbound_cn_master.csv ../inbound_cn_master.csv   # 根目录副本与 out/ 保持同步
echo "=== 完成, 产出在 out/ ==="
