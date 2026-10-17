package push

import (
	"fmt"
	"os"
	"path/filepath"
	"syscall"
)

// AcquireSchedulerLock 用 syscall.Flock 对 dir/scheduler.lock 加 LOCK_EX|LOCK_NB。
// 拿不到锁时返回明确错误，调用方应放弃启动调度循环。
// 返回的 release 函数释放文件锁并关闭文件句柄，可安全重复调用。
func AcquireSchedulerLock(dir string) (release func(), err error) {
	if dir == "" {
		return nil, fmt.Errorf("push: scheduler lock dir is empty")
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("push: create scheduler lock dir %q: %w", dir, err)
	}
	lockPath := filepath.Join(dir, "scheduler.lock")
	f, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0o644)
	if err != nil {
		return nil, fmt.Errorf("push: open scheduler lock %q: %w", lockPath, err)
	}
	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		f.Close()
		return nil, fmt.Errorf("push: another scheduler instance holds lock %q: %w", lockPath, err)
	}
	released := false
	release = func() {
		if released {
			return
		}
		released = true
		if err := syscall.Flock(int(f.Fd()), syscall.LOCK_UN); err != nil {
			f.Close()
			return
		}
		f.Close()
	}
	return release, nil
}