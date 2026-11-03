package auth

import (
	"errors"
	"strings"
	"sync"
	"testing"

	"golang.org/x/crypto/bcrypt"
)

func TestValidPasswordPolicyBoundaries(t *testing.T) {
	cases := []struct {
		name    string
		pw      string
		wantErr bool
		errMsg  string
	}{
		{name: "empty", pw: "", wantErr: true, errMsg: "密码不能为空"},
		{name: "single_ascii", pw: "a", wantErr: false},
		{name: "exactly_128_ascii", pw: strings.Repeat("a", 128), wantErr: false},
		{name: "129_ascii", pw: strings.Repeat("a", 129), wantErr: true, errMsg: "密码过长，最多 128 个字符"},
		{name: "exactly_128_runes_cjk", pw: strings.Repeat("中", 128), wantErr: false},
		{name: "129_runes_cjk", pw: strings.Repeat("中", 129), wantErr: true, errMsg: "密码过长，最多 128 个字符"},
		{name: "mixed_runes_within_limit", pw: strings.Repeat("a中", 64), wantErr: false},
	}
	for _, c := range cases {
		c := c
		t.Run(c.name, func(t *testing.T) {
			err := ValidPasswordPolicy(c.pw)
			if c.wantErr {
				if err == nil {
					t.Fatalf("期望返回错误，实际为 nil")
				}
				if err.Error() != c.errMsg {
					t.Fatalf("错误文案不匹配，期望 %q，实际 %q", c.errMsg, err.Error())
				}
			} else {
				if err != nil {
					t.Fatalf("期望通过策略，实际返回错误 %v", err)
				}
			}
			if c.wantErr && c.pw == "" {
				if len([]rune(c.pw)) != 0 {
					t.Fatalf("空密码 rune 长度应为 0")
				}
			}
		})
	}
}

func TestHashPasswordProducesVerifiableBcryptHash(t *testing.T) {
	origCost := BcryptCost
	BcryptCost = bcrypt.MinCost
	defer func() { BcryptCost = origCost }()

	pw := "晚风的密码Abc123"
	hash, err := HashPassword(pw)
	if err != nil {
		t.Fatalf("HashPassword 返回错误: %v", err)
	}
	if hash == "" {
		t.Fatalf("哈希不应为空")
	}
	if hash == pw {
		t.Fatalf("哈希不应等于明文密码")
	}
	if !strings.HasPrefix(hash, "$2") {
		t.Fatalf("哈希应以 bcrypt 前缀 $2 开头，实际 %q", hash)
	}
	cost, err := bcrypt.Cost([]byte(hash))
	if err != nil {
		t.Fatalf("解析 bcrypt cost 失败: %v", err)
	}
	if cost != bcrypt.MinCost {
		t.Fatalf("哈希 cost 期望 %d，实际 %d", bcrypt.MinCost, cost)
	}
	if !CheckPassword(hash, pw) {
		t.Fatalf("正确明文应通过校验")
	}
	if CheckPassword(hash, pw+"x") {
		t.Fatalf("错误明文不应通过校验")
	}
}

func TestHashPasswordRejectsPolicyViolation(t *testing.T) {
	origCost := BcryptCost
	BcryptCost = bcrypt.MinCost
	defer func() { BcryptCost = origCost }()

	hash, err := HashPassword("")
	if err == nil {
		t.Fatalf("空密码应返回错误")
	}
	if hash != "" {
		t.Fatalf("策略失败时哈希应为空字符串，实际 %q", hash)
	}
	if err.Error() != "密码不能为空" {
		t.Fatalf("错误文案不匹配，实际 %q", err.Error())
	}

	tooLong := strings.Repeat("中", 129)
	hash2, err2 := HashPassword(tooLong)
	if err2 == nil {
		t.Fatalf("超长密码应返回错误")
	}
	if hash2 != "" {
		t.Fatalf("策略失败时哈希应为空字符串，实际 %q", hash2)
	}
	if err2.Error() != "密码过长，最多 128 个字符" {
		t.Fatalf("错误文案不匹配，实际 %q", err2.Error())
	}
}

func TestCheckPasswordEmptyHashAlwaysFalse(t *testing.T) {
	if CheckPassword("", "anything") {
		t.Fatalf("空哈希必须返回 false")
	}
	if CheckPassword("", "") {
		t.Fatalf("空哈希配空密码也必须返回 false")
	}
}

func TestCheckPasswordRejectsTamperedHash(t *testing.T) {
	origCost := BcryptCost
	BcryptCost = bcrypt.MinCost
	defer func() { BcryptCost = origCost }()

	pw := "tamper-check-密码"
	hash, err := HashPassword(pw)
	if err != nil {
		t.Fatalf("HashPassword 返回错误: %v", err)
	}
	if !CheckPassword(hash, pw) {
		t.Fatalf("原始哈希应通过校验")
	}

	tampered := hash[:len(hash)-1] + "x"
	if tampered == hash {
		tampered = hash[:len(hash)-1] + "y"
	}
	if CheckPassword(tampered, pw) {
		t.Fatalf("被篡改的哈希不应通过校验")
	}

	corrupted := []byte(hash)
	corrupted[0] = 'X'
	if CheckPassword(string(corrupted), pw) {
		t.Fatalf("被破坏的哈希不应通过校验")
	}
}

