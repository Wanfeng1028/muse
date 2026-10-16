package store

// PushLogStatus 查询指定 (date, channel, user) 的 push_log 最新状态。
//
// 返回约定：
//   - 有记录：返回 (status, true)。
//   - 无记录：返回 ("", false)。
//   - 查询出错：返回 ("", false)。
//
// 这里刻意不返回 error，是为了让调用方（如死信幂等判断）在查询失败时
// 走"未找到"分支继续执行，而不是中断整个批次；是否记录日志由调用方决定。
//
// user 会经过 NormalizeUser 归一化，与 RecordPushFor 写入时的 user_id 保持一致，
// 否则会出现"写入用归一化值、查询用原始值"导致查不到记录的问题。
func (s *Store) PushLogStatus(date, channel, user string) (string, bool) {
	normalized := NormalizeUser(user)

	row := s.db.QueryRow(
		`SELECT status FROM push_log WHERE date = ? AND channel = ? AND user_id = ? ORDER BY created_at DESC LIMIT 1`,
		date, channel, normalized,
	)

	var status string
	if err := row.Scan(&status); err != nil {
		return "", false
	}
	return status, true
}
