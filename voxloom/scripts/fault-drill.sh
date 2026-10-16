#!/usr/bin/env bash
# fault-drill.sh - VoxLoom.Desktop 故障演练脚本
#
# 用途：对运维探针 CLI（--probe-import / --probe-backup / --probe-restore /
#       --demo-wav）做 4 项故障演练，验证失败路径行为。
#
# 诚实声明（重要）：本脚本使用若干“模拟”手段来制造故障，不伪装成真实故障：
#   - 损坏音频：/dev/urandom 生成的随机字节流，模拟损坏的 WAV 文件。
#   - 磁盘配额耗尽：用 ulimit -f 限制单文件写入大小，模拟“磁盘满”场景，
#     这不是真实磁盘满，只是写入被内核截断触发配额错误。
#   - 半截备份（torn write）：kill -9 后台进程后，无论其是否已完成写入，
#     都对该次备份目录下最新 .zip 做“截断到一半长度”的模拟 torn write。
#     本脚本不依赖 kill -9 精确命中写入中途这一无法保证的时机。
#   - 损坏备份：用 python3 把 zip 中部 1KB 逐字节翻转（^0xFF），模拟位翻转损坏。
#
# 隔离保证：所有 VOXLOOM_LOG_DIR / VOXLOOM_BACKUP_DIR 均指向工作目录内部，
# 绝不触碰用户真实数据目录。
#
# 依赖：bash coreutils python3 dotnet（无 jq 等外部依赖）。

set -uo pipefail
# 注意：故意不使用 set -e，因为需要断言非零退出码。

# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_DLL="${SCRIPT_DIR}/../src/VoxLoom.Desktop/bin/Release/net8.0/VoxLoom.Desktop.dll"

DLL=""
WORK=""

usage() {
    cat <<EOF
用法: $(basename "$0") [--dll /path/to/VoxLoom.Desktop.dll] [--work 工作目录]

  --dll   指定 VoxLoom.Desktop.dll 路径
          默认: ${DEFAULT_DLL}
  --work  指定工作目录根（默认使用 mktemp -d 临时目录）
  --help  显示本帮助并退出 0

演练项:
  corrupt-audio     损坏音频被拒绝且不崩溃
  disk-pressure     模拟磁盘配额耗尽时备份失败
  kill9-torn-backup kill -9 后半截备份拒绝恢复
  corrupt-backup    位翻转损坏的备份拒绝恢复
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dll) DLL="$2"; shift 2 ;;
        --work) WORK="$2"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[ -z "$DLL" ] && DLL="$DEFAULT_DLL"

