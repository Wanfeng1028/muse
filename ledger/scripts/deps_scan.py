"""依赖定期扫描：过期依赖 + OSV 已知漏洞。

仅使用 Python 标准库。依赖清单从 pyproject.toml 的 [project].dependencies 读取，
不做任何包名硬编码。

用法：
    python scripts/deps_scan.py           # 人类可读报告
    python scripts/deps_scan.py --json    # 机器可读 JSON

exit code：
    0 = 无问题
    1 = 发现已知漏洞，或有包过期超过 1 个大版本
    2 = 扫描本身失败
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from importlib import metadata
from pathlib import Path

OSV_URL = "https://api.osv.dev/v1/querybatch"
PIP_OUTDATED_TIMEOUT = 120
OSV_TIMEOUT = 30
ECOSYSTEM = "PyPI"


def find_pyproject() -> Path:
    """从脚本位置向上查找 pyproject.toml。"""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("未找到 pyproject.toml")


def parse_dependencies(pyproject: Path) -> list[dict]:
    """解析 [project].dependencies，返回 [{name, raw, specifier}]。"""
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    raw_deps = data.get("project", {}).get("dependencies", [])
    parsed = []
    for raw in raw_deps:
        name = raw
        specifier = ""
        for sep in [">=", "<=", "==", "!=", "~=", ">", "<", "["]:
            idx = name.find(sep)
            if idx != -1:
                specifier = name[idx:]
                name = name[:idx]
                break
        parsed.append(
            {
                "name": name.strip(),
                "raw": raw,
                "specifier": specifier.strip(),
            }
        )
    return parsed


def installed_version(name: str) -> str | None:
    """用 importlib.metadata 查已安装版本。"""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def check_outdated() -> tuple[dict | None, str | None]:
    """调 pip list --outdated，返回 (最新版本映射, 错误原因)。"""
    cmd = [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=PIP_OUTDATED_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, f"pip 命令超时（>{PIP_OUTDATED_TIMEOUT}s）"
    except OSError as exc:
        return None, f"pip 命令无法执行：{exc}"

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip() or f"exit code {proc.returncode}"
        return None, stderr

    try:
        rows = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return None, f"pip 输出无法解析：{exc}"

    latest: dict[str, str] = {}
    for row in rows:
        pkg = row.get("name", "")
        if pkg:
            latest[pkg.lower()] = row.get("latest_version", "")
    return latest, None


def query_osv(queries: list[dict]) -> tuple[dict | None, str | None]:
    """调 OSV querybatch，返回 (name_lower -> [vuln_ids], 错误原因)。"""
    if not queries:
        return {}, None

    body = json.dumps({"queries": queries}).encode("utf-8")
    req = urllib.request.Request(
        OSV_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=OSV_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return None, f"OSV 返回 HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return None, f"OSV 不可达：{exc.reason}"
    except TimeoutError:
        return None, f"OSV 请求超时（>{OSV_TIMEOUT}s）"
    except json.JSONDecodeError as exc:
        return None, f"OSV 响应无法解析：{exc}"

    vulns: dict[str, list[str]] = {}
    results = payload.get("results", [])
    for query, result in zip(queries, results):
        name = query["package"]["name"].lower()
        ids = [v.get("id", "") for v in result.get("vulns", []) if v.get("id")]
        if ids:
            vulns.setdefault(name, []).extend(ids)
    return vulns, None


def major_of(version: str) -> int | None:
    """取版本号主版本，解析失败返回 None。"""
    if not version:
        return None
    head = version.split(".", 1)[0]
    head = head.split("+", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="依赖过期 + OSV 漏洞扫描")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args()

    report: dict = {"dependencies": [], "errors": []}
    exit_code = 0

    try:
        pyproject = find_pyproject()
    except FileNotFoundError as exc:
        report["errors"].append(str(exc))
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"扫描失败：{exc}")
        return 2

    deps = parse_dependencies(pyproject)
    latest_map, pip_error = check_outdated()

    queries = []
    for dep in deps:
        ver = installed_version(dep["name"])
        dep["installed"] = ver
        if ver:
            queries.append(
                {
                    "package": {"name": dep["name"], "ecosystem": ECOSYSTEM},
                    "version": ver,
                }
            )

    vuln_map, osv_error = query_osv(queries)

    if pip_error is not None:
        report["errors"].append(f"联网检查失败：{pip_error}")
    if osv_error is not None:
        report["errors"].append(f"漏洞库不可达：{osv_error}")

    has_vuln = False
    has_major_outdated = False

    for dep in deps:
        name_lower = dep["name"].lower()
        installed = dep["installed"]
        latest = None
        outdated = False
        major_outdated = False

        if latest_map is not None:
            latest = latest_map.get(name_lower)
            if latest and installed and latest != installed:
                outdated = True
                inst_major = major_of(installed)
                late_major = major_of(latest)
                if inst_major is not None and late_major is not None:
                    if late_major - inst_major > 1:
                        major_outdated = True

        vulns = vuln_map.get(name_lower, []) if vuln_map is not None else []

        if vulns:
            has_vuln = True
        if major_outdated:
            has_major_outdated = True

        report["dependencies"].append(
            {
                "name": dep["name"],
                "raw": dep["raw"],
                "installed": installed,
                "latest": latest,
                "outdated": outdated,
                "major_outdated": major_outdated,
                "vulnerabilities": vulns,
            }
        )

    if has_vuln or has_major_outdated:
        exit_code = 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("依赖扫描报告")
        print("=" * 60)
        for entry in report["dependencies"]:
            installed = entry["installed"] or "未安装"
            latest = entry["latest"] or "未知"
            print(f"- {entry['name']}  已安装：{installed}  最新：{latest}")
            if entry["vulnerabilities"]:
                print(f"    已知漏洞：{', '.join(entry['vulnerabilities'])}")
        if report["errors"]:
            print("-" * 60)
            for err in report["errors"]:
                print(f"警告：{err}")

    if pip_error is not None and latest_map is None:
        return 2

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
