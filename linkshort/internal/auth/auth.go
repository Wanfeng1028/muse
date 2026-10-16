// Package auth 提供短链访问密码的校验与哈希能力。
// 密码只以 bcrypt 哈希形式落库，绝不保存明文。
package auth

import (
	"errors"
	"fmt"

	"golang.org/x/crypto/bcrypt"
)

// BcryptCost 是 bcrypt 哈希强度，测试时可调低以加速。
var BcryptCost = bcrypt.DefaultCost

// MaxPasswordRunes 是密码允许的最大字符数（按 rune 计）。
const MaxPasswordRunes = 128

// ValidPasswordPolicy 校验密码是否符合策略：非空且不超过 MaxPasswordRunes 个字符。
func ValidPasswordPolicy(pw string) error {
	if pw == "" {
		return errors.New("密码不能为空")
	}
	if len([]rune(pw)) > MaxPasswordRunes {
		return errors.New("密码过长，最多 128 个字符")
	}
	return nil
}

// HashPassword 校验密码策略后返回其 bcrypt 哈希。
func HashPassword(pw string) (string, error) {
	if err := ValidPasswordPolicy(pw); err != nil {
		return "", err
	}
	h, err := bcrypt.GenerateFromPassword([]byte(pw), BcryptCost)
	if err != nil {
		return "", fmt.Errorf("hash password: %w", err)
	}
	return string(h), nil
}

// CheckPassword 比对明文密码与 bcrypt 哈希，匹配返回 true。
// hash 为空时直接返回 false。
func CheckPassword(hash, pw string) bool {
	if hash == "" {
		return false
	}
	return bcrypt.CompareHashAndPassword([]byte(hash), []byte(pw)) == nil
}
