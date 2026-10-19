#!/usr/bin/env bash
#
# hyperframes_probe.sh —— HyperFrames 渲染引擎运维探活脚本
#
# 用途：
#   部署 / 排障时一键检查 HyperFrames 渲染引擎的前置条件，
#   输出单行 JSON 到 stdout 供其他脚本消费（stdout 只打 JSON，日志走 stderr）。
#
# 环境变量：
#   HYPERFRAMES_CLI   指定 hyperframes CLI 可执行文件名或路径。
#                     默认值：hyperframes
#                     例：HYPERFRAMES_CLI=/usr/local/bin/hyperframes ./hyperframes_probe.sh
#
# 退出码：
#   0 = 探活流程执行完成（注意：不代表 hyperframes 一定可用！）
#       结论请以 JSON 中的 "engine" 字段为准：
#         "hyperframes" -> 推荐走 hyperframes 引擎
#         "chromium"    -> 回退到 chromium 引擎
#   其他非零值仅在脚本自身异常（例如 shell 内部错误）时可能出现；
#   检查项失败不会导致非零退出。
#
# 输出示例：
#   {"node":{"ok":true,"version":"v24.20.0"},"npm":{"ok":true,"version":"10.9.0"},"hyperframes":{"ok":true,"cli":"hyperframes","version":"0.8.176"},"engine":"hyperframes","note":"..."}
#

set -euo pipefail

log() {
  printf '%s\n' "$*" >&2
}

# 最小 JSON 字符串转义：反斜杠、双引号、控制字符（换行/回车/制表）
json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

# 取版本字符串中的主版本号（去掉前导 v，截取第一个数字段）
major_of() {
  local v="$1"
  v="${v#v}"
  printf '%s' "$v" | sed -n 's/^\([0-9]\{1,\}\).*/\1/p'
}

# ---------- node ----------
node_ok=false
node_version=""
node_major=0
node_err=""
if command -v node >/dev/null 2>&1; then
  if node_raw="$(node --version 2>/dev/null)"; then
    node_version="$(printf '%s' "$node_raw" | head -n 1)"
    node_ok=true
    node_major="$(major_of "$node_version")"
    [ -n "$node_major" ] || node_major=0
  else
    node_err="node --version 执行失败"
  fi
else
  node_err="未找到 node"
fi

# ---------- npm ----------
npm_ok=false
npm_version=""
npm_err=""
if command -v npm >/dev/null 2>&1; then
  if npm_raw="$(npm --version 2>/dev/null)"; then
    npm_version="$(printf '%s' "$npm_raw" | head -n 1)"
    npm_ok=true
  else
    npm_err="npm --version 执行失败"
  fi
else
  npm_err="未找到 npm"
fi

# ---------- hyperframes ----------
HF_CLI="${HYPERFRAMES_CLI:-hyperframes}"
hf_ok=false
hf_version=""
hf_err=""
hf_rc=""
if command -v "$HF_CLI" >/dev/null 2>&1; then
  set +e
  hf_out="$(timeout 15 "$HF_CLI" --version 2>/dev/null)"
  hf_rc=$?
  set -e
  if [ "$hf_rc" -eq 0 ]; then
    hf_version="$(printf '%s' "$hf_out" | head -n 1)"
    hf_ok=true
  elif [ "$hf_rc" -eq 124 ]; then
    hf_err="hyperframes --version 超时（15s）"
  else
    hf_err="hyperframes --version 退出码 $hf_rc"
  fi
else
  hf_err="未找到 CLI: $HF_CLI"
fi

# ---------- engine 判定 ----------
if [ "$hf_ok" = true ] && [ "$node_ok" = true ] && [ "$node_major" -ge 22 ] 2>/dev/null; then
  engine="hyperframes"
  note="hyperframes 探活成功且 node 主版本 >=22，推荐使用 hyperframes 引擎。"
else
  engine="chromium"
  if [ "$hf_ok" != true ]; then
    note="hyperframes 不可用（${hf_err:-未知原因}），降级为 chromium 引擎。"
  elif [ "$node_ok" != true ]; then
    note="node 不可用（${node_err:-未知原因}），降级为 chromium 引擎。"
  elif [ "$node_major" -lt 22 ] 2>/dev/null; then
    note="node 版本 ${node_version} 低于 v22，降级为 chromium 引擎。"
  else
    note="前置条件不满足，降级为 chromium 引擎。"
  fi
fi

# ---------- 组装 JSON ----------
node_ok_json=false; [ "$node_ok" = true ] && node_ok_json=true
npm_ok_json=false;  [ "$npm_ok" = true ]  && npm_ok_json=true
hf_ok_json=false;   [ "$hf_ok" = true ]   && hf_ok_json=true

json="{\"node\":{\"ok\":${node_ok_json},\"version\":\"$(json_escape "$node_version")\"},"
json="${json}\"npm\":{\"ok\":${npm_ok_json},\"version\":\"$(json_escape "$npm_version")\"},"
json="${json}\"hyperframes\":{\"ok\":${hf_ok_json},\"cli\":\"$(json_escape "$HF_CLI")\",\"version\":\"$(json_escape "$hf_version")\"},"
json="${json}\"engine\":\"$(json_escape "$engine")\","
json="${json}\"note\":\"$(json_escape "$note")\"}"

log "[hyperframes_probe] node=${node_ok}(${node_version:-n/a}) npm=${npm_ok}(${npm_version:-n/a}) hyperframes=${hf_ok}(${hf_version:-n/a}) engine=${engine}"
printf '%s\n' "$json"
exit 0
