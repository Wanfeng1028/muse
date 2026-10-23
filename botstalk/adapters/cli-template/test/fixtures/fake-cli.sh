#!/usr/bin/env bash
# 测试替身 CLI：模拟 coding CLI 的各种行为，供 cli-adapter.test.ts 做 E2E 与失败注入。
set -u

has_arg() {
  local want="$1"; shift
  for a in "$@"; do
    if [ "$a" = "$want" ]; then return 0; fi
  done
  return 1
}

# 按优先级匹配特殊行为（特殊 flag 优先于默认 stdin 回显）
if has_arg "--boom" "$@"; then
  echo "kaboom" >&2
  exit 3
fi

if has_arg "--big" "$@"; then
  # 输出 2MB 的 x（测试 stdout 截断）
  head -c 2097152 /dev/zero | tr '\0' 'x'
  exit 0
fi

if has_arg "--ignore-sigint" "$@"; then
  trap '' INT
  sleep 30
  exit 0
fi

if has_arg "--slow" "$@"; then
  sleep 30
  exit 0
fi

if has_arg "auth" "$@" && has_arg "status" "$@"; then
  echo '{"loggedIn": true}'
  exit 0
fi

if has_arg "--print" "$@"; then
  # 输出 --print 后面的参数
  prev=""
  for a in "$@"; do
    if [ "$prev" = "--print" ]; then echo "$a"; exit 0; fi
    prev="$a"
  done
  exit 0
fi

# 默认：stdin 原样回显到 stdout
cat
exit 0
