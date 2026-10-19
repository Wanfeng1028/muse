#!/usr/bin/env bash
# =============================================================================
# scripts/seed-shot-users.sh
#
# 用途：为 mini-os v1.7 截图重拍造一套干净的演示种子数据。
#       v1.7 的两张截图（viewer 页桌面图标与权限矩阵重叠、admin 页用户名是
#       svmvb5zuig 之类的测试脏数据）需要重拍，先跑本脚本造出用户名干净、
#       数据真实的演示账号。
#
# 演示密码：ShotDemo123
#   本地截图抛弃型库专用密码，明文写在这里，不玩脱敏。
#
# 前置条件：
#   1. mini-os 服务已经启动（默认 http://127.0.0.1:8090，可用第一个参数覆盖）。
#   2. 数据库最好是 fresh 的（首个注册用户会自动成为 admin）；
#      若用户已存在（409），脚本会跳过注册、改走登录复用现有账号。
#   3. 依赖：bash + curl + python3，不依赖 jq。
#
# 用法：
#   ./scripts/seed-shot-users.sh
#   ./scripts/seed-shot-users.sh http://127.0.0.1:8090
# =============================================================================

set -euo pipefail

BASE="${1:-http://127.0.0.1:8090}"
DEMO_PASSWORD="ShotDemo123"

# cookie jar 目录，放在脚本同目录下
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COOKIE_DIR="${SCRIPT_DIR}/.shot-cookies"
mkdir -p "${COOKIE_DIR}"

COOKIE_ADMIN="${COOKIE_DIR}/zhangwei.cookie"
COOKIE_EDITOR="${COOKIE_DIR}/editor01.cookie"
COOKIE_VIEWER="${COOKIE_DIR}/viewer01.cookie"

# -----------------------------------------------------------------------------
# 工具函数
# -----------------------------------------------------------------------------

die() {
  echo "[错误] $*" >&2
  exit 1
}

# 从 stdin 读 JSON，用 python3 取某个顶层字段
json_field() {
  local field="$1"
  python3 -c "
import sys, json
data = json.load(sys.stdin)
val = data.get('${field}')
if val is None:
    print('')
elif isinstance(val, bool):
    print('true' if val else 'false')
else:
    print(val)
"
}

# 检查 HTTP 状态码是否在期望集合内；否则报错退出
# 用法：check_status <实际码> <期望码...> <描述>
check_status() {
  local actual="$1"; shift
  local desc="${!#}"
  # 去掉最后一个参数（desc），剩下的是期望码
  local expected=("${@:1:$#-1}")
  for e in "${expected[@]}"; do
    if [[ "${actual}" == "${e}" ]]; then
      return 0
    fi
  done
  die "${desc}：期望 HTTP ${expected[*]}，实际 HTTP ${actual}"
}

