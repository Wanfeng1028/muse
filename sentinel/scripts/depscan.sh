
#!/usr/bin/env bash
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/..
TMP_DIR="$REPO/.depscan-tmp"
DOCS_DIR="$REPO/docs"
DATE=$(date +%Y%m%d)
REPORT="$DOCS_DIR/dependency-scan-$DATE.json"

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf '[PASS] %s\n' "$1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf '[FAIL] %s\n' "$1"
}

info() {
  printf '[INFO] %s\n' "$1"
}

cleanup() {
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT

mkdir -p "$TMP_DIR" "$DOCS_DIR"

# 阶段0：环境检查
if [ -d "$HOME/workspace/toolchains/go/bin" ]; then
  PATH="$HOME/workspace/toolchains/go/bin:$PATH"
  export PATH
fi

MISSING=""
command -v go >/dev/null 2>&1 || MISSING="$MISSING go"
command -v curl >/dev/null 2>&1 || MISSING="$MISSING curl"
command -v python3 >/dev/null 2>&1 || MISSING="$MISSING python3"

if [ -n "$MISSING" ]; then
  fail "缺少必要工具:$MISSING"
  exit 2
fi
pass "环境检查通过 (go/curl/python3)"

# 阶段1：模块清单
MODULES_JSON="$TMP_DIR/modules.json"
PAYLOAD="$TMP_DIR/payload.json"

if ! (cd "$REPO" && go list -json -m all) >"$MODULES_JSON" 2>"$TMP_DIR/golist.err"; then
  fail "go list -json -m all 执行失败"
  cat "$TMP_DIR/golist.err" >&2 || true
  exit 2
fi

if ! python3 - "$MODULES_JSON" "$PAYLOAD" <<'PYEOF'
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
dec = json.JSONDecoder()
buf = open(src, encoding="utf-8").read()
idx = 0
n = len(buf)
modules = []
while idx < n:
    while idx < n and buf[idx] in " \t\r\n":
        idx += 1
    if idx >= n:
        break
    obj, end = dec.raw_decode(buf, idx)
    idx = end
    if not isinstance(obj, dict):
        continue
    path = obj.get("Path")
    ver = obj.get("Version")
    if not path:
        continue
    if obj.get("Main"):
        continue
    if not ver:
        continue
    modules.append({"path": path, "version": ver})

with open(dst, "w", encoding="utf-8") as f:
    json.dump(
        {"queries": [
            {"package": {"name": m["path"], "ecosystem": "Go"}, "version": m["version"]}
            for m in modules
        ]},
        f,
    )

with open(dst + ".modules", "w", encoding="utf-8") as f:
    json.dump(modules, f)

print(len(modules))
PYEOF
then
  fail "组装 OSV payload 失败"
  exit 2
fi

MODULE_COUNT=$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))))' "$PAYLOAD.modules")
info "发现 $MODULE_COUNT 个依赖模块"

OSV_FAILED=0
if [ "$MODULE_COUNT" -eq 0 ]; then
  info "无外部依赖模块，跳过 OSV 查询"
  OSV_RAW="$TMP_DIR/osv.json"
  printf '{"results":[]}' >"$OSV_RAW"
else
  # 阶段2：OSV 批量查询
  OSV_RAW="$TMP_DIR/osv.json"
  OSV_URL="https://api.osv.dev/v1/querybatch"
  attempt=0
  ok=0
  while [ "$attempt" -lt 3 ]; do
    attempt=$((attempt + 1))
    if curl -sS --max-time 30 \
      -H 'Content-Type: application/json' \
      --data @"$PAYLOAD" \
      -o "$OSV_RAW" \
      "$OSV_URL"; then
      ok=1
      break
    fi
    info "OSV 查询失败，重试第 $attempt 次"
  done
  if [ "$ok" -ne 1 ]; then
    info "OSV 批量查询失败（本环境到 api.osv.dev 的 POST 被拦截），降级走 govulncheck"
    OSV_FAILED=1
  else
    pass "OSV 批量查询成功"
  fi
fi

# 阶段3：解析
SUMMARY_JSON="$TMP_DIR/summary.json"
if [ "$OSV_FAILED" -eq 0 ]; then
python3 - "$OSV_RAW" "$PAYLOAD.modules" "$SUMMARY_JSON" <<'PYEOF'
import json
import sys

osv_path, mod_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
osv = json.load(open(osv_path, encoding="utf-8"))
modules = json.load(open(mod_path, encoding="utf-8"))
results = osv.get("results") or []

vulns_out = []


def extract_fixed(aff):
    fixed = None
    for a in aff or []:
        for r in a.get("ranges") or []:
            for ev in r.get("events") or []:
                if "fixed" in ev and ev["fixed"]:
                    fixed = ev["fixed"]
    return fixed


for i, mod in enumerate(modules):
    if i >= len(results):
        break
    r = results[i] or {}
    vulns = r.get("vulns") or []
    for v in vulns:
        aliases = v.get("aliases") or []
        cves = [a for a in aliases if isinstance(a, str) and a.startswith("CVE-")]
        sev = ""
        for s in v.get("severity") or []:
            if isinstance(s, dict) and s.get("score"):
                sev = s.get("score")
                break
        fixed = extract_fixed(v.get("affected"))
        if fixed is None:
            fixed = "unknown"
        vulns_out.append({
            "module": mod["path"],
            "version": mod["version"],
            "osv_id": v.get("id") or "",
            "cves": cves,
            "summary": v.get("summary") or "",
            "severity": sev,
            "fixed_in": fixed,
        })

