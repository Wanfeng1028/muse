#!/usr/bin/env bash
# scripts/smoke_incidents.sh
# incidents 事件页 v0.8 冒烟验收：down -> recovered 事件闭环
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8200}"
PORT="${2:-8200}"
TARGET_DOWN="http://127.0.0.1:1/"
TARGET_UP="http://127.0.0.1:${PORT}/healthz"
MONITOR_NAME_PREFIX="smoke-incidents-"

fail() {
  echo "FAIL: $1"
  if [ "${2:-}" != "" ]; then
    echo "----- 接口返回体 -----"
    echo "$2"
    echo "----------------------"
  fi
  exit 1
}

pass() {
  echo "PASS: $1"
}

# 1. 环境检查
if ! command -v jq >/dev/null 2>&1; then
  echo "FAIL: 缺少 jq 命令，请先安装 jq" >&2
  exit 1
fi

if [ -z "${SENTINEL_API_TOKEN:-}" ]; then
  echo "FAIL: 环境变量 SENTINEL_API_TOKEN 未设置，无法进行鉴权" >&2
  exit 1
fi

AUTH_HEADER="Authorization: Bearer ${SENTINEL_API_TOKEN}"

# 幂等：生成唯一名称，避免与历史残留冲突
MONITOR_NAME="${MONITOR_NAME_PREFIX}$(date +%s)-$$"

MONITOR_ID=""

cleanup() {
  if [ -n "${MONITOR_ID}" ]; then
    local code
    code=$(curl -sS -o /dev/null -w '%{http_code}' \
      -X DELETE "${BASE_URL}/api/monitors/${MONITOR_ID}" \
      -H "${AUTH_HEADER}" || true)
    if [ "${code}" = "204" ]; then
      echo "INFO: 已清理监控 id=${MONITOR_ID}"
    else
      echo "INFO: 清理监控 id=${MONITOR_ID} 返回 http_code=${code}"
    fi
  fi
}
trap cleanup EXIT

echo "== smoke_incidents 开始 =="
echo "base_url=${BASE_URL} port=${PORT} monitor_name=${MONITOR_NAME}"

# 2. 创建监控（target 不可连，保证 down）
CREATE_BODY=$(jq -nc \
  --arg name "${MONITOR_NAME}" \
  --arg target "${TARGET_DOWN}" \
  '{name:$name, kind:"http", target:$target, interval_sec:3600}')

CREATE_RESP_FILE=$(mktemp)
CREATE_CODE=$(curl -sS -o "${CREATE_RESP_FILE}" -w '%{http_code}' \
  -X POST "${BASE_URL}/api/monitors" \
  -H "${AUTH_HEADER}" \
  -H 'Content-Type: application/json' \
  -d "${CREATE_BODY}")

CREATE_RESP=$(cat "${CREATE_RESP_FILE}")
rm -f "${CREATE_RESP_FILE}"

if [ "${CREATE_CODE}" != "201" ]; then
  fail "创建监控失败，期望 201，实际 ${CREATE_CODE}" "${CREATE_RESP}"
fi

MONITOR_ID=$(echo "${CREATE_RESP}" | jq -r '.id // empty')
if [ -z "${MONITOR_ID}" ] || [ "${MONITOR_ID}" = "null" ]; then
  fail "创建监控返回中缺少 id 字段" "${CREATE_RESP}"
fi
pass "创建监控成功 id=${MONITOR_ID}"

# 3. 触发检查（down）
CHECK1_FILE=$(mktemp)
CHECK1_CODE=$(curl -sS -o "${CHECK1_FILE}" -w '%{http_code}' \
  -X POST "${BASE_URL}/api/monitors/${MONITOR_ID}/check" \
  -H "${AUTH_HEADER}")
CHECK1_RESP=$(cat "${CHECK1_FILE}")
rm -f "${CHECK1_FILE}"

if [ "${CHECK1_CODE}" != "200" ]; then
  fail "第一次触发检查失败，期望 200，实际 ${CHECK1_CODE}" "${CHECK1_RESP}"
fi

CHECK1_OK=$(echo "${CHECK1_RESP}" | jq -r '.ok')
if [ "${CHECK1_OK}" != "false" ]; then
  fail "第一次检查期望 ok=false，实际 ok=${CHECK1_OK}" "${CHECK1_RESP}"