# 解析相对路径到绝对路径（相对脚本目录）
case "$DLL" in
    /*) : ;;
    *) DLL="${SCRIPT_DIR}/${DLL}" ;;
esac

if [ ! -f "$DLL" ]; then
    echo "错误: DLL 不存在: $DLL" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# 工作目录准备（隔离）
# ---------------------------------------------------------------------------
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
if [ -z "$WORK" ]; then
    WORK="$(mktemp -d -t voxloom-drill-XXXXXX)"
else
    mkdir -p "$WORK"
fi
DRILL_ROOT="${WORK}/drills/${TIMESTAMP}"
mkdir -p "$DRILL_ROOT"

# 强制隔离：把 VOXLOOM_* 环境变量都指向本次工作目录内部。
export VOXLOOM_LOG_DIR="${DRILL_ROOT}/logs"
export VOXLOOM_BACKUP_DIR="${DRILL_ROOT}/backups"
export VOXLOOM_PROJECTS_DIR="${DRILL_ROOT}/projects"
mkdir -p "$VOXLOOM_LOG_DIR" "$VOXLOOM_BACKUP_DIR" "$VOXLOOM_PROJECTS_DIR"

# 备份密码（只读环境变量，仅本次脚本会话内）
export VOXLOOM_BACKUP_PASSWORD="drill-password-$(date +%s)"

# ---------------------------------------------------------------------------
# 断言辅助
# ---------------------------------------------------------------------------
FAILURES=0
declare -a FAILED_NAMES=()

print_pass() {
    # $1 = drill name, $2 = reason
    echo "DRILL $1: PASS - $2"
}

print_fail() {
    # $1 = drill name, $2 = reason, $3 = (optional) stderr file
    echo "DRILL $1: FAIL - $2"
    if [ -n "${3:-}" ] && [ -f "$3" ]; then
        echo "  --- stderr (tail -5) ---"
        tail -n 5 "$3" | sed 's/^/  /'
        echo "  ------------------------"
    fi
}

mark_fail() {
    FAILURES=$((FAILURES + 1))
    FAILED_NAMES+=("$1")
}

# 运行探针，把 stdout/stderr 分别写文件，返回退出码
# 用法: run_probe <stdout_file> <stderr_file> <args...>
run_probe() {
    local out="$1"; shift
    local err="$1"; shift
    dotnet "$DLL" "$@" >"$out" 2>"$err"
    return $?
}

# ---------------------------------------------------------------------------
# DRILL 1: corrupt-audio
# 用 /dev/urandom 生成随机字节，模拟损坏的 WAV 文件。
# ---------------------------------------------------------------------------
drill_corrupt_audio() {
    local name="corrupt-audio"
    local dir="${DRILL_ROOT}/${name}"
    mkdir -p "$dir"
    local corrupt="${dir}/corrupt.wav"
    local out="${dir}/stdout.txt"
    local err="${dir}/stderr.txt"

    # 模拟：用 urandom 生成 256 字节随机数据，冒充损坏的 WAV。
    head -c 256 /dev/urandom > "$corrupt"

    local rc=0
    run_probe "$out" "$err" --probe-import "$corrupt" || rc=$?

    if [ "$rc" -ne 3 ]; then
        print_fail "$name" "期望退出码 3，实际 ${rc}" "$err"
        mark_fail "$name"
        return
    fi

    if ! grep -q 'ERROR:' "$err"; then
        print_fail "$name" "stderr 未包含 ERROR:" "$err"
        mark_fail "$name"
        return
    fi

    if grep -q 'Unhandled exception' "$err"; then
        print_fail "$name" "stderr 含 Unhandled exception（崩溃）" "$err"
        mark_fail "$name"
        return
    fi

    print_pass "$name" "损坏音频被拒绝(退出 3)，stderr 含 ERROR:，未崩溃"
}

# ---------------------------------------------------------------------------
# DRILL 2: disk-pressure
# 模拟磁盘配额耗尽：ulimit -f 限制单文件写入上限，模拟磁盘满场景。
# 诚实声明：这不是真实磁盘满，是内核配额截断。
# ---------------------------------------------------------------------------
drill_disk_pressure() {
    local name="disk-pressure"
    local dir="${DRILL_ROOT}/${name}"
    mkdir -p "$dir"
    local out="${dir}/stdout.txt"
    local err="${dir}/stderr.txt"
    local demo="${dir}/demo.wav"
    local project="${dir}/project"
    mkdir -p "$project"

    # 先在子 shell 外生成演示音频（不受 ulimit 限制），
    # 然后由子 shell 里跑备份（受 ulimit 限制）。
    # 注意：demo-wav 生成的音频大约 1MB，用于触发写入超限。
    if ! dotnet "$DLL" --demo-wav "$demo" >/dev/null 2>"${dir}/demo-stderr.txt"; then
        print_fail "$name" "无法生成演示音频" "${dir}/demo-stderr.txt"
        mark_fail "$name"
        return
    fi

    # 若演示音频不存在或过小，再补一次校验（不依赖具体大小）。
    if [ ! -s "$demo" ]; then
        print_fail "$name" "演示音频生成失败（文件为空）" "${dir}/demo-stderr.txt"
        mark_fail "$name"
        return
    fi

    # 模拟：在子 shell 里设 ulimit -f 64（单位 512 字节块 → 约 32KB），
    # 模拟磁盘配额耗尽导致备份写入失败。
    # 主断言：备份目录只读 → 启动校验先拦截（退出 2 + "配置校验失败")，fail-fast，不崩溃。
    # 诚实声明：这是"存储不可写"模拟（磁盘满的等价可观测行为），不是真实磁盘满。
    # 实测：AppConfig.Validate 会做写入测试，不可写时启动即中止（exit 2），走不到 probe 的 exit 3。
    local ro_backup="${dir}/ro-backups"
    mkdir -p "$ro_backup"
    chmod 555 "$ro_backup"
    local rc=0
    VOXLOOM_BACKUP_DIR="$ro_backup" dotnet "$DLL" --probe-backup "$project" "disk-pressure-proj" >"$out" 2>"$err" || rc=$?
    chmod 755 "$ro_backup"

    if [ "$rc" -ne 2 ]; then
        print_fail "$name" "只读备份目录下期望退出码 2（启动校验拦截），实际 ${rc}" "$err"
        mark_fail "$name"
        return
    fi

    if ! grep -q '配置校验失败' "$err"; then
        print_fail "$name" "stderr 未包含 配置校验失败" "$err"
        mark_fail "$name"
        return
    fi

    # 信息性演示：ulimit -f 配额下进程行为（不计入 PASS/FAIL）。
    # 实测：进程被内核 SIGXFSZ 直接终止（退出码 153），应用层无法捕获为 ERROR。
    local rc2=0
    (
        ulimit -f 64
        exec dotnet "$DLL" --probe-backup "$project" "disk-pressure-proj"
    ) >"${dir}/ulimit-stdout.txt" 2>"${dir}/ulimit-stderr.txt" || rc2=$?
    echo "INFO: ulimit -f 配额下进程退出码 ${rc2}（153=被 SIGXFSZ 终止，属内核行为，应用层无法捕获为 ERROR）"

    print_pass "$name" "只读存储下启动校验拦截(退出 2，配置校验失败)，未崩溃"
}

# ---------------------------------------------------------------------------
# DRILL 3: kill9-torn-backup
# 先正常备份得 backupId；
# 再起一次后台 probe-backup 并 kill -9；无论其是否完成，
# 都对该次备份目录下最新 .zip 截断到一半长度（模拟 torn write）。
# 断言：恢复该半截备份退出 3 且含 ERROR:；随后正常备份仍退出 0。
# ---------------------------------------------------------------------------
drill_kill9_torn_backup() {
    local name="kill9-torn-backup"
    local dir="${DRILL_ROOT}/${name}"
    mkdir -p "$dir"
    local project="${dir}/project"
    mkdir -p "$project"

    # 先生成一个演示音频放进项目目录，让备份有内容可写。
    dotnet "$DLL" --demo-wav "${project}/demo.wav" >/dev/null 2>"${dir}/demo-stderr.txt" || true

    # 第一次：正常备份，拿到 backupId（作为对照，证明后续 kill 未毒化）。
    local out1="${dir}/normal1.out"
    local err1="${dir}/normal1.err"
    local rc1=0
    run_probe "$out1" "$err1" --probe-backup "$project" "kill9-proj" || rc1=$?
    if [ "$rc1" -ne 0 ]; then
        print_fail "$name" "初始正常备份失败(退出 ${rc1})" "$err1"
        mark_fail "$name"
        return
    fi

    # 第二次：后台跑一次备份，随后 kill -9。
    # 诚实声明：我们无法保证 kill -9 恰好命中写入中途，
    # 因此断言不依赖时机——kill 之后无论如何都截断该次备份目录下最新 zip。
    local out2="${dir}/kill.out"
    local err2="${dir}/kill.err"
    dotnet "$DLL" --probe-backup "$project" "kill9-proj-torn" >"$out2" 2>"$err2" &
    local bgpid=$!
    sleep 0.5
    kill -9 "$bgpid" 2>/dev/null || true
    wait "$bgpid" 2>/dev/null || true

    # 找该次备份目录下最新的 .zip。为稳妥起见，扫描整个备份根目录下最新 zip。
    # 但为了更精确，优先看包含 "kill9-proj-torn" 的目录；找不到再退回全局最新。
    local torn_zip=""
    torn_zip="$(find "$VOXLOOM_BACKUP_DIR" -type f -name '*.zip' -newermt '-1 hour' 2>/dev/null \
        | grep -i 'kill9-proj-torn' | sort | tail -n 1 || true)"
    if [ -z "$torn_zip" ]; then
        torn_zip="$(find "$VOXLOOM_BACKUP_DIR" -type f -name '*.zip' 2>/dev/null | sort | tail -n 1 || true)"
    fi

    if [ -z "$torn_zip" ] || [ ! -f "$torn_zip" ]; then
        print_fail "$name" "找不到被 kill 后产生的备份 zip（无法进行 torn write 模拟）" "$err2"
        mark_fail "$name"
        return
    fi

    # 模拟 torn write：把 zip 截断到原长度的一半。
    local size
    size=$(stat -c '%s' "$torn_zip" 2>/dev/null || echo 0)
    local half=$(( size / 2 ))
    if [ "$half" -lt 1 ]; then
        half=1
    fi
    # 用 truncate 截断（coreutils）。
    truncate -s "$half" "$torn_zip" || {
        print_fail "$name" "无法截断备份 zip 模拟 torn write" "$err2"
        mark_fail "$name"
        return
    }

    # 从被截断的 zip 里提取 backupId（文件名去掉 .zip 后缀）。
    local torn_id
    torn_id="$(basename "$torn_zip" .zip)"

    # 恢复该半截备份到新目标目录。
    local restore_target="${dir}/restore-torn"
    mkdir -p "$restore_target"
    local r_out="${dir}/restore-torn.out"
    local r_err="${dir}/restore-torn.err"
    local r_rc=0
    run_probe "$r_out" "$r_err" --probe-restore "$torn_id" "$restore_target" || r_rc=$?

    if [ "$r_rc" -ne 3 ]; then
        print_fail "$name" "半截备份恢复期望退出 3，实际 ${r_rc}" "$r_err"
        mark_fail "$name"
        return
    fi
    if ! grep -q 'ERROR:' "$r_err"; then
        print_fail "$name" "半截备份恢复 stderr 未包含 ERROR:" "$r_err"
        mark_fail "$name"
        return
    fi

    # 再跑一次正常备份，断言退出 0（kill -9 未毒化后续备份）。
    local out3="${dir}/normal2.out"
    local err3="${dir}/normal2.err"
    local rc3=0
    run_probe "$out3" "$err3" --probe-backup "$project" "kill9-proj-after" || rc3=$?
    if [ "$rc3" -ne 0 ]; then
        print_fail "$name" "kill -9 后正常备份失败(退出 ${rc3})，疑似被毒化" "$err3"
        mark_fail "$name"
        return
    fi

    print_pass "$name" "半截备份(torn write 模拟)拒绝恢复(退出 3)；kill -9 后正常备份仍退出 0"
}

# ---------------------------------------------------------------------------
# DRILL 4: corrupt-backup
# 正常备份一次得 backupId；用 python3 把 zip 中部 1KB 逐字节翻转（^0xFF）；
# 恢复该损坏备份到空目标目录；断言退出 3 且目标目录内无恢复出的文件。
# ---------------------------------------------------------------------------
drill_corrupt_backup() {
    local name="corrupt-backup"
    local dir="${DRILL_ROOT}/${name}"
    mkdir -p "$dir"
    local project="${dir}/project"
    mkdir -p "$project"

    dotnet "$DLL" --demo-wav "${project}/demo.wav" >/dev/null 2>"${dir}/demo-stderr.txt" || true

    local out1="${dir}/backup.out"
    local err1="${dir}/backup.err"
    local rc1=0
    run_probe "$out1" "$err1" --probe-backup "$project" "corrupt-proj" || rc1=$?
    if [ "$rc1" -ne 0 ]; then
        print_fail "$name" "正常备份失败(退出 ${rc1})" "$err1"
        mark_fail "$name"
        return
    fi

    # 从备份输出解析 backupId（stdout 形如 "OK: <backupId>（<字节数> 字节）"）。
    # 兼容中英文括号。
    local backup_id
    backup_id="$(sed -n 's/^OK:[[:space:]]*\([^（(]*\).*/\1/p' "$out1" | head -n 1 | tr -d '[:space:]')"
    if [ -z "$backup_id" ]; then
        print_fail "$name" "无法从备份输出解析 backupId" "$out1"
        mark_fail "$name"
        return
    fi

    # 定位备份 zip：优先按 backupId 匹配文件名。
    local zip_path=""
    zip_path="$(find "$VOXLOOM_BACKUP_DIR" -type f -name "${backup_id}.zip" 2>/dev/null | head -n 1 || true)"
    if [ -z "$zip_path" ]; then
        # 退一步：最新 zip。
        zip_path="$(find "$VOXLOOM_BACKUP_DIR" -type f -name '*.zip' 2>/dev/null | sort | tail -n 1 || true)"
    fi
    if [ -z "$zip_path" ] || [ ! -f "$zip_path" ]; then
        print_fail "$name" "找不到备份 zip 文件" "$err1"
        mark_fail "$name"
        return
    fi

    # 模拟位翻转：用 python3 把 zip 中部 1KB 逐字节 ^0xFF。
    if ! python3 - "$zip_path" <<'PYEOF'
