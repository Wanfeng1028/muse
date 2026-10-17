package notify

import (
	"context"
	"errors"
	"testing"
)

type fakeSender struct {
	name    string
	sendErr error
	calls   int
	lastMsg Message
}

func (f *fakeSender) Name() string { return f.name }

func (f *fakeSender) Send(ctx context.Context, msg Message) error {
	f.calls++
	f.lastMsg = msg
	if f.sendErr != nil {
		return f.sendErr
	}
	return nil
}

func TestSenderNameReturnsConfiguredName(t *testing.T) {
	cases := []struct {
		name     string
		confName string
	}{
		{name: "普通名称", confName: "wechat"},
		{name: "空名称", confName: ""},
		{name: "含空格名称", confName: "ding talk"},
		{name: "中文名称", confName: "企业微信"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s := &fakeSender{name: tc.confName}
			got := s.Name()
			if got != tc.confName {
				t.Fatalf("Name() = %q, want %q", got, tc.confName)
			}
			if len(got) != len(tc.confName) {
				t.Fatalf("Name() 长度 = %d, want %d", len(got), len(tc.confName))
			}
		})
	}
}

func TestSenderSendSuccess(t *testing.T) {
	s := &fakeSender{name: "wechat"}
	msg := Message{Subject: "标题", TextBody: "正文"}
	err := s.Send(context.Background(), msg)
	if err != nil {
		t.Fatalf("Send() 返回错误 = %v, want nil", err)
	}
	if s.calls != 1 {
		t.Fatalf("Send() 调用次数 = %d, want 1", s.calls)
	}
	if s.lastMsg.Subject != msg.Subject || s.lastMsg.TextBody != msg.TextBody {
		t.Fatalf("Send() 收到消息 = %+v, want %+v", s.lastMsg, msg)
	}
}

func TestSenderSendPropagatesAuthError(t *testing.T) {
	s := &fakeSender{name: "wechat", sendErr: ErrAuth}
	err := s.Send(context.Background(), Message{Subject: "t", TextBody: "b"})
	if !errors.Is(err, ErrAuth) {
		t.Fatalf("Send() 返回错误 = %v, want ErrAuth", err)
	}
	if errors.Is(err, ErrConn) {
		t.Fatalf("Send() 返回错误不应是 ErrConn, got %v", err)
	}
	if s.calls != 1 {
		t.Fatalf("Send() 调用次数 = %d, want 1", s.calls)
	}
}

func TestSenderSendPropagatesConnError(t *testing.T) {
	s := &fakeSender{name: "wechat", sendErr: ErrConn}
	err := s.Send(context.Background(), Message{Subject: "t", TextBody: "b"})
	if !errors.Is(err, ErrConn) {
		t.Fatalf("Send() 返回错误 = %v, want ErrConn", err)
	}
	if errors.Is(err, ErrAuth) {
		t.Fatalf("Send() 返回错误不应是 ErrAuth, got %v", err)
	}
}

func TestSenderSendEmptyMessage(t *testing.T) {
	s := &fakeSender{name: "wechat"}
	err := s.Send(context.Background(), Message{})
	if err != nil {
		t.Fatalf("Send() 空消息返回错误 = %v, want nil", err)
	}
	if s.lastMsg.Subject != "" {
		t.Fatalf("Send() 空消息 Subject = %q, want 空", s.lastMsg.Subject)
	}
	if s.lastMsg.TextBody != "" {
		t.Fatalf("Send() 空消息 TextBody = %q, want 空", s.lastMsg.TextBody)
	}
}

func TestSenderSendCancelledContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	s := &fakeSender{name: "wechat"}
	err := s.Send(ctx, Message{Subject: "t", TextBody: "b"})
	if err != nil {
		t.Fatalf("Send() 取消上下文返回错误 = %v, want nil", err)
	}
	if s.calls != 1 {
		t.Fatalf("Send() 调用次数 = %d, want 1", s.calls)
	}
}

func TestSenderSendMultipleCallsAccumulate(t *testing.T) {
	s := &fakeSender{name: "wechat"}
	for i := 0; i < 5; i++ {
		if err := s.Send(context.Background(), Message{Subject: "t", TextBody: "b"}); err != nil {
			t.Fatalf("第 %d 次 Send() 返回错误 = %v, want nil", i, err)
		}
	}
	if s.calls != 5 {
		t.Fatalf("Send() 调用次数 = %d, want 5", s.calls)
	}
	if s.lastMsg.Subject != "t" {
		t.Fatalf("Send() 最后一次 Subject = %q, want %q", s.lastMsg.Subject, "t")
	}
}

func TestSenderErrorIdentity(t *testing.T) {
	if ErrAuth == nil {
		t.Fatal("ErrAuth 不应为 nil")
	}
	if ErrConn == nil {
		t.Fatal("ErrConn 不应为 nil")
	}
	if ErrAuth == ErrConn {
		t.Fatal("ErrAuth 与 ErrConn 不应是同一个错误实例")
	}
	if ErrAuth.Error() != "notify: auth failed" {
		t.Fatalf("ErrAuth.Error() = %q, want %q", ErrAuth.Error(), "notify: auth failed")
	}
	if ErrConn.Error() != "notify: connection failed" {
		t.Fatalf("ErrConn.Error() = %q, want %q", ErrConn.Error(), "notify: connection failed")
	}
}

func TestSenderImplementsInterface(t *testing.T) {
	var _ Sender = (*fakeSender)(nil)
	s := &fakeSender{name: "wechat"}
	var iface Sender = s
	if iface.Name() != "wechat" {
		t.Fatalf("接口调用 Name() = %q, want %q", iface.Name(), "wechat")
	}
	if err := iface.Send(context.Background(), Message{Subject: "t", TextBody: "b"}); err != nil {
		t.Fatalf("接口调用 Send() 返回错误 = %v, want nil", err)
	}
}

func TestSenderSendWrappedErrorNotMatched(t *testing.T) {
	other := errors.New("notify: other failure")
	s := &fakeSender{name: "wechat", sendErr: other}
	err := s.Send(context.Background(), Message{Subject: "t", TextBody: "b"})
	if errors.Is(err, ErrAuth) {
		t.Fatalf("Send() 返回错误不应匹配 ErrAuth, got %v", err)
	}
	if errors.Is(err, ErrConn) {
		t.Fatalf("Send() 返回错误不应匹配 ErrConn, got %v", err)
	}
	if err == nil || err.Error() != "notify: other failure" {
		t.Fatalf("Send() 返回错误 = %v, want %q", err, "notify: other failure")
	}
}

func TestSenderSendNilErrorWhenNoFailure(t *testing.T) {
	s := &fakeSender{name: "wechat"}
	err := s.Send(context.Background(), Message{Subject: "告警", TextBody: "磁盘使用率 95%"})
	if err != nil {
		t.Fatalf("Send() 返回错误 = %v, want nil", err)
	}
	if s.lastMsg.Subject != "告警" {
		t.Fatalf("Send() 记录 Subject = %q, want %q", s.lastMsg.Subject, "告警")
	}
	if s.lastMsg.TextBody != "磁盘使用率 95%" {
		t.Fatalf("Send() 记录 TextBody = %q, want %q", s.lastMsg.TextBody, "磁盘使用率 95%")
	}
}