fi
pass "第一次检查触发成功 ok=false"

# 4. 断言 incidents 为 OPEN 态
INC1_FILE=$(mktemp)
INC1_CODE=$(curl -sS -o "${INC1_FILE}" -w '%{http_code}' \
  -X GET "${BASE_URL}/api/incidents?monitor_id=${MONITOR_ID}" \
  -H "${AUTH_HEADER}")
INC1_RESP=$(cat "${INC1_FILE}")
rm -f "${INC1_FILE}"

if [ "${INC1_CODE}" != "200" ]; then
  fail "查询 incidents 失败，期望 200，实际 ${INC1_CODE}" "${INC1_RESP}"
fi

INC1_COUNT=$(echo "${INC1_RESP}" | jq -r '.items | length')
if [ "${INC1_COUNT}" != "1" ]; then
  fail "OPEN 态断言失败：期望 incidents 数量为 1，实际 ${INC1_COUNT}" "${INC1_RESP}"
fi

INC1_ENDED=$(echo "${INC1_RESP}" | jq -r '.items[0].ended_at')
if [ "${INC1_ENDED}" != "null" ]; then
  fail "OPEN 态断言失败：期望 ended_at 为 null，实际 ${INC1_ENDED}" "${INC1_RESP}"
fi

INC1_MON_ID=$(echo "${INC1_RESP}" | jq -r '.items[0].monitor_id')
INC1_MON_NAME=$(echo "${INC1_RESP}" | jq -r '.items[0].monitor_name')
INC1_STARTED=$(echo "${INC1_RESP}" | jq -r '.items[0].started_at')
INC1_DOWNTIME=$(echo "${INC1_RESP}" | jq -r '.items[0].downtime_sec')

if [ "${INC1_MON_ID}" != "${MONITOR_ID}" ]; then
  fail "OPEN 态断言失败：incident.monitor_id 期望 ${MONITOR_ID}，实际 ${INC1_MON_ID}" "${INC1_RESP}"
fi
if [ "${INC1_MON_NAME}" != "${MONITOR_NAME}" ]; then
  fail "OPEN 态断言失败：incident.monitor_name 期望 ${MONITOR_NAME}，实际 ${INC1_MON_NAME}" "${INC1_RESP}"
fi
if [ -z "${INC1_STARTED}" ] || [ "${INC1_STARTED}" = "null" ]; then
  fail "OPEN 态断言失败：started_at 为空" "${INC1_RESP}"
fi
if [ "${INC1_DOWNTIME}" != "null" ]; then
  fail "OPEN 态断言失败：期望 downtime_sec 为 null，实际 ${INC1_DOWNTIME}" "${INC1_RESP}"
fi

INCIDENT_ID=$(echo "${INC1_RESP}" | jq -r '.items[0].id')
pass "OPEN 态断言通过 incident_id=${INCIDENT_ID}"

# 5. 修改 target 为可连地址
UPDATE_BODY=$(jq -nc --arg name "${MONITOR_NAME}" --arg target "${TARGET_UP}" '{name:$name,kind:"http",target:$target}')
UPDATE_FILE=$(mktemp)
UPDATE_CODE=$(curl -sS -o "${UPDATE_FILE}" -w '%{http_code}' \
  -X PUT "${BASE_URL}/api/monitors/${MONITOR_ID}" \
  -H "${AUTH_HEADER}" \
  -H 'Content-Type: application/json' \
  -d "${UPDATE_BODY}")
UPDATE_RESP=$(cat "${UPDATE_FILE}")
rm -f "${UPDATE_FILE}"

if [ "${UPDATE_CODE}" != "200" ]; then
  fail "更新监控 target 失败，期望 200，实际 ${UPDATE_CODE}" "${UPDATE_RESP}"
fi
pass "更新监控 target 为 ${TARGET_UP}"

# 6. 再次触发检查（up -> recovered）
CHECK2_FILE=$(mktemp)
CHECK2_CODE=$(curl -sS -o "${CHECK2_FILE}" -w '%{http_code}' \
  -X POST "${BASE_URL}/api/monitors/${MONITOR_ID}/check" \
  -H "${AUTH_HEADER}")
