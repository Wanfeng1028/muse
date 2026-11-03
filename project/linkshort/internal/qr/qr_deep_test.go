package qr

import (
	"bytes"
	"errors"
	"image/png"
	"strings"
	"sync"
	"testing"
)

func TestPNGSizeBoundaryLowest(t *testing.T) {
	var buf bytes.Buffer
	err := PNG(&buf, "https://example.com/abc", 128)
	if err != nil {
		t.Fatalf("size 128 should be valid, got err: %v", err)
	}
	if buf.Len() == 0 {
		t.Fatalf("expected non-empty png output")
	}
	img, err := png.Decode(bytes.NewReader(buf.Bytes()))
	if err != nil {
		t.Fatalf("output is not a valid png: %v", err)
	}
	b := img.Bounds()
	if b.Dx() != 128 || b.Dy() != 128 {
		t.Fatalf("expected 128x128 image, got %dx%d", b.Dx(), b.Dy())
	}
}

func TestPNGSizeBoundaryHighest(t *testing.T) {
	var buf bytes.Buffer
	err := PNG(&buf, "https://example.com/xyz", 1024)
	if err != nil {
		t.Fatalf("size 1024 should be valid, got err: %v", err)
	}
	img, err := png.Decode(bytes.NewReader(buf.Bytes()))
	if err != nil {
		t.Fatalf("output is not a valid png: %v", err)
	}
	b := img.Bounds()
	if b.Dx() != 1024 || b.Dy() != 1024 {
		t.Fatalf("expected 1024x1024 image, got %dx%d", b.Dx(), b.Dy())
	}
}

func TestPNGSizeJustBelowLowerBound(t *testing.T) {
	var buf bytes.Buffer
	err := PNG(&buf, "https://example.com/abc", 127)
	if !errors.Is(err, ErrInvalidSize) {
		t.Fatalf("expected ErrInvalidSize for 127, got: %v", err)
	}
	if buf.Len() != 0 {
		t.Fatalf("expected no bytes written on invalid size, got %d", buf.Len())
	}
}

func TestPNGSizeJustAboveUpperBound(t *testing.T) {
	var buf bytes.Buffer
	err := PNG(&buf, "https://example.com/abc", 1025)
	if !errors.Is(err, ErrInvalidSize) {
		t.Fatalf("expected ErrInvalidSize for 1025, got: %v", err)
	}
	if buf.Len() != 0 {
		t.Fatalf("expected no bytes written on invalid size, got %d", buf.Len())
	}
}

func TestPNGSizeZeroAndNegative(t *testing.T) {
	for _, size := range []int{0, -1, -128} {
		var buf bytes.Buffer
		err := PNG(&buf, "https://example.com/abc", size)
		if !errors.Is(err, ErrInvalidSize) {
			t.Fatalf("size %d: expected ErrInvalidSize, got: %v", size, err)
		}
		if buf.Len() != 0 {
			t.Fatalf("size %d: expected no bytes written, got %d", size, buf.Len())
		}
	}
}

func TestPNGContentTooLong(t *testing.T) {
	long := strings.Repeat("A", 8000)
	var buf bytes.Buffer
	err := PNG(&buf, long, 256)
	if err == nil {
		t.Fatalf("expected error for oversized content")
	}
	if errors.Is(err, ErrInvalidSize) {
		t.Fatalf("oversized content should not produce ErrInvalidSize")
	}
	if buf.Len() != 0 {
		t.Fatalf("expected no bytes written on encode failure, got %d", buf.Len())
	}
}

func TestPNGEmptyContent(t *testing.T) {
	// 注：底层 qrcode 库拒绝空内容，产品透传该错误；空内容不应生成二维码
	var buf bytes.Buffer
	err := PNG(&buf, "", 256)
	if err == nil {
		t.Fatalf("empty content should fail, got success with %d bytes", buf.Len())
	}
}

