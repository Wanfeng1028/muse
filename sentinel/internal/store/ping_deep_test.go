package store

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"io"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// ---- 测试用驱动 ----

type pingDriver struct {
	pingErr    error
	pingDelay  time.Duration
	pingCount  int64
	openErr    error
}

func (d *pingDriver) Open(name string) (driver.Conn, error) {
	if d.openErr != nil {
		return nil, d.openErr
	}
	return &pingConn{driver: d}, nil
}

type pingConn struct {
	driver *pingDriver
	closed int32
}

func (c *pingConn) Prepare(query string) (driver.Stmt, error) {
	return nil, errors.New("prepare not supported")
}

func (c *pingConn) Close() error {
	atomic.StoreInt32(&c.closed, 1)
	return nil
}

func (c *pingConn) Begin() (driver.Tx, error) {
	return nil, errors.New("begin not supported")
}

func (c *pingConn) Ping(ctx context.Context) error {
	atomic.AddInt64(&c.driver.pingCount, 1)
	if c.driver.pingDelay > 0 {
		select {
		case <-time.After(c.driver.pingDelay):
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	if c.driver.pingErr != nil {
		return c.driver.pingErr
	}
	return nil
}

var pingDriverNameCounter int64

func newTestDB(t *testing.T, d *pingDriver) *sql.DB {
	t.Helper()
	name := "ping-test-" + time.Now().Format("150405.000000000") + "-" + itoa(atomic.AddInt64(&pingDriverNameCounter, 1))
	sql.Register(name, d)
	db, err := sql.Open(name, "test")
	if err != nil {
		t.Fatalf("sql.Open 失败: %v", err)
	}
	return db
}

func itoa(n int64) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}

func newStore(t *testing.T, d *pingDriver) *Store {
	t.Helper()
	db := newTestDB(t, d)
	t.Cleanup(func() { _ = db.Close() })
	return &Store{db: db}
}

// ---- 用例 ----

func TestPing_Success(t *testing.T) {
	d := &pingDriver{}
	s := newStore(t, d)

	start := time.Now()
	err := s.Ping()
	elapsed := time.Since(start)

	if err != nil {
		t.Fatalf("Ping 期望返回 nil, 实际: %v", err)
	}
	if got := atomic.LoadInt64(&d.pingCount); got != 1 {
		t.Fatalf("Ping 期望底层探针调用 1 次, 实际: %d", got)
	}
	if elapsed > 2*time.Second {
		t.Fatalf("Ping 期望快速返回, 实际耗时: %v", elapsed)
	}
}

func TestPing_ProbeTimeout(t *testing.T) {
	timeoutErr := errors.New("probe timeout")
	d := &pingDriver{pingErr: timeoutErr}
	s := newStore(t, d)

	err := s.Ping()

	if err == nil {
		t.Fatalf("Ping 期望返回超时错误, 实际: nil")
	}
	if !errors.Is(err, timeoutErr) {
		t.Fatalf("Ping 期望错误可被 errors.Is 匹配到 %v, 实际: %v", timeoutErr, err)
	}
	if atomic.LoadInt64(&d.pingCount) != 1 {
		t.Fatalf("Ping 期望底层探针调用 1 次, 实际: %d", atomic.LoadInt64(&d.pingCount))
	}
}

func TestPing_NetworkError(t *testing.T) {
	netErr := errors.New("connection refused")
	d := &pingDriver{pingErr: netErr}
	s := newStore(t, d)

	err := s.Ping()

	if err == nil {
		t.Fatalf("Ping 期望返回网络错误, 实际: nil")
	}
	if !errors.Is(err, netErr) {
		t.Fatalf("Ping 期望错误可被 errors.Is 匹配到 %v, 实际: %v", netErr, err)
	}
	if err.Error() == "" {
		t.Fatalf("Ping 返回的错误信息不应为空")
	}
}

func TestPing_DBFailure(t *testing.T) {
	dbErr := errors.New("database is closed")
	d := &pingDriver{pingErr: dbErr}
	s := newStore(t, d)
	if err := s.db.Close(); err != nil {
		t.Fatalf("关闭 db 失败: %v", err)
	}

	err := s.Ping()

	if err == nil {
		t.Fatalf("Ping 期望返回数据库失败错误, 实际: nil")
	}
	if !strings.Contains(err.Error(), "closed") {
		t.Fatalf("Ping 期望错误包含 closed, 实际: %v", err)
	}
}

func TestPing_EmptyTarget(t *testing.T) {
	d := &pingDriver{}
	s := newStore(t, d)
	// 空目标: 底层 ping 行为不因目标为空而异常
	err := s.Ping()
	if err != nil {
		t.Fatalf("Ping 空目标期望 nil, 实际: %v", err)
	}
	if atomic.LoadInt64(&d.pingCount) < 1 {
		t.Fatalf("Ping 空目标期望至少调用 1 次底层探针, 实际: %d", atomic.LoadInt64(&d.pingCount))
	}
}

func TestPing_InvalidURL(t *testing.T) {
	openErr := errors.New("invalid dsn")
	d := &pingDriver{openErr: openErr}
	name := "ping-invalid-" + itoa(atomic.AddInt64(&pingDriverNameCounter, 1))
	sql.Register(name, d)
	db, err := sql.Open(name, "invalid://dsn")
	if err != nil {
		t.Fatalf("sql.Open 失败: %v", err)
	}
	defer db.Close()
	s := &Store{db: db}

	err = s.Ping()

	if err == nil {
		t.Fatalf("Ping 非法 URL 期望返回错误, 实际: nil")
	}
	if !errors.Is(err, openErr) {
		t.Fatalf("Ping 非法 URL 期望错误可被 errors.Is 匹配到 %v, 实际: %v", openErr, err)
	}
}

func TestPing_OverlongTarget(t *testing.T) {
	d := &pingDriver{}
	s := newStore(t, d)

	long := strings.Repeat("x", 1<<20)
	_ = long

	err := s.Ping()

	if err != nil {
		t.Fatalf("Ping 超长目标期望 nil, 实际: %v", err)
	}
	if atomic.LoadInt64(&d.pingCount) != 1 {
		t.Fatalf("Ping 超长目标期望底层探针调用 1 次, 实际: %d", atomic.LoadInt64(&d.pingCount))
	}
}

func TestPing_Concurrent(t *testing.T) {
	d := &pingDriver{}
	s := newStore(t, d)

	const goroutines = 32
	var wg sync.WaitGroup
	var errCount int64
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			if err := s.Ping(); err != nil {
				atomic.AddInt64(&errCount, 1)
			}
		}()
	}
	wg.Wait()

	if errCount != 0 {
		t.Fatalf("Ping 并发期望无错误, 实际错误数: %d", errCount)
	}
	if got := atomic.LoadInt64(&d.pingCount); got != goroutines {
		t.Fatalf("Ping 并发期望底层探针调用 %d 次, 实际: %d", goroutines, got)
	}
}

