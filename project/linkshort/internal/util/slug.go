package util

import (
	"crypto/rand"
	"errors"
	"regexp"
)

// base62Chars 使用完整 base62 字符集（0-9a-zA-Z）。
// 说明：未剔除易混淆字符（0/O、1/l/I 等），因为在 URL 短链场景下
// 大写与小写被视为不同 slug，剔除会显著降低 6 位空间下的碰撞概率优势；
// 若未来有需求可在此处替换为无歧义字符集（如 base58）。
const base62Chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

// slugPattern 校验 slug 的合法格式：1-64 位，仅允许字母数字、下划线、连字符。
var slugPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{1,64}$`)

// ErrInvalidSlug 表示 slug 格式不合法。
var ErrInvalidSlug = errors.New("invalid slug format")

// Generate 使用 crypto/rand 生成 n 位 base62 随机 slug。
// n <= 0 时返回空字符串。
func Generate(n int) (string, error) {
	if n <= 0 {
		return "", nil
	}
	out := make([]byte, n)
	// 一次性读取 n 个随机字节，再用取模映射到 base62 字符。
	buf := make([]byte, n)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	for i, b := range buf {
		out[i] = base62Chars[int(b)%len(base62Chars)]
	}
	return string(out), nil
}

// IsValidSlug 校验 slug 是否满足 ^[A-Za-z0-9_-]{1,64}$。
func IsValidSlug(s string) bool {
	return slugPattern.MatchString(s)
}
