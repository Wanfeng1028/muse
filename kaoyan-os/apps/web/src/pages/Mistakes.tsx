// 错题本页面：支持按科目/掌握状态/关键词筛选，新增、展开查看、切换掌握、删除错题
import { useCallback, useEffect, useState } from 'react'
import {
  SUBJECTS,
  type Mistake,
  type MistakeSummary,
  type SubjectKey,
  type CreateMistakeInput,
  type ExamRecord,
} from '@kaoyan/shared'

import { api } from '../api'

// 筛选状态下拉选项类型
type MasteredFilter = 'all' | 'unmastered' | 'mastered'

// 科目下拉选项类型（'all' 表示全部科目）
type SubjectFilter = 'all' | SubjectKey

// 新增表单的初始值
const EMPTY_FORM: CreateMistakeInput = {
  subject: 'math',
  title: '',
  content: '',
  analysis: '',
}

// 根据科目 key 获取中文名称
function subjectName(key: SubjectKey): string {
  const s = SUBJECTS.find((item) => item.key === key)
  return s ? s.name : key
}

// 格式化创建时间为日期（YYYY-MM-DD）
function formatDate(iso: string): string {
  return iso.slice(0, 10)
}

export default function Mistakes() {
  // 筛选状态
  const [subject, setSubject] = useState<SubjectFilter>('all')
  const [mastered, setMastered] = useState<MasteredFilter>('all')
  const [q, setQ] = useState('')

  // 列表数据与加载/错误状态
  const [list, setList] = useState<Mistake[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 掌握率汇总（跟随科目筛选）
  const [summary, setSummary] = useState<MistakeSummary | null>(null)


  // 当前展开查看详情的错题 id
  const [expandedId, setExpandedId] = useState<number | null>(null)

  // 新增表单状态与提交状态
  const [form, setForm] = useState<CreateMistakeInput>(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)

  // 来源真题：按错题 id 缓存
  const [sourceExams, setSourceExams] = useState<Record<number, ExamRecord[]>>({})
  const [sourceLoadingId, setSourceLoadingId] = useState<number | null>(null)

  const loadSourceExams = useCallback(
    async (m: Mistake) => {
      if (sourceExams[m.id]) return
      setSourceLoadingId(m.id)
      try {
        const data = await api.mistakeSourceExams(m.id)
        setSourceExams((prev) => ({ ...prev, [m.id]: data }))
      } catch {
        setSourceExams((prev) => ({ ...prev, [m.id]: [] }))
      } finally {
        setSourceLoadingId(null)
      }
    },
    [sourceExams],
  )

  // 按当前筛选条件加载错题列表
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // mastered 为 'all' 时传 undefined（不传该参数）
      const masteredParam =
        mastered === 'all' ? undefined : mastered === 'mastered'
      const data = await api.listMistakes({
        subject: subject === 'all' ? undefined : subject,
        mastered: masteredParam,
        q: q.trim() === '' ? undefined : q.trim(),
      })
      setList(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [subject, mastered, q])

  // 掌握率汇总跟随科目筛选
  useEffect(() => {
    let cancelled = false
    api
      .mistakeSummary(subject === 'all' ? undefined : subject)
      .then((s) => {
        if (!cancelled) setSummary(s)
      })
      .catch(() => {
        if (!cancelled) setSummary(null)
      })
    return () => {
      cancelled = true
    }
  }, [subject])


  // 筛选条件变化时重新加载
  useEffect(() => {
    void load()
  }, [load])

  // 提交新增错题表单
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (form.title.trim() === '' || form.content.trim() === '') {
      setError('请填写题目标题与内容')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await api.createMistake({
        subject: form.subject,
        title: form.title.trim(),
        content: form.content,
        analysis: form.analysis,
      })
      // 清空表单并刷新列表
      setForm(EMPTY_FORM)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '新增失败')
    } finally {
      setSubmitting(false)
    }
  }

  // 切换某道错题的掌握状态
  async function toggleMastered(m: Mistake) {
    try {
      await api.updateMistake(m.id, { mastered: !m.mastered })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新失败')
    }
  }

  // 删除某道错题
  async function handleDelete(id: number) {
    try {
      await api.deleteMistake(id)
      if (expandedId === id) setExpandedId(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败')
    }
  }

  return (
    <div className="page">
      {/* 掌握率汇总 */}
      {summary && summary.total > 0 && (
        <div className="card mistakes-summary">
          <div className="mistakes-summary-track">
            <div className="mistakes-summary-item">
              <div className="stat-label">全部错题</div>
              <div className="stat-value">{summary.total}</div>
            </div>
            <div className="mistakes-summary-item">
              <div className="stat-label">已掌握</div>
              <div className="stat-value mistakes-summary-mastered">
                {summary.mastered}
              </div>
            </div>
            <div className="mistakes-summary-item">
              <div className="stat-label">未掌握</div>
              <div className="stat-value mistakes-summary-unmastered">
                {summary.unmastered}
              </div>
            </div>
            <div className="mistakes-summary-item">
              <div className="stat-label">掌握率</div>
              <div className="stat-value">
                {(summary.masteredRate * 100).toFixed(1)}%
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 页头与筛选栏 */}
      <div className="page-header">
        <h1>错题本</h1>
        <div className="form-row mistakes-filter-row">
          {/* 科目筛选 */}
          <select
            className="select"
            value={subject}
            onChange={(e) => setSubject(e.target.value as SubjectFilter)}
          >
            <option value="all">全部科目</option>
            {SUBJECTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.name}
              </option>
            ))}
          </select>

          {/* 掌握状态筛选 */}
          <select
            className="select"
            value={mastered}
            onChange={(e) => setMastered(e.target.value as MasteredFilter)}
          >
            <option value="all">全部状态</option>
            <option value="unmastered">未掌握</option>
            <option value="mastered">已掌握</option>
          </select>

          {/* 关键词搜索 */}
          <input
            className="input"
            placeholder="搜索题目/解析关键词"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>

      {/* 新增错题表单 */}
      <form className="card mistakes-form" onSubmit={handleSubmit}>
        <div className="form-grid">
          <select
            className="select"
            value={form.subject}
            onChange={(e) =>
              setForm({ ...form, subject: e.target.value as SubjectKey })
            }
          >
            {SUBJECTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.name}
              </option>
            ))}
          </select>

          <input
            className="input"
            placeholder="题目标题"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
        </div>

        <textarea
          className="textarea"
          placeholder="题目内容"
          rows={3}
          value={form.content}
          onChange={(e) => setForm({ ...form, content: e.target.value })}
        />

        <textarea
          className="textarea"
          placeholder="解析 / 错误原因"
          rows={3}
          value={form.analysis}
          onChange={(e) => setForm({ ...form, analysis: e.target.value })}
        />

        <div className="form-row">
          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? '提交中…' : '添加错题'}
          </button>
        </div>
      </form>

      {/* 错误提示 */}
      {error && <div className="error-box">{error}</div>}

      {/* 加载状态 */}
      {loading && <div className="loading">加载中…</div>}

      {/* 空状态 */}
      {!loading && list.length === 0 && !error && (
        <div className="empty">暂无错题</div>
      )}

      {/* 错题列表 */}
      {!loading && list.length > 0 && (
        <div className="list">
          {list.map((m) => {
            const isOpen = expandedId === m.id
            return (
              <div className="list-item mistakes-item" key={m.id}>
                <div className="mistakes-item-head">
                  <span className={`badge badge-${m.subject}`}>
                    {subjectName(m.subject)}
                  </span>
                  <span className="stat-label mistakes-item-date">
                    {formatDate(m.createdAt)}
                  </span>
                </div>
                {/* 点击标题展开/收起详情 */}
                <button
                  className="btn btn-ghost btn-sm mistakes-item-title"
                  type="button"
                  onClick={() => setExpandedId(isOpen ? null : m.id)}
                >
                  {m.title}
                </button>
                <div className="mistakes-item-actions">
                  {/* 掌握状态切换 */}
                  <button
                    className="btn btn-sm"
                    type="button"
                    onClick={() => void toggleMastered(m)}
                  >
                    {m.mastered ? '已掌握' : '未掌握'}
                  </button>
                  {/* 删除 */}
                  <button
                    className="btn btn-danger btn-sm"
                    type="button"
                    onClick={() => void handleDelete(m.id)}
                  >
                    删除
                  </button>
                </div>

                {/* 展开详情 */}
                {isOpen && (
                  <div className="mistakes-item-detail">
                    <div className="mistakes-item-detail-block">
                      <strong>题目：</strong>
                      {m.content}
                    </div>
                    <div className="mistakes-item-detail-block">
                      <strong>解析：</strong>
                      {m.analysis}
                    </div>
                    <div className="mistakes-item-detail-block">
                      <strong>来源真题：</strong>
                      {sourceExams[m.id] ? (
                        sourceExams[m.id].length === 0 ? (
                          <span className="stat-label">附近没有真题记录</span>
                        ) : (
                          <ul style={{ margin: '4px 0', paddingLeft: 18 }}>
                            {sourceExams[m.id].map((e) => (
                              <li key={e.id}>
                                {e.takenAt} {e.paper}（{e.score}/{e.totalScore}）
                              </li>
                            ))}
                          </ul>
                        )
                      ) : (
                        <button
                          className="btn btn-sm"
                          type="button"
                          disabled={sourceLoadingId === m.id}
                          onClick={() => void loadSourceExams(m)}
                        >
                          {sourceLoadingId === m.id ? '加载中…' : '查看来源真题'}
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
