import { useEffect, useMemo, useState } from 'react';
import type { WordSource } from '@kaoyan/shared';
import { api, type VocabStatus } from '../api';
import type { WordWithState } from '@kaoyan/shared';

const PAGE_SIZE = 20;
const CORE_SOURCE: WordSource = 'core500';

type MasterFilter = 'all' | 'mastered' | 'pending';

function isMastered(w: WordWithState): boolean {
  return (w.state?.repetitions ?? 0) > 0;
}

export default function Vocab() {
  const [words, setWords] = useState<WordWithState[]>([]);
  const [status, setStatus] = useState<VocabStatus | null>(null);
  const [loadingWords, setLoadingWords] = useState(false);
  const [wordsError, setWordsError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [seedMsg, setSeedMsg] = useState<string | null>(null);
  const [seedError, setSeedError] = useState<string | null>(null);

  const [keyword, setKeyword] = useState('');
  const [masterFilter, setMasterFilter] = useState<MasterFilter>('all');
  const [page, setPage] = useState(1);

  const loadWords = async () => {
    setLoadingWords(true);
    setWordsError(null);
    try {
      const data = await api.listWords();
      setWords(data);
    } catch (err) {
      setWordsError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingWords(false);
    }
  };

  const loadStatus = async () => {
    try {
      const s = await api.vocabStatus();
      setStatus(s);
    } catch (err) {
      setWordsError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    void loadWords();
    void loadStatus();
  }, []);

  const coreWords = useMemo(
    () => words.filter((w) => w.source === CORE_SOURCE),
    [words],
  );

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return coreWords.filter((w) => {
      const mastered = isMastered(w);
      if (masterFilter === 'mastered' && !mastered) return false;
      if (masterFilter === 'pending' && mastered) return false;
      if (!kw) return true;
      const inWord = w.word.toLowerCase().includes(kw);
      const inMeaning = (w.meaning || '').toLowerCase().includes(kw);
      return inWord || inMeaning;
    });
  }, [coreWords, keyword, masterFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageItems = filtered.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE,
  );

  useEffect(() => {
    setPage(1);
  }, [keyword, masterFilter]);

  const handleSeed = async () => {
    setSeeding(true);
    setSeedMsg(null);
    setSeedError(null);
    try {
      const result = await api.seedVocab();
      setSeedMsg(`导入 ${result.imported} 个，已有 ${result.skippedExisting} 个跳过`);
      await Promise.all([loadWords(), loadStatus()]);
    } catch (err) {
      setSeedError(err instanceof Error ? err.message : String(err));
    } finally {
      setSeeding(false);
    }
  };

  const handleMaster = async (id: number) => {
    try {
      const updated = await api.reviewWord(id, 2);
      setWords((prev) => prev.map((w) => (w.id === id ? updated : w)));
      await loadStatus();
    } catch (err) {
      setWordsError(err instanceof Error ? err.message : String(err));
    }
  };

  const total = status?.total ?? 0;
  const mastered = status?.mastered ?? 0;
  const pending = status?.pending ?? 0;
  const percent = total > 0 ? Math.round((mastered / total) * 100) : 0;

  return (
    <div className="page">
      <div className="page-header">
        <h1>核心词库</h1>
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleSeed}
          disabled={seeding}
        >
          {seeding ? '导入中…' : '导入词库'}
        </button>
      </div>

      {seedError && <div className="error-box">{seedError}</div>}
      {seedMsg && <div className="text-muted" style={{ marginBottom: 12 }}>{seedMsg}</div>}

      <div className="card">
        <div className="stat-label">词库状态</div>
        <div style={{ margin: '8px 0' }}>
          共收录 {total} 词 · 已掌握 {mastered} · 待掌握 {pending}
        </div>
        <div className="progress">
          <div className="progress-bar" style={{ width: `${percent}%` }} />
        </div>
        <div className="text-muted" style={{ marginTop: 6 }}>已掌握 {percent}%</div>
      </div>

      <div className="card">
        <div className="form-row">
          <div className="form-label">搜索</div>
          <input
            className="input"
            type="text"
            placeholder="搜单词或中文释义"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>
        <div className="form-row">
          <div className="form-label">掌握情况</div>
          <select
            className="form-select"
            value={masterFilter}
            onChange={(e) => setMasterFilter(e.target.value as MasterFilter)}
          >
            <option value="all">全部</option>
            <option value="mastered">已掌握</option>
            <option value="pending">未掌握</option>
          </select>
          <div className="stat-label" style={{ marginLeft: 'auto' }}>
            共 {filtered.length} 个
          </div>
        </div>

        {loadingWords ? (
          <div className="loading">加载中…</div>
        ) : wordsError ? (
          <div className="error-box">{wordsError}</div>
        ) : pageItems.length === 0 ? (
          <div className="empty">
            {coreWords.length === 0
              ? '还没导入词库，先点右上角导入'
              : '没有符合筛选条件的单词，换个关键词或筛选试试'}
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>单词</th>
                <th>音标</th>
                <th>释义</th>
                <th>记忆法</th>
                <th style={{ whiteSpace: 'nowrap' }}>状态</th>
                <th style={{ whiteSpace: 'nowrap' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {pageItems.map((w) => {
                const masteredNow = isMastered(w);
                return (
                  <tr key={w.id}>
                    <td>{w.word}</td>
                    <td>{w.phonetic || '—'}</td>
                    <td>{w.meaning}</td>
                    <td>{w.memory_tip || '—'}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>{masteredNow ? '已掌握' : '未掌握'}</td>
                    <td>
                      {masteredNow ? (
                        <span className="text-muted" style={{ whiteSpace: 'nowrap' }}>已掌握</span>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-sm btn-ghost"
                          style={{ whiteSpace: 'nowrap' }}
                          onClick={() => handleMaster(w.id)}
                        >
                          标记已掌握
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {filtered.length > 0 && (
          <div className="form-row" style={{ marginTop: 12, alignItems: 'center' }}>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1}
            >
              上一页
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages}
            >
              下一页
            </button>
            <div className="stat-label">
              第 {currentPage} / 共 {totalPages} 页
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
