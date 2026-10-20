"""Tao thu muc project moi cho mot video, kem content.json mau.

  python new_project.py <duong-dan-project> [so-card]
"""
import json
import os
import sys

MAU = {
    "source": "<dan link bai goc vao day>",
    "handle": "Threads",
    "watermark": "CHUYỆN NGƯỜI BÁN HÀNG",
    "watermark_sub": "GÓC NHÌN THẬT TỪ CỘNG ĐỒNG",
    "cards": [],
}


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Dung: python new_project.py <duong-dan-project> [so-card]")
    proj = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6

    for sub in ("cards", "voice", "work", "output"):
        os.makedirs(os.path.join(proj, sub), exist_ok=True)

    data = dict(MAU)
    data["cards"] = [
        {"role": "question" if i == 1 else "answer",
         "name": "Bài đăng" if i == 1 else f"Bình luận {i - 1}",
         "speak": "<loi doc nguyen van, mo rong viet tat de may doc dung>"}
        for i in range(1, n + 1)
    ]
    path = os.path.join(proj, "content.json")
    if os.path.exists(path):
        print(f"Da co {path}, khong ghi de.")
    else:
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"Da tao {path} voi {n} card mau")

    print(f"""
Buoc tiep theo (chay TRONG thu muc {proj}):
  python <skill>/scripts/tts.py
  python <skill>/scripts/build_bg.py
  python <skill>/scripts/build_final.py
""")


if __name__ == "__main__":
    main()
