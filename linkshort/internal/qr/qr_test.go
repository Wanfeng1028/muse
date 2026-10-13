package qr

import (
	"bytes"
	"errors"
	"testing"
)

// TestPNG_输出PNG魔数 验证输出以 PNG 魔数开头
func TestPNG_输出PNG魔数(t *testing.T) {
	var buf bytes.Buffer
	if err := PNG(&buf, "https://example.com/abc", 256); err != nil {
		t.Fatalf("PNG 返回错误: %v", err)
	}
	out := buf.Bytes()
	pngMagic := []byte{0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A}
	if len(out) < len(pngMagic) {
		t.Fatalf("PNG 输出长度不足 8 字节: 实际 %d 字节", len(out))
	}
	if !bytes.Equal(out[:8], pngMagic) {
		t.Errorf("PNG 前 8 字节不是 PNG 魔数: 实际 % x", out[:8])
	}
}

// TestPNG_非法尺寸 验证非法尺寸返回 ErrInvalidSize
func TestPNG_非法尺寸(t *testing.T) {
	cases := []int{0, -1, -100}
	for _, size := range cases {
		var buf bytes.Buffer
		err := PNG(&buf, "https://example.com/abc", size)
		if err == nil {
			t.Errorf("PNG(size=%d) 期望错误 ErrInvalidSize，实际 nil", size)
			continue
		}
		if !errors.Is(err, ErrInvalidSize) {
			t.Errorf("PNG(size=%d) 期望 ErrInvalidSize，实际 %v", size, err)
		}
	}
}
