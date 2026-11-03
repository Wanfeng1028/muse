package qr

import (
	"bytes"
	"errors"
	"io"
	"testing"
)

// partialErrWriterDeep3 写入部分字节后返回错误。
type partialErrWriterDeep3 struct {
	limit int
	wrote int
}

func (p *partialErrWriterDeep3) Write(b []byte) (int, error) {
	remaining := p.limit - p.wrote
	if remaining <= 0 {
		return 0, errors.New("deep3: partial writer exhausted")
	}
	if len(b) <= remaining {
		p.wrote += len(b)
		return len(b), nil
	}
	p.wrote += remaining
	return remaining, errors.New("deep3: partial write error")
}

// shortWriterDeep3 永远只接受 1 字节且报告成功。
type shortWriterDeep3 struct {
	total int
}

func (s *shortWriterDeep3) Write(b []byte) (int, error) {
	if len(b) == 0 {
		return 0, nil
	}
	s.total++
	return 1, nil
}

func TestPNGSizeBoundaryLowerDeep3(t *testing.T) {
	var buf bytes.Buffer
	err := PNG(&buf, "https://example.com/lower", 128)
	if err != nil {
		t.Fatalf("size=128 应合法, 实际错误: %v", err)
	}
	if buf.Len() == 0 {
		t.Fatalf("size=128 输出为空")
	}
}

func TestPNGSizeBoundaryUpperDeep3(t *testing.T) {
	var buf bytes.Buffer
	err := PNG(&buf, "https://example.com/upper", 1024)
	if err != nil {
		t.Fatalf("size=1024 应合法, 实际错误: %v", err)
	}
	if buf.Len() == 0 {
		t.Fatalf("size=1024 输出为空")
	}
}

func TestPNGSizeBelowLowerDeep3(t *testing.T) {
	cases := []int{-1, 0, 1, 127}
	for _, size := range cases {
		var buf bytes.Buffer
		err := PNG(&buf, "https://example.com/toolow", size)
		if !errors.Is(err, ErrInvalidSize) {
			t.Fatalf("size=%d 期望 ErrInvalidSize, 实际: %v", size, err)
		}
		if buf.Len() != 0 {
			t.Fatalf("size=%d 非法但写入了 %d 字节", size, buf.Len())
		}
	}
}

func TestPNGSizeAboveUpperDeep3(t *testing.T) {
	cases := []int{1025, 2000, 1 << 20}
	for _, size := range cases {
		var buf bytes.Buffer
		err := PNG(&buf, "https://example.com/toohigh", size)
		if !errors.Is(err, ErrInvalidSize) {
			t.Fatalf("size=%d 期望 ErrInvalidSize, 实际: %v", size, err)
		}
		if buf.Len() != 0 {
			t.Fatalf("size=%d 非法但写入了 %d 字节", size, buf.Len())
		}
	}
}

func TestPNGInvalidSizeDoesNotTouchWriterDeep3(t *testing.T) {
	w := &countingWriterDeep3{}
	err := PNG(w, "anything", 1024+1)
	if !errors.Is(err, ErrInvalidSize) {
		t.Fatalf("期望 ErrInvalidSize, 实际: %v", err)
	}
	if w.calls != 0 {
		t.Fatalf("非法 size 不应调用 Write, 实际调用 %d 次", w.calls)
	}
}

// countingWriterDeep3 统计 Write 调用次数。
type countingWriterDeep3 struct {
	calls int
}

func (c *countingWriterDeep3) Write(b []byte) (int, error) {
	c.calls++
	return len(b), nil
}

func TestPNGPartialWriteErrorDeep3(t *testing.T) {
	w := &partialErrWriterDeep3{limit: 16}
	err := PNG(w, "https://example.com/partial", 128)
	if err == nil {
		t.Fatalf("部分写入后错误应被传播, 实际 nil")
	}
}

func TestPNGShortWriterSuccessDeep3(t *testing.T) {
	w := &shortWriterDeep3{}
	err := PNG(w, "https://example.com/short", 128)
	if err != nil {
		t.Fatalf("短写 writer 未返回错误时 PNG 不应报错, 实际: %v", err)
	}
	if w.total == 0 {
		t.Fatalf("短写 writer 从未被调用")
	}
}

func TestPNGVeryLongContentDeep3(t *testing.T) {
	var content bytes.Buffer
	for content.Len() < 2000 {
		content.WriteString("https://example.com/very/long/path/segment/")
	}
	var buf bytes.Buffer
	err := PNG(&buf, content.String(), 256)
	if err == nil {
		if buf.Len() == 0 {
			t.Fatalf("超长 content 成功但输出为空")
		}
		return
	}
	// 若 go-qrcode 因容量拒绝, 输出应保持为空。
	if buf.Len() != 0 {
		t.Fatalf("超长 content 报错却写入了 %d 字节", buf.Len())
	}
}

func TestPNGWhitespaceContentDeep3(t *testing.T) {
	cases := []string{" ", "\t", "\n", "   \n\t  "}
	for i, c := range cases {
		var buf bytes.Buffer
		err := PNG(&buf, c, 128)
		if err == nil && buf.Len() == 0 {
			t.Fatalf("case %d 成功但输出为空", i)
		}
	}
}

func TestPNGNilWriterPanicsOrErrorsDeep3(t *testing.T) {
	defer func() {
		_ = recover()
	}()
	err := PNG(nil, "https://example.com/nil-writer", 128)
	if err == nil {
		t.Fatalf("nil writer 应返回错误或 panic 被恢复, 实际 nil 且未 panic")
	}
}

func TestPNGErrInvalidSizeMessageDeep3(t *testing.T) {
	if ErrInvalidSize == nil {
		t.Fatalf("ErrInvalidSize 不应为 nil")
	}
	msg := ErrInvalidSize.Error()
	if msg == "" {
		t.Fatalf("ErrInvalidSize.Error() 为空字符串")
	}
}

func TestPNGErrInvalidSizeIsSentinelDeep3(t *testing.T) {
	var buf bytes.Buffer
	err := PNG(&buf, "x", 0)
	if err == nil {
		t.Fatalf("size=0 应返回错误")
	}
	if !errors.Is(err, ErrInvalidSize) {
		t.Fatalf("返回错误应等于 ErrInvalidSize, 实际: %v", err)
	}
}

func TestPNGWriterOnlyCalledOnceDeep3(t *testing.T) {
	w := &countingWriterDeep3{}
	if err := PNG(w, "https://example.com/once", 128); err != nil {
		t.Fatalf("PNG 返回错误: %v", err)
	}
	if w.calls != 1 {
		t.Fatalf("期望 Write 调用 1 次, 实际 %d 次", w.calls)
	}
}

func TestPNGDiscardWriterDeep3(t *testing.T) {
	err := PNG(io.Discard, "https://example.com/discard", 256)
	if err != nil {
		t.Fatalf("io.Discard 作为 writer 不应报错, 实际: %v", err)
	}
}