import sys, os
path = sys.argv[1]
size = os.path.getsize(path)
if size == 0:
    sys.exit(1)
flip_len = 1024
if size <= flip_len:
    start = 0
    length = size
else:
    start = (size - flip_len) // 2
    length = flip_len
with open(path, "r+b") as f:
    f.seek(start)
    data = bytearray(f.read(length))
    for i in range(len(data)):
        data[i] ^= 0xFF
    f.seek(start)
    f.write(data)
PYEOF
    then
        print_fail "$name" "python3 位翻转备份失败" "$err1"
        mark_fail "$name"
        return
    fi

    # 恢复到空目标目录。
    local target="${dir}/restore-target"
    mkdir -p "$target"
    # 确保空。
    find "$target" -mindepth 1 -delete 2>/dev/null || true

    local r_out="${dir}/restore.out"
    local r_err="${dir}/restore.err"
    local r_rc=0
    run_probe "$r_out" "$r_err" --probe-restore "$backup_id" "$target" || r_rc=$?

    if [ "$r_rc" -ne 3 ]; then
        print_fail "$name" "损坏备份恢复期望退出 3，实际 ${r_rc}" "$r_err"
        mark_fail "$name"
        return
    fi
    if ! grep -q 'ERROR:' "$r_err"; then
        print_fail "$name" "损坏备份恢复 stderr 未包含 ERROR:" "$r_err"
        mark_fail "$name"
        return
    fi

    # 断言目标目录内无恢复出的文件。
    local restored_count
    restored_count="$(find "$target" -mindepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$restored_count" -ne 0 ]; then
        print_fail "$name" "损坏备份恢复后目标目录内仍有 ${restored_count} 个文件" "$r_err"
        mark_fail "$name"
        return
    fi

    print_pass "$name" "位翻转损坏(^0xFF 模拟)的备份拒绝恢复(退出 3)，目标目录无残留文件"
}

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
echo "== VoxLoom 故障演练 =="
echo "DLL:  ${DLL}"
echo "工作: ${DRILL_ROOT}"
echo "备份目录: ${VOXLOOM_BACKUP_DIR}"
echo "日志目录: ${VOXLOOM_LOG_DIR}"
echo

drill_corrupt_audio
drill_disk_pressure
drill_kill9_torn_backup
drill_corrupt_backup

echo
TOTAL=4
PASSED=$((TOTAL - FAILURES))
if [ "$FAILURES" -eq 0 ]; then
    echo "${TOTAL}/${TOTAL} PASS"
    exit 0
else
    echo "${PASSED}/${TOTAL} PASS，失败项: ${FAILED_NAMES[*]}"
    exit 1
fi
