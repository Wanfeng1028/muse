package qr

import (
	"errors"
	"io"

	qrcode "github.com/skip2/go-qrcode"
)

// ErrInvalidSize 表示请求的图片尺寸超出允许范围。
var ErrInvalidSize = errors.New("qr size must be between 128 and 1024")

// PNG 将 content 生成 PNG 二维码写入 w，size 为边长像素。
// size 必须在 128..1024 之间，否则返回 ErrInvalidSize。
func PNG(w io.Writer, content string, size int) error {
	if size < 128 || size > 1024 {
		return ErrInvalidSize
	}
	code, err := qrcode.New(content, qrcode.Medium)
	if err != nil {
		return err
	}
	png, err := code.PNG(size)
	if err != nil {
		return err
	}
	if _, err := w.Write(png); err != nil {
		return err
	}
	return nil
}
