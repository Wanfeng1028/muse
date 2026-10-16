#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
用法: check-alerts.sh [--dir 日志目录] [--hours N]

选项:
  --dir DIR     指标日志目录（默认: ${VOXLOOM_LOG_DIR:-./appdir/logs}）
  --hours N     回溯窗口小时数（默认: 24）
  --help        显示帮助并退出

退出码:
  0  无告警
  1  仅 WARN 级别告警
  2  存在 CRIT 级别告警

规则:
  1. transcript.import 转写失败率（样本>=5）: >=0.30 CRIT, >=0.10 WARN
  2. edit.apply 剪辑冲突率（EditConflictException，样本>=10）: >=0.15 CRIT, >=0.05 WARN
  3. 磁盘空间: <1GiB CRIT, <5GiB WARN
  4. backup.create/backup.restore 失败次数: >=3 CRIT, >=1 WARN
EOF
}

DIR="${VOXLOOM_LOG_DIR:-./appdir/logs}"
HOURS=24

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --dir)
      if [[ $# -lt 2 ]]; then
        echo "错误: --dir 需要一个参数" >&2
        usage >&2
        exit 2
      fi
      DIR="$2"
      shift 2
      ;;
    --hours)
      if [[ $# -lt 2 ]]; then
        echo "错误: --hours 需要一个参数" >&2
        usage >&2
        exit 2
      fi
      HOURS="$2"
      shift 2
      ;;
    *)
      echo "错误: 未知参数 '$1'" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! [[ "$HOURS" =~ ^[0-9]+$ ]] || [[ "$HOURS" -eq 0 ]]; then
  echo "错误: --hours 必须是正整数" >&2
  usage >&2
  exit 2
fi

if [[ ! -d "$DIR" ]]; then
  echo "OK: 指标目录不存在（$DIR），跳过扫描"
  exit 0
fi

# 收集所有 metrics-*.jsonl 文件
shopt -s nullglob
FILES=("$DIR"/metrics-*.jsonl)
shopt -u nullglob

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "OK: 无告警（扫描 0 行，窗口 $HOURS 小时）"
  exit 0
fi

# 通过 python3 解析并统计
PY_OUT=$(python3 - "$HOURS" "${FILES[@]}" <<'PYEOF'
import sys, json, datetime

hours = int(sys.argv[1])
files = sys.argv[2:]

now = datetime.datetime.now(datetime.timezone.utc)
cutoff = now - datetime.timedelta(hours=hours)

total_lines = 0
valid_lines = 0

# 规则1: transcript.import
ti_total = 0
ti_fail = 0

# 规则2: edit.apply
ea_total = 0
ea_conflict = 0

# 规则4: backup
bk_fail = 0

def parse_ts(s):
    if not isinstance(s, str):
        return None
    try:
        # 支持 'Z' 结尾
        t = s.replace('Z', '+00:00')
        dt = datetime.datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        return None

for path in files:
    try:
        f = open(path, 'r', encoding='utf-8', errors='replace')
    except Exception:
        continue
    with f:
        for line in f:
            total_lines += 1
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            ts = parse_ts(obj.get('ts'))
            if ts is None:
                continue
            if ts < cutoff or ts > now:
                continue
            valid_lines += 1

            op = obj.get('op')
            success = obj.get('success')
            error_type = obj.get('error_type')

            if op == 'transcript.import':
                ti_total += 1
                if success is False:
                    ti_fail += 1
            elif op == 'edit.apply':
                ea_total += 1
                if error_type == 'EditConflictException':
                    ea_conflict += 1
            elif op in ('backup.create', 'backup.restore'):
                if success is False:
                    bk_fail += 1

alerts = []
crit = False
warn = False

# 规则1
if ti_total >= 5:
    rate = ti_fail / ti_total
    if rate >= 0.30:
        crit = True
        alerts.append("ALERT [CRIT] transcript_failure_rate: 失败率 %.2f (失败 %d / 样本 %d)" % (rate, ti_fail, ti_total))
    elif rate >= 0.10:
        warn = True
        alerts.append("ALERT [WARN] transcript_failure_rate: 失败率 %.2f (失败 %d / 样本 %d)" % (rate, ti_fail, ti_total))

# 规则2
if ea_total >= 10:
    rate = ea_conflict / ea_total
    if rate >= 0.15:
        crit = True
        alerts.append("ALERT [CRIT] edit_conflict_rate: 冲突率 %.2f (冲突 %d / 样本 %d)" % (rate, ea_conflict, ea_total))
    elif rate >= 0.05:
        warn = True
        alerts.append("ALERT [WARN] edit_conflict_rate: 冲突率 %.2f (冲突 %d / 样本 %d)" % (rate, ea_conflict, ea_total))

# 规则4
if bk_fail >= 3:
    crit = True
    alerts.append("ALERT [CRIT] backup_failure: 备份失败 %d 次" % bk_fail)
elif bk_fail >= 1:
    warn = True
    alerts.append("ALERT [WARN] backup_failure: 备份失败 %d 次" % bk_fail)

print("__STATS__ %d %d" % (total_lines, valid_lines))
for a in alerts:
    print(a)
if crit:
    print("__EXIT__ 2")
elif warn:
    print("__EXIT__ 1")
else:
    print("__EXIT__ 0")
PYEOF
)

# 解析 python 输出
STATS_LINE=""
EXIT_CODE=""
ALERTS=()
while IFS= read -r line; do
  case "$line" in
    __STATS__*)
      STATS_LINE="$line"
      ;;
    __EXIT__*)
      EXIT_CODE="${line#__EXIT__ }"
      ;;
    ALERT*)
      ALERTS+=("$line")
      ;;
  esac
done <<< "$PY_OUT"

TOTAL_LINES=0
if [[ -n "$STATS_LINE" ]]; then
  TOTAL_LINES=$(echo "$STATS_LINE" | awk '{print $2}')
fi

# 磁盘检查（规则3），只在本机目录存在时运行
if [[ -d "$DIR" ]]; then
  AVAIL_KIB=$(df -k --output=avail "$DIR" 2>/dev/null | tail -1 | tr -d '[:space:]' || echo "")
  if [[ "$AVAIL_KIB" =~ ^[0-9]+$ ]]; then
    if (( AVAIL_KIB < 1048576 )); then
      ALERTS+=("ALERT [CRIT] disk_space: 可用空间 $((AVAIL_KIB / 1024)) MiB (<1GiB)")
      EXIT_CODE=2
    elif (( AVAIL_KIB < 5242880 )); then
      ALERTS+=("ALERT [WARN] disk_space: 可用空间 $((AVAIL_KIB / 1024)) MiB (<5GiB)")
      if [[ "$EXIT_CODE" != "2" ]]; then
        EXIT_CODE=1
      fi
    fi
  fi
fi

if [[ -z "$EXIT_CODE" ]]; then
  EXIT_CODE=0
fi

if [[ ${#ALERTS[@]} -eq 0 ]]; then
  echo "OK: 无告警（扫描 $TOTAL_LINES 行，窗口 $HOURS 小时）"
  exit 0
fi

for a in "${ALERTS[@]}"; do
  echo "$a"
done

exit "$EXIT_CODE"
