package qr

import (
	"bytes"
	"sync"
	"testing"
)

// errWriter 是一个总是在写入时返回错误的 io.Writer 实现。
type errWriterDeep2 struct{}

func (errWriterDeep2) Write(p []byte) (int, error) {
	return 0, errWriteDeep2
}

var errWriteDeep2 = &writeErrorDeep2{}

type writeErrorDeep2 struct{}

func (e *writeErrorDeep2) Error() string { return "deep2: forced write error" }

// pngMagic 是 PNG 文件的固定魔数头。
var pngMagicDeep2 = []byte{0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A}

func TestPNGMagicHeaderDeep2(t *testing.T) {
	var buf bytes.Buffer
	if err := PNG(&buf, "https://example.com/hello", 128); err != nil {
		t.Fatalf("PNG 返回错误: %v", err)
	}
	out := buf.Bytes()
	if len(out) < len(pngMagicDeep2) {
		t.Fatalf("输出字节数 %d 小于 PNG 魔数长度 %d", len(out), len(pngMagicDeep2))
	}
	if !bytes.HasPrefix(out, pngMagicDeep2) {
		t.Fatalf("输出未以 PNG 魔数开头, 实际前 %d 字节: %v", len(pngMagicDeep2), out[:len(pngMagicDeep2)])
	}
}

func TestPNGDeterministicDeep2(t *testing.T) {
	content := "deterministic-content-测试"
	size := 200

	var first bytes.Buffer
	if err := PNG(&first, content, size); err != nil {
		t.Fatalf("第一次 PNG 返回错误: %v", err)
	}

	var second bytes.Buffer
	if err := PNG(&second, content, size); err != nil {
		t.Fatalf("第二次 PNG 返回错误: %v", err)
	}

	if !bytes.Equal(first.Bytes(), second.Bytes()) {
		t.Fatalf("相同 content+size 两次输出不一致: len1=%d len2=%d", first.Len(), second.Len())
	}
}

func TestPNGDifferentContentDeep2(t *testing.T) {
	size := 200

	var bufA bytes.Buffer
	if err := PNG(&bufA, "content-aaaa", size); err != nil {
		t.Fatalf("PNG(content-aaaa) 返回错误: %v", err)
	}

	var bufB bytes.Buffer
	if err := PNG(&bufB, "content-bbbb", size); err != nil {
		t.Fatalf("PNG(content-bbbb) 返回错误: %v", err)
	}

	if bytes.Equal(bufA.Bytes(), bufB.Bytes()) {
		t.Fatalf("不同 content 产生了相同的输出, 长度均为 %d", bufA.Len())
	}
}

func TestPNGSizeMonotonicDeep2(t *testing.T) {
	content := "https://example.com/size-test"

	var small bytes.Buffer
	if err := PNG(&small, content, 128); err != nil {
		t.Fatalf("PNG size=128 返回错误: %v", err)
	}

	var large bytes.Buffer
	if err := PNG(&large, content, 256); err != nil {
		t.Fatalf("PNG size=256 返回错误: %v", err)
	}

	if small.Len() == 0 || large.Len() == 0 {
		t.Fatalf("输出为空: small=%d large=%d", small.Len(), large.Len())
	}

	if large.Len() <= small.Len() {
		t.Fatalf("size 增大未使输出字节数增加: size=64 -> %d 字节, size=256 -> %d 字节", small.Len(), large.Len())
	}
}

func TestPNGURLWithChinesePathDeep2(t *testing.T) {
	content := "https://example.com/路径/中文页面?query=值&flag=1"
	size := 256

	var buf bytes.Buffer
	if err := PNG(&buf, content, size); err != nil {
		t.Fatalf("PNG 含中文路径 URL 返回错误: %v", err)
	}

	out := buf.Bytes()
	if len(out) == 0 {
		t.Fatalf("含中文路径 URL 的输出为空")
	}
	if !bytes.HasPrefix(out, pngMagicDeep2) {
		t.Fatalf("含中文路径 URL 输出未以 PNG 魔数开头")
	}

	var again bytes.Buffer
	if err := PNG(&again, content, size); err != nil {
		t.Fatalf("第二次 PNG 含中文路径 URL 返回错误: %v", err)
	}
	if !bytes.Equal(out, again.Bytes()) {
		t.Fatalf("含中文路径 URL 两次输出不一致: len1=%d len2=%d", len(out), again.Len())
	}
}

func TestPNGEmptyContentDeep2(t *testing.T) {
	var buf bytes.Buffer
	err := PNG(&buf, "", 128)

	if err != nil {
		// 源码对空 content 报错: 断言返回了非 nil 错误且未写入有效 PNG。
		if buf.Len() > 0 && bytes.HasPrefix(buf.Bytes(), pngMagicDeep2) {
			t.Fatalf("空 content 返回错误但仍写入了合法 PNG: %v", err)
		}
		return
	}

	// 源码对空 content 不报错: 断言成功写出 PNG。
	out := buf.Bytes()
	if len(out) < len(pngMagicDeep2) {
		t.Fatalf("空 content 成功但输出字节数 %d 小于 PNG 魔数长度", len(out))
	}
	if !bytes.HasPrefix(out, pngMagicDeep2) {
		t.Fatalf("空 content 成功但输出未以 PNG 魔数开头")
	}
}

func TestPNGErrorWriterDeep2(t *testing.T) {
	err := PNG(errWriterDeep2{}, "https://example.com/error", 128)
	if err == nil {
		t.Fatalf("错误 writer 应返回非 nil 错误, 实际返回 nil")
	}
}

func TestPNGConcurrentDeep2(t *testing.T) {
	const goroutines = 10
	content := "https://example.com/concurrent-并发"
	size := 200

	var reference bytes.Buffer
	if err := PNG(&reference, content, size); err != nil {
		t.Fatalf("基准 PNG 返回错误: %v", err)
	}
	expected := reference.Bytes()

	results := make([][]byte, goroutines)
	errs := make([]error, goroutines)

	var wg sync.WaitGroup
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func(idx int) {
			defer wg.Done()
			var buf bytes.Buffer
			errs[idx] = PNG(&buf, content, size)
			results[idx] = buf.Bytes()
		}(i)
	}
	wg.Wait()

	for i := 0; i < goroutines; i++ {
		if errs[i] != nil {
			t.Fatalf("goroutine %d 返回错误: %v", i, errs[i])
		}
		if !bytes.Equal(results[i], expected) {
			t.Fatalf("goroutine %d 输出与基准不一致: len=%d 期望 len=%d", i, len(results[i]), len(expected))
		}
	}
}

func TestPNGSameContentDifferentSizesDeep2(t *testing.T) {
	content := "https://example.com/multi-size"

	sizes := []int{128, 256, 512}
	outputs := make([][]byte, len(sizes))

	for i, s := range sizes {
		var buf bytes.Buffer
		if err := PNG(&buf, content, s); err != nil {
			t.Fatalf("PNG size=%d 返回错误: %v", s, err)
		}
		if buf.Len() == 0 {
			t.Fatalf("PNG size=%d 输出为空", s)
		}
		if !bytes.HasPrefix(buf.Bytes(), pngMagicDeep2) {
			t.Fatalf("PNG size=%d 输出未以 PNG 魔数开头", s)
		}
		outputs[i] = buf.Bytes()
	}

	for i := 1; i < len(outputs); i++ {
		if len(outputs[i]) <= len(outputs[i-1]) {
			t.Fatalf("size %d -> %d 字节数未增加: %d <= %d", sizes[i-1], sizes[i], len(outputs[i]), len(outputs[i-1]))
		}
	}
}