func TestHashPasswordIsSaltedPerCall(t *testing.T) {
	origCost := BcryptCost
	BcryptCost = bcrypt.MinCost
	defer func() { BcryptCost = origCost }()

	pw := "same-password-同一个密码"
	h1, err := HashPassword(pw)
	if err != nil {
		t.Fatalf("第一次 HashPassword 出错: %v", err)
	}
	h2, err := HashPassword(pw)
	if err != nil {
		t.Fatalf("第二次 HashPassword 出错: %v", err)
	}
	if h1 == h2 {
		t.Fatalf("bcrypt 每次应加随机盐，两次哈希不应相同")
	}
	if !CheckPassword(h1, pw) || !CheckPassword(h2, pw) {
		t.Fatalf("两个哈希都应能校验原始密码")
	}
}

func TestHashPasswordConcurrentRaceSafe(t *testing.T) {
	origCost := BcryptCost
	BcryptCost = bcrypt.MinCost
	defer func() { BcryptCost = origCost }()

	const workers = 16
	pw := "并发密码-race"

	var wg sync.WaitGroup
	hashes := make([]string, workers)
	errs := make([]error, workers)
	wg.Add(workers)
	for i := 0; i < workers; i++ {
		go func(idx int) {
			defer wg.Done()
			h, err := HashPassword(pw)
			hashes[idx] = h
			errs[idx] = err
		}(i)
	}
	wg.Wait()

	for i := 0; i < workers; i++ {
		if errs[i] != nil {
			t.Fatalf("worker %d 出错: %v", i, errs[i])
		}
		if !CheckPassword(hashes[i], pw) {
			t.Fatalf("worker %d 的哈希无法校验密码", i)
		}
	}
	for i := 0; i < workers; i++ {
		for j := i + 1; j < workers; j++ {
			if hashes[i] == hashes[j] {
				t.Fatalf("worker %d 与 %d 的哈希相同，盐未随机", i, j)
			}
		}
	}
}

func TestCheckPasswordConcurrentReads(t *testing.T) {
	origCost := BcryptCost
	BcryptCost = bcrypt.MinCost
	defer func() { BcryptCost = origCost }()

	pw := "读并发-密码"
	hash, err := HashPassword(pw)
	if err != nil {
		t.Fatalf("HashPassword 出错: %v", err)
	}

	const readers = 24
	var wg sync.WaitGroup
	results := make([]bool, readers)
	wg.Add(readers)
	for i := 0; i < readers; i++ {
		go func(idx int) {
			defer wg.Done()
			results[idx] = CheckPassword(hash, pw)
		}(i)
	}
	wg.Wait()

	for i, ok := range results {
		if !ok {
			t.Fatalf("reader %d 校验失败", i)
		}
	}
}

func TestBcryptCostVariableIsRespected(t *testing.T) {
	origCost := BcryptCost
	defer func() { BcryptCost = origCost }()

	BcryptCost = bcrypt.MinCost
	hMin, err := HashPassword("cost-test")
	if err != nil {
		t.Fatalf("MinCost 哈希出错: %v", err)
	}
	minCost, err := bcrypt.Cost([]byte(hMin))
	if err != nil {
		t.Fatalf("解析 MinCost 哈希失败: %v", err)
	}
	if minCost != bcrypt.MinCost {
		t.Fatalf("期望 cost %d，实际 %d", bcrypt.MinCost, minCost)
	}

	BcryptCost = bcrypt.MinCost + 1
	hNext, err := HashPassword("cost-test")
	if err != nil {
		t.Fatalf("cost+1 哈希出错: %v", err)
	}
	nextCost, err := bcrypt.Cost([]byte(hNext))
	if err != nil {
		t.Fatalf("解析 cost+1 哈希失败: %v", err)
	}
	if nextCost != bcrypt.MinCost+1 {
		t.Fatalf("期望 cost %d，实际 %d", bcrypt.MinCost+1, nextCost)
	}
}

func TestValidPasswordPolicyErrorIsDistinct(t *testing.T) {
	errEmpty := ValidPasswordPolicy("")
	errLong := ValidPasswordPolicy(strings.Repeat("a", 129))
	if errEmpty == nil || errLong == nil {
		t.Fatalf("两种违规都应返回非 nil 错误")
	}
	if errors.Is(errEmpty, errLong) {
		t.Fatalf("空密码与超长密码的错误不应是同一个")
	}
	if errEmpty.Error() == errLong.Error() {
		t.Fatalf("两种错误文案应不同，实际都为 %q", errEmpty.Error())
	}
	if len([]rune(strings.Repeat("中", 128))) != MaxPasswordRunes {
		t.Fatalf("MaxPasswordRunes 应为 128，实际 %d", MaxPasswordRunes)
	}
}
