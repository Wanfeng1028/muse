// Package search 提供轻量的关键词分词与相关性打分，用于笔记检索排序。
package search

import (
	"reflect"
	"testing"
)

func TestSegmentCJK_QuantumComputing(t *testing.T) {
	got := SegmentCJK("量子计算", cjkDictSet)
	want := []string{"量子", "计算"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SegmentCJK(量子计算) = %v, want %v", got, want)
	}
	if len(got) != 2 {
		t.Fatalf("SegmentCJK(量子计算) 词元数 = %d, want 2", len(got))
	}
}

func TestSegmentCJK_SingleCharFallback(t *testing.T) {
	got := SegmentCJK("鑫淼", cjkDictSet)
	want := []string{"鑫", "淼"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SegmentCJK(鑫淼) = %v, want %v", got, want)
	}
	if len(got) != 2 {
		t.Fatalf("SegmentCJK(鑫淼) 词元数 = %d, want 2", len(got))
	}
}

func TestSegmentCJK_MixedChineseEnglish(t *testing.T) {
	got := SegmentCJK("量子CPU计算", cjkDictSet)
	want := []string{"量子", "C", "P", "U", "计算"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SegmentCJK(量子CPU计算) = %v, want %v", got, want)
	}
	if len(got) != 5 {
		t.Fatalf("SegmentCJK(量子CPU计算) 词元数 = %d, want 5", len(got))
	}
}

func TestSegmentCJK_Empty(t *testing.T) {
	got := SegmentCJK("", cjkDictSet)
	if len(got) != 0 {
		t.Fatalf("SegmentCJK(\"\") = %v, want 空切片", got)
	}
	if got == nil {
		t.Fatalf("SegmentCJK(\"\") 返回 nil，期望非 nil 空切片")
	}
}

func TestSegmentCJK_LongestMatchFirst(t *testing.T) {
	got := SegmentCJK("量子计算机", cjkDictSet)
	want := []string{"量子", "计算", "机"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SegmentCJK(量子计算机) = %v, want %v", got, want)
	}
	if len(got) != 3 {
		t.Fatalf("SegmentCJK(量子计算机) 词元数 = %d, want 3", len(got))
	}
}

func TestSegmentCJK_FourCharWord(t *testing.T) {
	got := SegmentCJK("量子计算", cjkDictSet)
	if got[0] != "量子" {
		t.Fatalf("首词元 = %q, want 量子", got[0])
	}
	if got[1] != "计算" {
		t.Fatalf("次词元 = %q, want 计算", got[1])
	}
}

func TestSegmentCJK_ArtificialIntelligence(t *testing.T) {
	got := SegmentCJK("人工智能", cjkDictSet)
	want := []string{"人工智能"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SegmentCJK(人工智能) = %v, want %v", got, want)
	}
	if len(got) != 1 {
		t.Fatalf("SegmentCJK(人工智能) 词元数 = %d, want 1", len(got))
	}
}

func TestSegmentCJK_Learning(t *testing.T) {
	got := SegmentCJK("机器学习", cjkDictSet)
	want := []string{"机器学习"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SegmentCJK(机器学习) = %v, want %v", got, want)
	}
	if len(got) != 1 {
		t.Fatalf("SegmentCJK(机器学习) 词元数 = %d, want 1", len(got))
	}
}

func TestSegmentCJK_WithPunctuation(t *testing.T) {
	got := SegmentCJK("量子，计算", cjkDictSet)
	want := []string{"量子", "，", "计算"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SegmentCJK(量子，计算) = %v, want %v", got, want)
	}
	if len(got) != 3 {
		t.Fatalf("SegmentCJK(量子，计算) 词元数 = %d, want 3", len(got))
	}
}

func TestSegmentCJK_UnknownLongRunFallback(t *testing.T) {
	got := SegmentCJK("魑魅魍魉", cjkDictSet)
	want := []string{"魑", "魅", "魍", "魉"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SegmentCJK(魑魅魍魉) = %v, want %v", got, want)
	}
	if len(got) != 4 {
		t.Fatalf("SegmentCJK(魑魅魍魉) 词元数 = %d, want 4", len(got))
	}
}

func TestSegmentCJK_StopWordsNotRemoved(t *testing.T) {
	got := SegmentCJK("的了是", cjkDictSet)
	want := []string{"的", "了", "是"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SegmentCJK(的了是) = %v, want %v", got, want)
	}
	if len(got) != 3 {
		t.Fatalf("SegmentCJK(的了是) 词元数 = %d, want 3", len(got))
	}
}

func TestSegmentCJK_NilDictUsesDefault(t *testing.T) {
	got := SegmentCJK("量子计算", nil)
	want := []string{"量子", "计算"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SegmentCJK(量子计算, nil) = %v, want %v", got, want)
	}
	if len(got) != 2 {
		t.Fatalf("SegmentCJK(量子计算, nil) 词元数 = %d, want 2", len(got))
	}
}

func TestSegmentCJK_MixedDailyChinese(t *testing.T) {
	got := SegmentCJK("今天天气很好", cjkDictSet)
	want := []string{"今天", "天气", "很", "好"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("SegmentCJK(今天天气很好) = %v, want %v", got, want)
	}
	if len(got) != 4 {
		t.Fatalf("SegmentCJK(今天天气很好) 词元数 = %d, want 4", len(got))
	}
}

func TestCJKDict_SizeAtLeast800(t *testing.T) {
	if len(cjkDict) < 800 {
		t.Fatalf("cjkDict 词条数 = %d, want >= 800", len(cjkDict))
	}
	if len(cjkDictSet) != len(cjkDict) {
		t.Fatalf("cjkDictSet 大小 = %d, want %d（词典内存在重复词条）", len(cjkDictSet), len(cjkDict))
	}
}
