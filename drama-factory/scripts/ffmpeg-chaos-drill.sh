#!/usr/bin/env bash
#
# scripts/ffmpeg-chaos-drill.sh
# v2.29 ffmpeg 故障演练 (chaos drill)
#
# 目的：验证 "ffmpeg 进程被 kill -9 后，视频任务经退避重试最终 DONE"
#       —— 即 v2.29 引入的 "瞬时失败重试" 机制真实生效。
#
# 演练手法：
#   1) 起应用 (开放模式, mock 视频 provider)
#   2) 建 project -> episode -> shot -> submit-all
#   3) 等任务进入 PROCESSING (ffmpeg 已被拉起)
#   4) 精确 kill -9 掉 *本演练* 拉起的、命令行含 testsrc 的 ffmpeg 进程
#      —— 不杀他人进程：先记录 before 快照，只 kill 新出现的 PID
#   5) 轮询 video-tasks，期望 attempts>=1 且最终 status=DONE
#
# 产物落 ./target/chaos-drill/ (相对仓库根, 不写 /tmp)
#
set -euo pipefail

# ---------- 0. 路径 & 环境 ----------
# 脚本位于 <repo>/scripts/ 下，仓库根 = 脚本目录的上一级
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# 工具链 PATH 与 s1 保持一致
export JAVA_HOME="${JAVA_HOME:-$HOME/workspace/toolchains/jdk}"
export PATH="$HOME/workspace/toolchains/maven/bin:$HOME/workspace/toolchains/jdk/bin:$PATH"

PORT="${PORT:-8081}"
BASE_URL="http://127.0.0.1:${PORT}"

DRILL_DIR="${REPO_ROOT}/target/chaos-drill"
mkdir -p "${DRILL_DIR}"
FFMPEG_BEFORE="${DRILL_DIR}/ffmpeg_before.txt"
APP_LOG="${DRILL_DIR}/app.log"
APP_PID=""

echo "[chaos] repo=${REPO_ROOT}"
echo "[chaos] JAVA_HOME=${JAVA_HOME}"
echo "[chaos] BASE_URL=${BASE_URL}"

# ---------- 1. 打包 ----------
# 直接用打好的 jar 起应用 (mvn spring-boot:run 太慢)。
# target 下可能有多个 jar (plain / original / sources)，取第一个非 sources 的。
echo "[chaos] packaging (mvn -o -q -DskipTests package) ..."
mvn -o -q -DskipTests package

JAR="$(ls target/*.jar 2>/dev/null | grep -v sources | head -1 || true)"
if [[ -z "${JAR}" || ! -f "${JAR}" ]]; then
  echo "[chaos][FATAL] 打包后未在 target/ 下找到可执行 jar" >&2
  exit 1
fi
echo "[chaos] jar=${JAR}"

# ---------- 2. 记录当前 ffmpeg PID 快照 ----------
# 本机可能有其他 agent 的 ffmpeg 进程。这里先拍快照，
# 之后只 kill *新出现的* ffmpeg，避免误伤他人。
pgrep -f ffmpeg > "${FFMPEG_BEFORE}" 2>/dev/null || true
BEFORE_COUNT="$(wc -l < "${FFMPEG_BEFORE}" | tr -d ' ')"
echo "[chaos] ffmpeg before snapshot: ${BEFORE_COUNT} pid(s) -> ${FFMPEG_BEFORE}"

