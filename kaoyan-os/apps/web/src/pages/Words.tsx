import { useCallback, useEffect, useState } from 'react';
import type { WordWithState, CreateWordInput, ReviewGrade, WordSource } from '@kaoyan/shared';
import { WORD_SOURCES } from '@kaoyan/shared';
import { api } from '../api';

// 单词 SRS 复习页：今日复习队列 + 词表管理
export default function Words() {
  // 今日复习队列
  const [queue, setQueue] = useState<WordWithState[]>([]);
  const [total, setTotal] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [loadingQueue, setLoadingQueue] = useState(true);
  const [queueError, setQueueError] = useState('');

  // 词表管理
  const [words, setWords] = useState<WordWithState[]>([]);
  const [loadingWords, setLoadingWords] = useState(true);
  const [wordsError, setWordsError] = useState('');
  const [form, setForm] = useState<CreateWordInput>({
    word: '',
    phonetic: '',
    meaning: '',
    example: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [sourceFilter, setSourceFilter] = useState<'all' | WordSource>('all');

  const current = queue[0];
  const filteredWords =
    sourceFilter === 'all' ? words : words.filter((w) => w.source === sourceFilter);
  const learned = words.filter((w) => w.state.repetitions > 0).length;
  const learnedRate = words.length > 0 ? Math.round((learned / words.length) * 100) : 0;
  const sourceCounts = (Object.keys(WORD_SOURCES) as WordSource[])
    .map((k) => ({ key: k, name: WORD_SOURCES[k], count: words.filter((w) => w.source === k).length }))
    .filter((s) => s.count > 0);

  // 加载今日复习队列
  const loadQueue = useCallback(async () => {
    setLoadingQueue(true);
    setQueueError('');
    try {
      const data = await api.dueWords();
      setQueue(data);
      setTotal(data.length);
      setFlipped(false);
    } catch (e) {
      setQueueError(e instanceof Error ? e.message : '加载复习队列失败');
    } finally {
      setLoadingQueue(false);
    }
  }, []);

  // 加载词表
  const loadWords = useCallback(async () => {
    setLoadingWords(true);
    setWordsError('');
    try {
      const data = await api.listWords();
      setWords(data);
    } catch (e) {
      setWordsError(e instanceof Error ? e.message : '加载词表失败');
    } finally {
      setLoadingWords(false);
    }
  }, []);

  useEffect(() => {
    loadQueue();
    loadWords();
  }, [loadQueue, loadWords]);

  // 评分：调用接口后移出队列并复位翻面
  const handleGrade = async (grade: ReviewGrade) => {
    if (!current) return;
    try {
      await api.reviewWord(current.id, grade);
      setQueue((prev) => prev.slice(1));
      setFlipped(false);
    } catch (e) {
      setQueueError(e instanceof Error ? e.message : '提交评分失败');
    }
  };

  // 新增单词
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.word.trim() || !form.meaning.trim()) return;
    setSubmitting(true);
    try {
      await api.createWord({
        word: form.word.trim(),
        phonetic: form.phonetic.trim(),
        meaning: form.meaning.trim(),
        example: form.example.trim(),
      });
      setForm({ word: '', phonetic: '', meaning: '', example: '' });
      await loadWords();
      await loadQueue();
    } catch (e) {
      setWordsError(e instanceof Error ? e.message : '新增单词失败');
    } finally {
      setSubmitting(false);
    }
  };

  // 删除单词
  const handleDelete = async (id: number) => {
    try {
      await api.deleteWord(id);
      await loadWords();
      await loadQueue();
    } catch (e) {
      setWordsError(e instanceof Error ? e.message : '删除单词失败');
    }
  };

  const reviewed = total - queue.length;

  return (
    <div className="page">
      <div className="page-header">
        <h1>单词复习</h1>
      </div>

      {/* ① 今日复习 */}
      <div className="card">
        <div className="form-row" style={{ justifyContent: 'space-between' }}>
          <h2>今日复习</h2>
          <span className="stat-label">
            已复习 {reviewed} / 共 {total}
          </span>
        </div>

        {loadingQueue ? (
          <div className="loading">加载中…</div>
        ) : queueError ? (
          <div className="error-box">{queueError}</div>
        ) : current ? (
          <>
            <div
              className={`flashcard${flipped ? ' flipped' : ''}`}
              role="button"
              tabIndex={0}
              onClick={() => setFlipped((v) => !v)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setFlipped((v) => !v);
                }
              }}
            >
              <div className="flashcard-inner">
                <div className="flashcard-front">
                  <div className="flashcard-word">{current.word}</div>
                  <div className="flashcard-phonetic">{current.phonetic}</div>
                </div>
                <div className="flashcard-back">
                  <div className="flashcard-meaning">{current.meaning}</div>
                  {current.example && (
                    <div className="flashcard-example">{current.example}</div>
                  )}
                </div>
              </div>
            </div>

            <div className="grade-row">
              <button
                type="button"
                className="btn btn-danger grade-btn"
                onClick={() => handleGrade(0)}
              >
                不会
              </button>
              <button
                type="button"
                className="btn btn-ghost grade-btn"
                onClick={() => handleGrade(1)}
              >
                模糊
              </button>
              <button
                type="button"
                className="btn btn-primary grade-btn"
                onClick={() => handleGrade(2)}
              >
                熟练
              </button>
            </div>
          </>
        ) : (
          <div className="empty">
            {total > 0 ? `今日复习完成，共 ${total} 个单词` : '今日暂无需要复习的单词'}
          </div>
        )}
      </div>

      {/* ② 学习进度 */}
      <div className="card" style={{ marginTop: 16 }}>
        <h2>学习进度</h2>
        <div className="form-row words-stat-row" style={{ marginBottom: 12 }}>
          <span className="stat-label">词库总数 {words.length}</span>
          <span className="stat-label">已学习 {learned}</span>
          <span className="stat-label">今日待复习 {total}</span>
        </div>
        <div className="progress" style={{ marginBottom: 12 }}>
          <div className="progress-bar" style={{ width: `${learnedRate}%` }} />
        </div>
        <div className="text-muted" style={{ fontSize: 13 }}>
          已学习 {learned} / {words.length}（{learnedRate}%）
          {sourceCounts.length > 0 && '；' + sourceCounts.map((s) => `${s.name} ${s.count}`).join(' · ')}
        </div>
      </div>

      {/* ③ 词表管理 */}
      <div className="card" style={{ marginTop: 16 }}>
        <h2>词表管理</h2>

        <form className="form-grid words-form-grid" onSubmit={handleSubmit} style={{ marginBottom: 16 }}>
          <input
            className="input"
            placeholder="单词"
            value={form.word}
            onChange={(e) => setForm({ ...form, word: e.target.value })}
          />
          <input
            className="input"
            placeholder="音标"
            value={form.phonetic}
            onChange={(e) => setForm({ ...form, phonetic: e.target.value })}
          />
          <input
            className="input"
            placeholder="释义"
            value={form.meaning}
            onChange={(e) => setForm({ ...form, meaning: e.target.value })}
          />
          <input
            className="input"
            placeholder="例句"
            value={form.example}
            onChange={(e) => setForm({ ...form, example: e.target.value })}
          />
          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? '添加中…' : '新增单词'}
          </button>
        </form>

        <div className="form-row words-filter-row" style={{ marginBottom: 12 }}>
          <label className="form-label" style={{ margin: 0 }}>
            词库来源
          </label>
          <select
            className="form-select words-source-select"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value as 'all' | WordSource)}
          >
            <option value="all">全部来源</option>
            {(Object.keys(WORD_SOURCES) as WordSource[]).map((k) => (
              <option key={k} value={k}>
                {WORD_SOURCES[k]}
              </option>
            ))}
          </select>
          <span className="stat-label">共 {filteredWords.length} 个</span>
        </div>

        {loadingWords ? (
          <div className="loading">加载中…</div>
        ) : wordsError ? (
          <div className="error-box">{wordsError}</div>
        ) : filteredWords.length === 0 ? (
          <div className="empty">{sourceFilter === 'all' ? '暂无单词' : '该来源暂无单词'}</div>
        ) : (
          <div className="words-table-wrap">
            <table className="table words-table">
              <thead>
                <tr>
                  <th>单词</th>
                  <th>音标</th>
                  <th>释义</th>
                  <th>来源</th>
                  <th>到期日</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredWords.map((w) => (
                  <tr key={w.id}>
                    <td data-label="单词">{w.word}</td>
                    <td data-label="音标">{w.phonetic}</td>
                    <td data-label="释义">{w.meaning}</td>
                    <td data-label="来源">{WORD_SOURCES[w.source] ?? w.source}</td>
                    <td data-label="到期日">{w.state.dueDate}</td>
                    <td data-label="操作">
                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        onClick={() => handleDelete(w.id)}
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
