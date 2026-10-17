"""v09 语料由 dpsk 批次直接生成，已落盘至 eval/corpus_v09/，本脚本仅做存在性校验。"""
from pathlib import Path
def main():
    d = Path(__file__).resolve().parent / "corpus_v09"
    assert d.is_dir() and any(d.iterdir()), "corpus_v09 missing"
    print("corpus_v09 ok:", len(list(d.iterdir())), "docs")
if __name__ == "__main__":
    main()