func TestPNGUnicodeContent(t *testing.T) {
	var buf bytes.Buffer
	err := PNG(&buf, "晚风 https://例子.中国/路径?q=值", 200)
	if err != nil {
		t.Fatalf("unicode content should encode, got err: %v", err)
	}
	if buf.Len() == 0 {
		t.Fatalf("expected non-empty png for unicode content")
	}
	img, err := png.Decode(bytes.NewReader(buf.Bytes()))
	if err != nil {
		t.Fatalf("output is not a valid png: %v", err)
	}
	if img.Bounds().Dy() != 200 {
		t.Fatalf("expected height 200, got %d", img.Bounds().Dy())
	}
}

type errWriter struct {
	calls int
}

func (e *errWriter) Write(p []byte) (int, error) {
	e.calls++
	return 0, errors.New("sink refused")
}

func TestPNGWriterError(t *testing.T) {
	w := &errWriter{}
	err := PNG(w, "https://example.com/abc", 300)
	if err == nil {
		t.Fatalf("expected writer error to propagate")
	}
	if !strings.Contains(err.Error(), "sink refused") {
		t.Fatalf("expected underlying writer error, got: %v", err)
	}
	if w.calls != 1 {
		t.Fatalf("expected exactly one write attempt, got %d", w.calls)
	}
}

func TestPNGSameContentDeterministic(t *testing.T) {
	var a, b bytes.Buffer
	if err := PNG(&a, "https://example.com/deterministic", 256); err != nil {
		t.Fatalf("first render failed: %v", err)
	}
	if err := PNG(&b, "https://example.com/deterministic", 256); err != nil {
		t.Fatalf("second render failed: %v", err)
	}
	if a.Len() == 0 || b.Len() == 0 {
		t.Fatalf("expected non-empty outputs")
	}
	if !bytes.Equal(a.Bytes(), b.Bytes()) {
		t.Fatalf("same content and size should render identical bytes")
	}
}

func TestPNGDifferentContentDiffers(t *testing.T) {
	var a, b bytes.Buffer
	if err := PNG(&a, "https://example.com/one", 256); err != nil {
		t.Fatalf("first render failed: %v", err)
	}
	if err := PNG(&b, "https://example.com/two", 256); err != nil {
		t.Fatalf("second render failed: %v", err)
	}
	if a.Len() == 0 || b.Len() == 0 {
		t.Fatalf("expected non-empty outputs")
	}
	if bytes.Equal(a.Bytes(), b.Bytes()) {
		t.Fatalf("different content should render different bytes")
	}
}

func TestPNGConcurrentRenders(t *testing.T) {
	const workers = 16
	contents := make([]string, workers)
	sizes := make([]int, workers)
	for i := 0; i < workers; i++ {
		contents[i] = "https://example.com/concurrent/" + string(rune('a'+i))
		sizes[i] = 128 + i*17
	}
	results := make([][]byte, workers)
	errs := make([]error, workers)
	var wg sync.WaitGroup
	wg.Add(workers)
	for i := 0; i < workers; i++ {
		go func(idx int) {
			defer wg.Done()
			var buf bytes.Buffer
			if err := PNG(&buf, contents[idx], sizes[idx]); err != nil {
				errs[idx] = err
				return
			}
			results[idx] = buf.Bytes()
		}(i)
	}
	wg.Wait()
	for i := 0; i < workers; i++ {
		if errs[i] != nil {
			t.Fatalf("worker %d failed: %v", i, errs[i])
		}
		if len(results[i]) == 0 {
			t.Fatalf("worker %d produced empty output", i)
		}
		img, err := png.Decode(bytes.NewReader(results[i]))
		if err != nil {
			t.Fatalf("worker %d produced invalid png: %v", i, err)
		}
		if img.Bounds().Dx() != sizes[i] {
			t.Fatalf("worker %d expected width %d, got %d", i, sizes[i], img.Bounds().Dx())
		}
	}
}