CHECK2_RESP=$(cat "${CHECK2_FILE}")
rm -f "${CHECK2_FILE}"

if [ "${CHECK2_CODE}" != "200" ]; then
  fail "第二次触发检查失败，期望 200，实际 ${CHECK2_CODE}" "${CHECK2_RESP}"
fi
pass "第二次检查触发成功"

# 7. 断言 incidents 为 RECOVERED 态
INC2_FILE=$(mktemp)
INC2_CODE=$(curl -sS -o "${INC2_FILE}" -w '%{http_code}' \
  -X GET "${BASE_URL}/api/incidents?monitor_id=${MONITOR_ID}" \
  -H "${AUTH_HEADER}")
INC2_RESP=$(cat "${INC2_FILE}")
rm -f "${INC2_FILE}"

if [ "${INC2_CODE}" != "200" ]; then
  fail "查询 incidents 失败，期望 200，实际 ${INC2_CODE}" "${INC2_RESP}"
fi

INC2_COUNT=$(echo "${INC2_RESP}" | jq -r '.items | length')
if [ "${INC2_COUNT}" != "1" ]; then
  fail "RECOVERED 态断言失败：期望 incidents 数量为 1，实际 ${INC2_COUNT}" "${INC2_RESP}"
fi

INC2_ENDED=$(echo "${INC2_RESP}" | jq -r '.items[0].ended_at')
if [ -z "${INC2_ENDED}" ] || [ "${INC2_ENDED}" = "null" ]; then
  fail "RECOVERED 态断言失败：期望 ended_at 非空，实际 ${INC2_ENDED}" "${INC2_RESP}"
fi

INC2_DOWNTIME=$(echo "${INC2_RESP}" | jq -r '.items[0].downtime_sec')
if [ "${INC2_DOWNTIME}" = "null" ] || [ -z "${INC2_DOWNTIME}" ]; then
  fail "RECOVERED 态断言失败：downtime_sec 为空" "${INC2_RESP}"
fi

if ! awk -v v="${INC2_DOWNTIME}" 'BEGIN { exit !(v+0 >= 0) }'; then
  fail "RECOVERED 态断言失败：downtime_sec 期望 >=0，实际 ${INC2_DOWNTIME}" "${INC2_RESP}"
fi

INC2_ID=$(echo "${INC2_RESP}" | jq -r '.items[0].id')
INC2_MON_ID=$(echo "${INC2_RESP}" | jq -r '.items[0].monitor_id')
INC2_MON_NAME=$(echo "${INC2_RESP}" | jq -r '.items[0].monitor_name')
INC2_STARTED=$(echo "${INC2_RESP}" | jq -r '.items[0].started_at')

if [ "${INC2_ID}" != "${INCIDENT_ID}" ]; then
  fail "RECOVERED 态断言失败：incident.id 期望 ${INCIDENT_ID}，实际 ${INC2_ID}" "${INC2_RESP}"
fi
if [ "${INC2_MON_ID}" != "${MONITOR_ID}" ]; then
  fail "RECOVERED 态断言失败：monitor_id 期望 ${MONITOR_ID}，实际 ${INC2_MON_ID}" "${INC2_RESP}"
fi
if [ "${INC2_MON_NAME}" != "${MONITOR_NAME}" ]; then
  fail "RECOVERED 态断言失败：monitor_name 期望 ${MONITOR_NAME}，实际 ${INC2_MON_NAME}" "${INC2_RESP}"
fi
if [ -z "${INC2_STARTED}" ] || [ "${INC2_STARTED}" = "null" ]; then
  fail "RECOVERED 态断言失败：started_at 为空" "${INC2_RESP}"
fi

pass "RECOVERED 态断言通过 incident_id=${INCIDENT_ID} downtime_sec=${INC2_DOWNTIME}"

# 8. 清理监控
DELETE_CODE=$(curl -sS -o /dev/null -w '%{http_code}' \
  -X DELETE "${BASE_URL}/api/monitors/${MONITOR_ID}" \
  -H "${AUTH_HEADER}")
if [ "${DELETE_CODE}" != "204" ]; then
  fail "删除监控失败，期望 204，实际 ${DELETE_CODE}"
fi
pass "删除监控成功 id=${MONITOR_ID}"
MONITOR_ID=""

echo "== smoke_incidents 全部通过 =="