json.dump(vulns_out, open(out_path, "w", encoding="utf-8"))

for item in vulns_out:
    cve_str = ", ".join(item["cves"]) if item["cves"] else "无 CVE"
    sev = item["severity"] or "未标注"
    print(f"{item['module']}@{item['version']} -> {item['osv_id']} ({cve_str}) [{sev}] fixed in {item['fixed_in']}")
PYEOF

VULN_COUNT=$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))))' "$SUMMARY_JSON")

if [ "$VULN_COUNT" -eq 0 ]; then
  pass "OSV 未发现已知漏洞"
else
  fail "OSV 发现 $VULN_COUNT 个漏洞"
fi
else
  printf '[]' >"$SUMMARY_JSON"
  VULN_COUNT=0
  info "OSV 不可用，跳过 OSV 解析"
fi

# 阶段4：govulncheck
GOVULN_USED=false
GOVULN_OUTPUT=""

run_govulncheck() {
  local bin="$1"
  local out="$TMP_DIR/govulncheck.out"
  if (cd "$REPO" && "$bin" ./...) >"$out" 2>&1; then
    GOVULN_USED=true
    GOVULN_OUTPUT=$(cat "$out")
    return 0
  fi
  GOVULN_USED=true
  GOVULN_OUTPUT=$(cat "$out")
  return 0
}

if command -v govulncheck >/dev/null 2>&1; then
  info "使用 PATH 中的 govulncheck"
  run_govulncheck "$(command -v govulncheck)"
  pass "govulncheck 已执行"
else
  info "PATH 中无 govulncheck，尝试安装"
  GOBIN="$TMP_DIR/bin"
  mkdir -p "$GOBIN"
  if GOBIN="$GOBIN" timeout 180 go install golang.org/x/vuln/cmd/govulncheck@latest >"$TMP_DIR/install.log" 2>&1 && [ -x "$GOBIN/govulncheck" ]; then
    run_govulncheck "$GOBIN/govulncheck"
    pass "govulncheck 安装并执行成功"
  else
    GOVULN_USED=false
    GOVULN_OUTPUT="govulncheck 不可用，已降级为 OSV 查询"
    info "$GOVULN_OUTPUT"
  fi
fi

GOVULN_COUNT=0
if [ "$GOVULN_USED" = "true" ]; then
  GOVULN_COUNT=$(printf '%s' "$GOVULN_OUTPUT" | grep -c "^Vulnerability #" || true)
  info "govulncheck 报告 $GOVULN_COUNT 个漏洞"
fi

# 阶段5：落盘报告
REPORT="$REPORT" SUMMARY_JSON="$SUMMARY_JSON" OSV_RAW="$OSV_RAW" \
  MODULE_COUNT="$MODULE_COUNT" GOVULN_USED="$GOVULN_USED" GOVULN_OUTPUT="$GOVULN_OUTPUT" \
  OSV_FAILED="$OSV_FAILED" GOVULN_COUNT="$GOVULN_COUNT" \
  DATE="$DATE" python3 <<'PYEOF'
import json
import os

report_path = os.environ["REPORT"]
summary = json.load(open(os.environ["SUMMARY_JSON"], encoding="utf-8"))
try:
    osv_raw = json.load(open(os.environ["OSV_RAW"], encoding="utf-8"))
except Exception:
    osv_raw = {}

doc = {
    "date": os.environ["DATE"],
    "tool": "depscan.sh v0.6",
    "modules_scanned": int(os.environ["MODULE_COUNT"]),
    "vulnerabilities": summary,
    "govulncheck": {
        "used": os.environ["GOVULN_USED"] == "true",
        "vuln_count": int(os.environ["GOVULN_COUNT"]),
        "output": os.environ["GOVULN_OUTPUT"],
    },
    "osv_status": "unreachable" if os.environ["OSV_FAILED"] == "1" else "ok",
    "osv_raw": osv_raw,
}

with open(report_path, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)

sev_counts = {}
for v in summary:
    key = v.get("severity") or "unknown"
    sev_counts[key] = sev_counts.get(key, 0) + 1

print("===== 依赖漏洞扫描汇总 =====")
print(f"扫描模块数: {doc['modules_scanned']}")
print(f"漏洞总数(OSV): {len(summary)}")
print(f"漏洞总数(govulncheck): {os.environ['GOVULN_COUNT']}")
if sev_counts:
    print("按严重程度分组:")
    for k in sorted(sev_counts):
        print(f"  {k}: {sev_counts[k]}")
else:
    print("按严重程度分组: 无")
print(f"报告路径: {report_path}")
PYEOF

TOTAL_VULN=$(( VULN_COUNT + GOVULN_COUNT ))
if [ "$TOTAL_VULN" -gt 0 ]; then
  info "共发现 $TOTAL_VULN 个漏洞（OSV: $VULN_COUNT, govulncheck: $GOVULN_COUNT）"
  exit 1
fi
if [ "$OSV_FAILED" -eq 1 ] && [ "$GOVULN_USED" != "true" ]; then
  fail "OSV 与 govulncheck 均不可用，扫描未完成"
  exit 2
fi
pass "扫描完成，未发现已知漏洞"
exit 0
