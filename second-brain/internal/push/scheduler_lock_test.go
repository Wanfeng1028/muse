package push

import (
	"testing"
)

func TestAcquireSchedulerLockSecondInstanceFails(t *testing.T) {
	dir := t.TempDir()

	release1, err := AcquireSchedulerLock(dir)
	if err != nil {
		t.Fatalf("first AcquireSchedulerLock failed: %v", err)
	}
	if release1 == nil {
		t.Fatalf("first AcquireSchedulerLock returned nil release")
	}

	release2, err2 := AcquireSchedulerLock(dir)
	if err2 == nil {
		if release2 != nil {
			release2()
		}
		release1()
		t.Fatalf("second AcquireSchedulerLock succeeded, want error")
	}
	if release2 != nil {
		t.Fatalf("second AcquireSchedulerLock returned non-nil release on error")
	}

	release1()
}

func TestAcquireSchedulerLockReleaseAllowsReacquire(t *testing.T) {
	dir := t.TempDir()

	release1, err := AcquireSchedulerLock(dir)
	if err != nil {
		t.Fatalf("first AcquireSchedulerLock failed: %v", err)
	}

	release1()
	release1()

	release2, err := AcquireSchedulerLock(dir)
	if err != nil {
		t.Fatalf("reacquire after release failed: %v", err)
	}
	if release2 == nil {
		t.Fatalf("reacquire returned nil release")
	}
	release2()
}

func TestSchedulerLockReleaseAndReacquire(t *testing.T) {
	dir := t.TempDir()

	release, err := AcquireSchedulerLock(dir)
	if err != nil {
		t.Fatalf("AcquireSchedulerLock failed: %v", err)
	}
	if release == nil {
		t.Fatalf("AcquireSchedulerLock returned nil release")
	}

	// 持有锁期间第二次获取必须失败
	if _, err2 := AcquireSchedulerLock(dir); err2 == nil {
		t.Fatalf("second AcquireSchedulerLock while locked: want error, got nil")
	}

	// 释放后可以重新获取
	release()
	release2, err2 := AcquireSchedulerLock(dir)
	if err2 != nil {
		t.Fatalf("reacquire after release failed: %v", err2)
	}
	if release2 == nil {
		t.Fatalf("reacquire after release returned nil release")
	}
	release2()
}
