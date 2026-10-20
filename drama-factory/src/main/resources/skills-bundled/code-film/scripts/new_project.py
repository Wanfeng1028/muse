"""创建一个新的 code-film 视频工程（复制模板，写入标题、分辨率、帧率）。只用 Python 标准库。

用法：
  python new_project.py D:/films/sun --title "我从未见过太阳"
  python new_project.py D:/films/blue --title "天为什么是蓝的" --fps 30 --width 1080 --height 1920

工程必须放在纯英文路径下（中文路径偶尔会让渲染工具出错）。
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "remotion-template"


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="创建视频工程")
    ap.add_argument("dest", help="新工程目录（建议纯英文路径，例如 D:/films/sun）")
    ap.add_argument("--title", required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--force", action="store_true", help="目录已存在且非空时也创建")
    args = ap.parse_args()

    if not TEMPLATE.is_dir():
        sys.exit(f"找不到模板：{TEMPLATE}")
    if not re.fullmatch(r"[A-Za-z0-9_\-./:\\ ]+", args.dest) or re.search(r"[\u4e00-\u9fff]", args.dest):
        sys.exit("工程路径必须只用英文、数字、点、横线、下划线（中文路径可能让渲染出错）")
    if args.width % 2 or args.height % 2:
        sys.exit("宽高必须是偶数（H.264 要求）")

    dest = Path(args.dest).resolve()
    if dest.exists() and any(dest.iterdir()) and not args.force:
        sys.exit(f"{dest} 已存在且非空。换一个目录，或者加 --force")

    shutil.copytree(TEMPLATE, dest, dirs_exist_ok=True)

    sb_path = dest / "src" / "storyboard.json"
    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    sb["meta"]["title"] = args.title
    sb["meta"]["fps"] = args.fps
    sb["meta"]["width"] = args.width
    sb["meta"]["height"] = args.height
    # 演示配乐按 30fps 生成；帧率变了就先拿掉，等真实配乐就位
    if args.fps != 30:
        sb["meta"].pop("music", None)
        sb["meta"].pop("musicVolume", None)
        sb["meta"].pop("musicStartFrame", None)
    sb_path.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")

    pkg = dest / "package.json"
    pkg.write_text(pkg.read_text(encoding="utf-8").replace("code-film-project", dest.name), encoding="utf-8")

    print(f"[OK] {dest}")
    print("下一步：")
    print(f"  cd {dest.as_posix()}")
    print("  npm install")
    print("  npm run studio")


if __name__ == "__main__":
    main()
