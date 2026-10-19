import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { QuizItem, QuizGenerateInput, QuizGradeInput, QuizGradeResult, SubjectKey } from '@kaoyan/shared';
import { SUBJECTS } from '@kaoyan/shared';
import { api } from '../api';

type Stage = 'form' | 'quiz' | 'result';

function localDateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function subjectName(key: SubjectKey): string {
  const found = SUBJECTS.find((s) => s.key === key);
  return found ? found.name : key;
}

export default function Quiz() {
  const [stage, setStage] = useState<Stage>('form');

  // 组卷条件
  const [subject, setSubject] = useState<SubjectKey | ''>('');
  const [unmasteredOnly, setUnmasteredOnly] = useState(true);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [limit, setLimit] = useState(20);

  const [items, setItems] = useState<QuizItem[]>([]);
  const [judgements, setJudgements] = useState<Record<number, boolean>>({});
  const [result, setResult] = useState<QuizGradeResult | null>(null);

  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [emptyMsg, setEmptyMsg] = useState('');

  const answeredCount = useMemo(
    () => items.reduce((acc, it) => acc + (it.id in judgements ? 1 : 0), 0),
    [items, judgements],
  );
  const unanswered = items.length - answeredCount;

  async function handleGenerate() {
    setError('');
    setEmptyMsg('');
    setLoading(true);
    try {
      const input: QuizGenerateInput = {};
      if (subject) input.subject = subject;
      if (unmasteredOnly) input.unmasteredOnly = true;
      if (from) input.from = from;
      if (to) input.to = to;
      if (limit) input.limit = limit;

      const data = await api.generateQuiz(input);
      if (!data || data.length === 0) {
        setItems([]);
        setJudgements({});
        setEmptyMsg('没有符合条件的错题，换个条件试试');
        setStage('form');
      } else {
        setItems(data);
        setJudgements({});
        setResult(null);
        setStage('quiz');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '生成试卷失败，请重试');
    } finally {
      setLoading(false);
    }
  }

  function handleJudge(id: number, correct: boolean) {
    setJudgements((prev) => ({ ...prev, [id]: correct }));
  }

  async function handleSubmit() {
    if (unanswered > 0) return;
    setError('');
    setSubmitting(true);
    try {
      const input: QuizGradeInput = {
        results: items.map((it) => ({
          mistakeId: it.id,
          correct: judgements[it.id],
        })),
      };
      const res = await api.gradeQuiz(input);
      setResult(res);
      setStage('result');
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交批改失败，请重试');
    } finally {
      setSubmitting(false);
    }
  }

  function handlePrint() {
    window.print();
  }

  function handleRestart() {
    setStage('form');
    setItems([]);
    setJudgements({});
    setResult(null);
    setError('');
    setEmptyMsg('');
  }

  const today = localDateStr(new Date());

  return (
    <div className="page">
      <div className="page-header">
        <h1>错题组卷</h1>
        <p>从错题本里挑一批题，组成一套卷子练一练。</p>
      </div>

      {error && <div className="error-box">{error}</div>}

      {stage === 'form' && (
        <div className="card quiz-form">
          {emptyMsg && <div className="empty">{emptyMsg}</div>}

          <div className="form-row">
            <label htmlFor="quiz-subject">科目</label>
            <select
              id="quiz-subject"
              className="select"
              value={subject}
              onChange={(e) => setSubject(e.target.value as SubjectKey | '')}
            >
              <option value="">全部</option>
              {SUBJECTS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-row">
            <label htmlFor="quiz-unmastered">
              <input
                id="quiz-unmastered"
                type="checkbox"
                checked={unmasteredOnly}
                onChange={(e) => setUnmasteredOnly(e.target.checked)}
              />
              只组未掌握
            </label>
          </div>

          <div className="form-row">
            <label htmlFor="quiz-from">创建日期从</label>
            <input
              id="quiz-from"
              className="input"
              type="date"
              max={today}
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
            <label htmlFor="quiz-to">到</label>
            <input
              id="quiz-to"
              className="input"
              type="date"
              max={today}
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </div>

          <div className="form-row">
            <label htmlFor="quiz-limit">题数</label>
            <input
              id="quiz-limit"
              className="input"
              type="number"
              min={1}
              max={100}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            />
          </div>

          <div className="quiz-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={loading}
              onClick={handleGenerate}
            >
              {loading ? '生成中…' : '生成试卷'}
            </button>
          </div>
        </div>
      )}

      {stage === 'quiz' && (
        <div className="quiz-print-area">
          <div className="quiz-actions">
            <button type="button" className="btn" onClick={handlePrint}>
              打印试卷
            </button>
          </div>

          <div className="quiz-list">
            {items.map((it, idx) => {
              const j = judgements[it.id];
              return (
                <div className="quiz-item" key={it.id}>
                  <div className="quiz-item-head">
                    <span className="stat-label">第 {idx + 1} 题</span>
                    <span className={`badge badge-${it.subject}`}>{subjectName(it.subject)}</span>
                    <h3>{it.title}</h3>
                  </div>
                  <p className="quiz-item-content">{it.content}</p>
                  <div className="quiz-judge">
                    <button
                      type="button"
                      className={
                        'quiz-judge-btn' + (j === true ? ' selected-correct' : '')
                      }
                      onClick={() => handleJudge(it.id, true)}
                    >
                      答对了
                    </button>
                    <button
                      type="button"
                      className={
                        'quiz-judge-btn' + (j === false ? ' selected-wrong' : '')
                      }
                      onClick={() => handleJudge(it.id, false)}
                    >
                      答错了
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="quiz-actions">
            {unanswered > 0 && (
              <span className="stat-label">还有 {unanswered} 题没自评</span>
            )}
            <button
              type="button"
              className="btn btn-primary"
              disabled={unanswered > 0 || submitting}
              onClick={handleSubmit}
            >
              {submitting ? '提交中…' : '提交批改'}
            </button>
          </div>
        </div>
      )}

      {stage === 'result' && result && (
        <div className="quiz-result">
          <div className="quiz-result-score">
            <span className="stat-label">正确率</span>
            <strong>
              {result.total > 0
                ? Math.round((result.correct / result.total) * 100)
                : 0}
              %
            </strong>
          </div>
          <p>答对 {result.correct} 题，答错 {result.wrong} 题，共 {result.total} 题。</p>
          <p className="stat-label">
            已回写掌握度：更新了 {result.updatedIds.length} 道题
          </p>

          <div className="quiz-actions">
            <button type="button" className="btn btn-primary" onClick={handleRestart}>
              再组一套
            </button>
            <Link to="/mistakes" className="btn">
              返回错题本
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