# 注册或登录，写 cookie jar，回显 user id
# 用法：register_or_login <username> <cookie_jar>
# 回显：<id> <role>
register_or_login() {
  local username="$1"
  local cookie_jar="$2"

  local body
  body=$(python3 -c "
import json
print(json.dumps({'username': '${username}', 'password': '${DEMO_PASSWORD}'}))
")

  local resp http_code
  resp=$(curl -sS -o "${COOKIE_DIR}/resp.tmp" -w '%{http_code}' \
    -c "${cookie_jar}" \
    -H 'Content-Type: application/json' \
    -X POST "${BASE}/api/auth/register" \
    -d "${body}") || die "注册 ${username} 请求失败"
  http_code="${resp}"

  if [[ "${http_code}" == "201" ]]; then
    echo "[注册] ${username} 注册成功 (201)" >&2
  elif [[ "${http_code}" == "409" ]]; then
    echo "[复用] ${username} 已存在 (409)，改走登录" >&2
    local login_resp login_code
    login_resp=$(curl -sS -o "${COOKIE_DIR}/resp.tmp" -w '%{http_code}' \
      -c "${cookie_jar}" \
      -H 'Content-Type: application/json' \
      -X POST "${BASE}/api/auth/login" \
      -d "${body}") || die "登录 ${username} 请求失败"
    login_code="${login_resp}"
    check_status "${login_code}" 200 "登录 ${username}"
  else
    cat "${COOKIE_DIR}/resp.tmp" >&2 || true
    die "注册 ${username} 失败：HTTP ${http_code}"
  fi

  # 解析 id 与 role
  local id role
  id=$(json_field id < "${COOKIE_DIR}/resp.tmp")
  role=$(json_field role < "${COOKIE_DIR}/resp.tmp")
  rm -f "${COOKIE_DIR}/resp.tmp"

  [[ -n "${id}" ]] || die "解析 ${username} 的 id 失败"
  echo "${id} ${role}"
}

# 用 admin 会话把某用户设为 viewer
# 用法：set_role <admin_cookie> <user_id> <role>
set_role() {
  local admin_cookie="$1"
  local user_id="$2"
  local role="$3"

  local body
  body=$(python3 -c "
import json
print(json.dumps({'role': '${role}'}))
")

  local http_code
  http_code=$(curl -sS -o "${COOKIE_DIR}/resp.tmp" -w '%{http_code}' \
    -b "${admin_cookie}" \
    -H 'Content-Type: application/json' \
    -X PUT "${BASE}/api/users/${user_id}/role" \
    -d "${body}") || die "设置用户 ${user_id} 角色失败"

  check_status "${http_code}" 200 "设置用户 ${user_id} 角色为 ${role}"
  echo "[角色] 用户 ${user_id} -> ${role} (200)" >&2
  rm -f "${COOKIE_DIR}/resp.tmp"
}

# 建文件夹或文件，回显创建节点的 id
# 用法：create_fs <cookie> <name> <kind> [parentId] [content]
# 回显：创建成功时输出节点 id
create_fs() {
  local cookie="$1"
  local name="$2"
  local kind="$3"
  local parent_id="${4:-}"
  local content="${5:-}"

  local body
  body=$(python3 -c "
import json, sys
obj = {'name': '${name}', 'kind': '${kind}'}
pid = '${parent_id}'
if pid != '':
    obj['parentId'] = int(pid)
content = sys.stdin.read()
if content != '':
    obj['content'] = content
print(json.dumps(obj, ensure_ascii=False))
" <<< "${content}")

  local http_code
  http_code=$(curl -sS -o "${COOKIE_DIR}/resp.tmp" -w '%{http_code}' \
    -b "${cookie}" \
    -H 'Content-Type: application/json' \
    -X POST "${BASE}/api/fs" \
    -d "${body}") || die "创建 ${kind} ${name} 请求失败"

  check_status "${http_code}" 201 "创建 ${kind} ${name}"
  echo "[文件] ${kind} ${name} 创建成功 (201)" >&2

  local new_id
  new_id=$(json_field id < "${COOKIE_DIR}/resp.tmp")
  rm -f "${COOKIE_DIR}/resp.tmp"
  echo "${new_id}"
}

# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------

echo "=== mini-os 截图种子脚本 ==="
echo "目标服务：${BASE}"
echo

# 1. 注册/登录三个用户
echo "--- 步骤 1：准备三个演示账号 ---"
read -r ADMIN_ID ADMIN_ROLE < <(register_or_login "zhangwei" "${COOKIE_ADMIN}")
read -r EDITOR_ID EDITOR_ROLE < <(register_or_login "editor01" "${COOKIE_EDITOR}")
read -r VIEWER_ID VIEWER_ROLE < <(register_or_login "viewer01" "${COOKIE_VIEWER}")

echo
echo "账号就绪："
echo "  zhangwei  id=${ADMIN_ID} role=${ADMIN_ROLE}"
echo "  editor01  id=${EDITOR_ID} role=${EDITOR_ROLE}"
echo "  viewer01  id=${VIEWER_ID} role=${VIEWER_ROLE}"
echo

# 2. 确保 zhangwei 是 admin（首个注册用户自动 admin，但若已存在可能不是）
if [[ "${ADMIN_ROLE}" != "admin" ]]; then
  # 若 zhangwei 不是 admin，说明库里已有别的 admin，无法自行提权。
  # 此时用 editor01 或 viewer01 的会话都不行，只能提示。
  echo "[警告] zhangwei 当前角色为 ${ADMIN_ROLE}，不是 admin。" >&2
  echo "[警告] 若库非 fresh，请先清库再跑，否则 admin 截图可能不对。" >&2
fi

# 3. 把 viewer01 设为 viewer（需要 admin 会话）
echo "--- 步骤 2：设置 viewer01 角色为 viewer ---"
if [[ "${VIEWER_ROLE}" != "viewer" ]]; then
  set_role "${COOKIE_ADMIN}" "${VIEWER_ID}" "viewer"
else
  echo "[跳过] viewer01 已经是 viewer" >&2
fi
echo

# 4. 造文件数据
echo "--- 步骤 3：造真实文件数据 ---"

# zhangwei：Documents 文件夹 + 项目计划.md + Desktop 文件夹 + 待办.txt
ADMIN_DOCS_ID=$(create_fs "${COOKIE_ADMIN}" "Documents" "folder")
ADMIN_DESKTOP_ID=$(create_fs "${COOKIE_ADMIN}" "Desktop" "folder")

PLAN_CONTENT=$(cat <<'EOF'
项目计划（2025 年 Q2）

1. 把文件管理器的拖拽上传修好，上周测试发现大文件会断。
2. 权限矩阵页面要加一个「按角色筛选」的下拉，现在人多了看着累。
3. 下个月初做一次全量备份演练，别等到出事才想起来。
4. 跟设计确认一下暗色模式的对比度，有人反馈看久了眼睛酸。
EOF
)
create_fs "${COOKIE_ADMIN}" "项目计划.md" "file" "${ADMIN_DOCS_ID}" "${PLAN_CONTENT}" >/dev/null

TODO_CONTENT=$(cat <<'EOF'
待办：
- 周五前把 v1.7 的截图重拍完，用干净账号。
- 找运维确认 8090 端口有没有被防火墙挡。
- 把读书笔记里那本《设计数据密集型应用》还给图书馆。
EOF
)
create_fs "${COOKIE_ADMIN}" "待办.txt" "file" "${ADMIN_DESKTOP_ID}" "${TODO_CONTENT}" >/dev/null

# editor01：Documents 文件夹 + 读书笔记.md
EDITOR_DOCS_ID=$(create_fs "${COOKIE_EDITOR}" "Documents" "folder")

NOTE_CONTENT=$(cat <<'EOF'
读书笔记：《设计数据密集型应用》第 5 章

复制那块讲得挺清楚，单主复制写冲突少，但主挂了要手动切。
多主复制适合多机房，但冲突解决得自己写逻辑，麻烦。
无主复制（Dynamo 那种）读写都发多个节点，靠 quorum 保证一致，
适合对可用性要求高、能接受最终一致的场景。
回头再看看第 7 章事务隔离级别，上次没太看懂可重复读和幻读的区别。
EOF
)
create_fs "${COOKIE_EDITOR}" "读书笔记.md" "file" "${EDITOR_DOCS_ID}" "${NOTE_CONTENT}" >/dev/null

# viewer01：不造文件（只读用户，空桌面更真实）
echo "[跳过] viewer01 是只读用户，不造文件" >&2
echo

# 5. 汇总
echo "=== 种子完成 ==="
echo
printf "%-12s %-10s %-8s\n" "用户名" "角色" "用户 id"
printf "%-12s %-10s %-8s\n" "------------" "----------" "--------"
printf "%-12s %-10s %-8s\n" "zhangwei" "${ADMIN_ROLE}" "${ADMIN_ID}"
printf "%-12s %-10s %-8s\n" "editor01" "${EDITOR_ROLE}" "${EDITOR_ID}"
printf "%-12s %-10s %-8s\n" "viewer01" "viewer" "${VIEWER_ID}"
echo
echo "提示："
echo "  - viewer 页截图：用 viewer01 登录（密码 ShotDemo123），桌面为空。"
echo "  - admin 页截图：用 zhangwei 登录（密码 ShotDemo123），可见全量用户。"
echo "  - 若 admin 页用户名仍脏，说明库非 fresh，请清库后重跑本脚本。"
echo
echo "演示密码：ShotDemo123（本地截图抛弃型库专用）"
