package model

import "time"

// Link 表示一条短链记录。
type Link struct {
	ID           int64      // 主键
	Slug         string     // 短链标识，全局唯一
	URL          string     // 目标长链接
	Title        string     // 备注标题
	Clicks       int64      // 累计点击数
	Enabled      bool       // 是否启用
	ExpiresAt    *time.Time // 过期时间，nil 表示永不过期
	MaxVisits    *int64     // 限次访问，nil 表示不限
	Burn         bool       // 阅后即焚开关
	PasswordHash *string    // 密码的 bcrypt 哈希，nil 表示未设置密码
	BurnedAt     *time.Time // 阅后即焚销毁时间（UTC），nil 表示未销毁

	CreatedAt time.Time // 创建时间（UTC）

	UpdatedAt time.Time // 更新时间（UTC）
}

// Visit 表示一次访问记录。
type Visit struct {
	ID      int64     // 主键
	LinkID  int64     // 关联的短链 ID
	TS      time.Time // 访问时间（UTC）
	IPHash  string    // 客户端 IP 的哈希值（不存明文）
	UA      string    // User-Agent
	Referer string    // Referer
}

// DailyStat 表示某一天的点击统计。
type DailyStat struct {
	Date   string // 日期，格式 YYYY-MM-DD（UTC）
	Clicks int64  // 当天点击次数
}

// NamedStat 是通用的「名称-点击量」统计结构，用于 TopLinks / TopReferers。
type NamedStat struct {
	Name   string // 名称（slug / referer 等）
	Clicks int64  // 点击次数
}
