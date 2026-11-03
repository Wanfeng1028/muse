package store

import "strings"

// DefaultUser 默认用户：未声明身份时所有复习数据归属该用户。
const DefaultUser = "local"

// NormalizeUser 归一化用户标识：去首尾空格、转小写；空字符串回退为 DefaultUser；
// 超过 64 个字符截断。单机多用户简化方案：无注册、无鉴权，调用方自觉声明身份。
func NormalizeUser(user string) string {
	user = strings.TrimSpace(user)
	user = strings.ToLower(user)
	if user == "" {
		return DefaultUser
	}
	if len(user) > 64 {
		user = user[:64]
	}
	return user
}