# ---------- 3. 清理函数 / trap ----------
cleanup() {
  # 只杀本脚本拉起的应用进程；ffmpeg 由应用管理，应用退出后自行收尾
  if [[ -n "${APP_PID}" ]] && kill -0 "${APP_PID}" 2>/dev/null; then
    echo "[chaos] cleanup: stopping app pid=${APP_PID}"
    kill "${APP_PID}" 2>/dev/null || true
    # 给应用一点时间优雅退出
    for _ in $(seq 1 20); do
      kill -0 "${APP_PID}" 2>/dev/null || break
      sleep 0.5
    done
    kill -9 "${APP_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ---------- 4. 后台启动应用 ----------
# AUTH_JWT_SECRET 置空 => 开放模式 (JwtAuthFilter 放行, 无需登录)
# VIDEO_PROVIDER=mock => 走 mock 视频 provider，模拟 ffmpeg 调用
echo "[chaos] starting app (AUTH_JWT_SECRET= empty -> open mode) ..."
AUTH_JWT_SECRET= VIDEO_PROVIDER=mock nohup java -jar "${JAR}" \
  > "${APP_LOG}" 2>&1 &
APP_PID=$!
echo "[chaos] app pid=${APP_PID}, log=${APP_LOG}"

# ---------- 5. 等待健康检查就绪 (最多 120s) ----------
echo "[chaos] waiting for ${BASE_URL}/actuator/health ..."
READY=0
for _ in $(seq 1 120); do
  if curl -sf "${BASE_URL}/actuator/health" > /dev/null 2>&1; then
    READY=1
    break
  fi
  # 应用若已挂掉则直接失败
  if ! kill -0 "${APP_PID}" 2>/dev/null; then
    echo "[chaos][FATAL] app exited before becoming ready" >&2
    tail -n 50 "${APP_LOG}" >&2 || true
    exit 1
  fi
  sleep 1
done
if [[ "${READY}" -ne 1 ]]; then
  echo "[chaos][FATAL] health check timeout (120s)" >&2
  tail -n 50 "${APP_LOG}" >&2 || true
  exit 1
fi
echo "[chaos] app is healthy"

# ---------- 小工具：用 python3 从 JSON 里抠 id 字段 ----------
# 假设本机无 jq，用 python3 -c 解析。
json_id() {
  python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])'
}

# ---------- 6. 建 project / episode / shot ----------
echo "[chaos] POST /api/projects ..."
PID_JSON="$(curl -sf -X POST "${BASE_URL}/api/projects" \
  -H 'Content-Type: application/json' \
  -d '{"title":"chaos-drill","genre":"演练"}')"
PROJECT_ID="$(printf '%s' "${PID_JSON}" | json_id)"
echo "[chaos] project id=${PROJECT_ID}"

echo "[chaos] POST /api/projects/${PROJECT_ID}/episodes ..."
EP_JSON="$(curl -sf -X POST "${BASE_URL}/api/projects/${PROJECT_ID}/episodes" \
  -H 'Content-Type: application/json' \
  -d '{"episodeNo":1,"title":"演练集"}')"
EPISODE_ID="$(printf '%s' "${EP_JSON}" | json_id)"
echo "[chaos] episode id=${EPISODE_ID}"

# durationSeconds=8: 给 kill ffmpeg 留出时间窗口
echo "[chaos] POST /api/episodes/${EPISODE_ID}/shots ..."
SHOT_JSON="$(curl -sf -X POST "${BASE_URL}/api/episodes/${EPISODE_ID}/shots" \
  -H 'Content-Type: application/json' \
  -d '{"shotNo":1,"shotSize":"ZHONG_JING","cameraMove":"GU_DING","description":"演练镜","dialogue":"你好","videoPrompt":"中景","durationSeconds":8}')"
SHOT_ID="$(printf '%s' "${SHOT_JSON}" | json_id)"
echo "[chaos] shot id=${SHOT_ID}"

# ---------- 7. submit-all + 等 PROCESSING ----------
echo "[chaos] POST /api/episodes/${EPISODE_ID}/video-tasks/submit-all ..."
curl -sf -X POST "${BASE_URL}/api/episodes/${EPISODE_ID}/video-tasks/submit-all" \
  -o /dev/null

# 小工具：抓 shot 的视频任务数组
fetch_tasks() {
  curl -sf "${BASE_URL}/api/shots/${SHOT_ID}/video-tasks"
}

# 小工具：从任务数组里取第一个任务的 status / attempts
task_field() {
  local field="$1"
  fetch_tasks | python3 -c "
import sys, json
arr = json.load(sys.stdin)
if not arr:
    print('')
else:
    v = arr[0].get('${field}')
    print('' if v is None else v)
"
}