func TestPing_Idempotent(t *testing.T) {
	d := &pingDriver{}
	s := newStore(t, d)

	for i := 0; i < 5; i++ {
		if err := s.Ping(); err != nil {
			t.Fatalf("第 %d 次 Ping 期望 nil, 实际: %v", i+1, err)
		}
	}

	if got := atomic.LoadInt64(&d.pingCount); got != 5 {
		t.Fatalf("Ping 幂等期望底层探针调用 5 次, 实际: %d", got)
	}
}

func TestPing_TableDriven(t *testing.T) {
	cases := []struct {
		name    string
		pingErr error
		wantErr bool
	}{
		{name: "ok", pingErr: nil, wantErr: false},
		{name: "timeout", pingErr: errors.New("probe timeout"), wantErr: true},
		{name: "network", pingErr: errors.New("network unreachable"), wantErr: true},
		{name: "db down", pingErr: errors.New("db down"), wantErr: true},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			d := &pingDriver{pingErr: tc.pingErr}
			s := newStore(t, d)

			err := s.Ping()

			if tc.wantErr {
				if err == nil {
					t.Fatalf("期望返回错误, 实际: nil")
				}
				if !errors.Is(err, tc.pingErr) {
					t.Fatalf("期望错误匹配 %v, 实际: %v", tc.pingErr, err)
				}
			} else {
				if err != nil {
					t.Fatalf("期望返回 nil, 实际: %v", err)
				}
			}
			if atomic.LoadInt64(&d.pingCount) != 1 {
				t.Fatalf("期望底层探针调用 1 次, 实际: %d", atomic.LoadInt64(&d.pingCount))
			}
		})
	}
}

func TestPing_RepeatedFailureIsolation(t *testing.T) {
	failErr := errors.New("first probe failed")
	d := &pingDriver{pingErr: failErr}
	s := newStore(t, d)

	if err := s.Ping(); err == nil {
		t.Fatalf("第一次 Ping 期望错误, 实际: nil")
	}

	atomic.StoreInt64(&d.pingCount, 0)
	d.pingErr = nil

	if err := s.Ping(); err != nil {
		t.Fatalf("恢复后 Ping 期望 nil, 实际: %v", err)
	}
	if atomic.LoadInt64(&d.pingCount) != 1 {
		t.Fatalf("恢复后 Ping 期望底层探针调用 1 次, 实际: %d", atomic.LoadInt64(&d.pingCount))
	}
}

var _ io.Closer = (*pingConn)(nil)