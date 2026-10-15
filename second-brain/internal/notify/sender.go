package notify

import (
	"context"
	"errors"
)

// Sender 是一个通知通道。
type Sender interface {
	// Name 返回通道名称，用于日志与展示。
	Name() string
	// Send 发送一条通知。
	Send(ctx context.Context, msg Message) error
}

// ErrAuth 表示认证失败。
var ErrAuth = errors.New("notify: auth failed")

// ErrConn 表示连接失败。
var ErrConn = errors.New("notify: connection failed")