echo "[chaos] waiting for status=PROCESSING (max 30s) ..."
SEEN_PROCESSING=0
for _ in $(seq 1 60); do
  ST="$(task_field status || true)"
  if [[ "${ST}" == "PROCESSING" ]]; then
    SEEN_PROCESSING=1
    break
  fi
  # 若直接冲到 DONE 也无所谓，下面 kill 就杀不到新 ffmpeg
  if [[ "${ST}" == "DONE" ]]; then
    echo "[chaos][WARN] task already DONE before kill window; drill degenerate"
    break
  fi
  sleep 0.5
done
if [[ "${SEEN_PROCESSING}" -eq 1 ]]; then
  echo "[chaos] task is PROCESSING (ffmpeg should be running)"
else
  echo "[chaos][WARN] did not observe PROCESSING within 30s (status=${ST:-unknown})"
fi

# ---------- 8. 精确 kill 本演练拉起的 ffmpeg ----------
# 策略：只杀 *新出现的*、命令行含 testsrc 的 ffmpeg 进程。
#   - pgrep -f testsrc: 我们 mock provider 用 testsrc 作为输入源
#   - comm -13 before new: 取 "new 有 before 没有" 的 PID
#   - 严禁 pkill -9 ffmpeg 无差别杀 —— 会误伤其他 agent 的进程
echo "[chaos] locating newly-spawned ffmpeg (testsrc) ..."
NEW_FFMPEG="${DRILL_DIR}/ffmpeg_new.txt"
pgrep -f testsrc > "${NEW_FFMPEG}" 2>/dev/null || true

# 只保留 before 里没有的 PID
KILL_PIDS="$(comm -13 <(sort "${FFMPEG_BEFORE}") <(sort "${NEW_FFMPEG}") || true)"
if [[ -z "${KILL_PIDS}" ]]; then
  echo "[chaos][FATAL] 未发现本演练新拉起的 ffmpeg(testsrc) 进程，无法演练" >&2
  echo "[chaos] before=$(cat "${FFMPEG_BEFORE}" | tr '\n' ' ')" >&2
  echo "[chaos] testsrc_now=$(cat "${NEW_FFMPEG}" | tr '\n' ' ')" >&2
  tail -n 50 "${APP_LOG}" >&2 || true
  exit 1
fi

echo "[chaos] kill -9 (仅本演练新起的 testsrc ffmpeg, 不杀他人进程):"
for p in ${KILL_PIDS}; do
  echo "    pid=${p}  cmd=$(ps -o args= -p "${p}" 2>/dev/null || echo '?')"
  kill -9 "${p}" 2>/dev/null || true
done

# ---------- 9. 轮询等 DONE (最多 120s) ----------
# 期望：attempts>=1（说明触发过重试），最终 status=DONE
echo "[chaos] waiting for recovery: attempts>=1 and status=DONE (max 120s) ..."
FINAL_STATUS=""
FINAL_ATTEMPTS=""
for _ in $(seq 1 240); do
  ST="$(task_field status || true)"
  AT="$(task_field attempts || true)"
  if [[ "${ST}" == "DONE" ]]; then
    FINAL_STATUS="${ST}"
    FINAL_ATTEMPTS="${AT}"
    break
  fi
  if [[ "${ST}" == "FAILED" ]]; then
    FINAL_STATUS="${ST}"
    FINAL_ATTEMPTS="${AT}"
    break
  fi
  sleep 0.5
done

# ---------- 10. 结论 ----------
if [[ "${FINAL_STATUS}" == "DONE" && -n "${FINAL_ATTEMPTS}" && "${FINAL_ATTEMPTS}" -ge 1 ]]; then
  echo "CHAOS DRILL PASS: 任务在 ffmpeg 被 kill 后经重试恢复 DONE（attempts=${FINAL_ATTEMPTS}）"
  exit 0
fi

echo "CHAOS DRILL FAIL: final status=${FINAL_STATUS:-unknown} attempts=${FINAL_ATTEMPTS:-unknown}" >&2
echo "[chaos] --- app.log tail (50) ---" >&2
tail -n 50 "${APP_LOG}" >&2 || true
exit 1
