import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';

function pad(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

function backupFileName(): string {
  const d = new Date();
  const s = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`;
  return `kaoyan-backup-${s}.json`;
}

function downloadText(filename: string, text: string, mime: string) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

interface RowError {
  row: number;
  message: string;
}

function ErrorList({ errors }: { errors: RowError[] }) {
  if (errors.length === 0) return null;
  const shown = errors.slice(0, 50);
  return (
    <div className="stack">
      <div className="muted">
        错误 {errors.length} 行{errors.length > shown.length ? '（仅显示前 50 条）' : ''}
      </div>
      <ul className="stack">
        {shown.map((e, i) => (
          <li key={i} className="muted">
            第 {e.row} 行：{e.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function DataTransfer() {
  // 备份导出
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const [exportDone, setExportDone] = useState(false);

  // 备份恢复
  const backupInputRef = useRef<HTMLInputElement>(null);
  const [backupFile, setBackupFile] = useState<File | null>(null);
  const [restoreMode, setRestoreMode] = useState<'replace' | 'merge'>('replace');
  const [restoring, setRestoring] = useState(false);
  const [restoreError, setRestoreError] = useState('');
  const [restoreResult, setRestoreResult] = useState<{
    imported: Record<string, number>;
    skipped: Record<string, number>;
  } | null>(null);

  // 单词导入
  const wordsInputRef = useRef<HTMLInputElement>(null);
  const [wordsFile, setWordsFile] = useState<File | null>(null);
  const [wordsImporting, setWordsImporting] = useState(false);
  const [wordsError, setWordsError] = useState('');
  const [wordsResult, setWordsResult] = useState<{
    imported: number;
    skippedEmpty: number;
    skippedExisting: number;
    errors: RowError[];
  } | null>(null);

  // 错题导入
  const mistakesInputRef = useRef<HTMLInputElement>(null);
  const [mistakesFile, setMistakesFile] = useState<File | null>(null);
  const [mistakesImporting, setMistakesImporting] = useState(false);
  const [mistakesError, setMistakesError] = useState('');
  const [mistakesResult, setMistakesResult] = useState<{
    imported: number;
    errors: RowError[];
  } | null>(null);

  const handleExport = useCallback(async () => {
    setExporting(true);
    setExportError('');
    setExportDone(false);
    try {
      const payload = await api.exportBackup();
      downloadText(backupFileName(), JSON.stringify(payload, null, 2), 'application/json');
      setExportDone(true);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : '导出失败');
    } finally {
      setExporting(false);
    }
  }, []);

  const handleRestore = useCallback(async () => {
    if (!backupFile) return;
    const confirmText =
      restoreMode === 'replace'
        ? '覆盖恢复会清空现有全部数据，确定继续吗？'
        : '合并恢复只新增数据，不会删除现有内容。确定继续吗？';
    if (!window.confirm(confirmText)) return;
    setRestoring(true);
    setRestoreError('');
    setRestoreResult(null);
    try {
      const text = await backupFile.text();
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch {
        throw new Error('文件不是合法的 JSON');
      }
      const res = await api.importBackup(parsed, restoreMode);
      setRestoreResult({ imported: res.imported, skipped: res.skipped });
    } catch (e) {
      setRestoreError(e instanceof Error ? e.message : '恢复失败');
    } finally {
      setRestoring(false);
    }
  }, [backupFile, restoreMode]);

  const handleWordsTemplate = useCallback(() => {
    const csv =
      'word,phonetic,meaning,example\n' +
      'abandon,/əˈbændən/,放弃；抛弃,He abandoned the plan.\n' +
      'benefit,/ˈbenɪfɪt/,好处；受益,It benefits everyone.\n';
    downloadText('words-template.csv', csv, 'text/csv');
  }, []);

  const handleWordsImport = useCallback(async () => {
    if (!wordsFile) return;
    setWordsImporting(true);
    setWordsError('');
    setWordsResult(null);
    try {
      const csv = await wordsFile.text();
      const res = await api.importWordsCsv(csv);
      setWordsResult({
        imported: res.imported,
        skippedEmpty: res.skippedEmpty,
        skippedExisting: res.skippedExisting,
        errors: res.errors,
      });
    } catch (e) {
      setWordsError(e instanceof Error ? e.message : '导入失败');
    } finally {
      setWordsImporting(false);
    }
  }, [wordsFile]);

  const handleMistakesTemplate = useCallback(() => {
    const csv =
      'subject,title,content,analysis\n' +
      'math,极限计算错误,求极限时把分母直接代入,应先用等价无穷小替换\n' +
      'english,时态选错,过去完成时用成了过去时,注意时间状语的先后关系\n';
    downloadText('mistakes-template.csv', csv, 'text/csv');
  }, []);

  const handleMistakesImport = useCallback(async () => {
    if (!mistakesFile) return;
    setMistakesImporting(true);
    setMistakesError('');
    setMistakesResult(null);
    try {
      const csv = await mistakesFile.text();
      const res = await api.importMistakesCsv(csv);
      setMistakesResult({ imported: res.imported, errors: res.errors });
    } catch (e) {
      setMistakesError(e instanceof Error ? e.message : '导入失败');
    } finally {
      setMistakesImporting(false);
    }
  }, [mistakesFile]);

  useEffect(() => {
    return () => {
      setExportDone(false);
    };
  }, []);

  return (
    <div className="stack">
      <div className="card stack">
        <h2>备份与恢复</h2>
        <p className="muted">
          把全部数据导出成一个 JSON 文件，换电脑或重装后能恢复回来。
        </p>
        <div className="row">
          <button className="btn btn-primary" onClick={handleExport} disabled={exporting}>
            {exporting ? '处理中…' : '导出备份'}
          </button>
          {exportDone && <span className="muted">已开始下载备份文件</span>}
          {exportError && <span className="muted">导出失败：{exportError}</span>}
        </div>

        <div className="stack">
          <p className="muted">恢复备份</p>
          <div className="row">
            <input
              ref={backupInputRef}
              type="file"
              accept=".json"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                setBackupFile(f);
                setRestoreError('');
                setRestoreResult(null);
              }}
            />
            {backupFile && <span className="muted">{backupFile.name}</span>}
          </div>
          <div className="row">
            <select
              value={restoreMode}
              onChange={(e) => setRestoreMode(e.target.value as 'replace' | 'merge')}
            >
              <option value="replace">覆盖恢复（清空现有数据）</option>
              <option value="merge">合并恢复（只加不删）</option>
            </select>
            <button
              className="btn btn-primary"
              onClick={handleRestore}
              disabled={restoring || !backupFile}
            >
              {restoring ? '处理中…' : '开始恢复'}
            </button>
          </div>
          {restoreError && <p className="muted">恢复失败：{restoreError}</p>}
          {restoreResult && (
            <div className="stack">
              <p>恢复完成，各表结果：</p>
              <ul className="stack">
                {Object.keys({ ...restoreResult.imported, ...restoreResult.skipped }).map((k) => (
                  <li key={k} className="muted">
                    {k}：导入 {restoreResult.imported[k] ?? 0} 条，跳过{' '}
                    {restoreResult.skipped[k] ?? 0} 条
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      <div className="card stack">
        <h2>单词 CSV 导入</h2>
        <p className="muted">
          表头必须是 word,meaning，可加 phonetic,example。每行一个单词。
        </p>
        <div className="row">
          <button className="btn btn-ghost" onClick={handleWordsTemplate}>
            下载模板
          </button>
        </div>
        <div className="row">
          <input
            ref={wordsInputRef}
            type="file"
            accept=".csv"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setWordsFile(f);
              setWordsError('');
              setWordsResult(null);
            }}
          />
          {wordsFile && <span className="muted">{wordsFile.name}</span>}
        </div>
        <div className="row">
          <button
            className="btn btn-primary"
            onClick={handleWordsImport}
            disabled={wordsImporting || !wordsFile}
          >
            {wordsImporting ? '处理中…' : '开始导入'}
          </button>
        </div>
        {wordsError && <p className="muted">导入失败：{wordsError}</p>}
        {wordsResult && (
          <div className="stack">
            <p>
              导入 {wordsResult.imported} 个 / 跳过空词 {wordsResult.skippedEmpty} 个 /
              已存在 {wordsResult.skippedExisting} 个
            </p>
            <ErrorList errors={wordsResult.errors} />
          </div>
        )}
      </div>

      <div className="card stack">
        <h2>错题 CSV 导入</h2>
        <p className="muted">
          表头必须是 subject,title，可加 content,analysis。subject 用 math/english/politics/major。
        </p>
        <div className="row">
          <button className="btn btn-ghost" onClick={handleMistakesTemplate}>
            下载模板
          </button>
        </div>
        <div className="row">
          <input
            ref={mistakesInputRef}
            type="file"
            accept=".csv"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setMistakesFile(f);
              setMistakesError('');
              setMistakesResult(null);
            }}
          />
          {mistakesFile && <span className="muted">{mistakesFile.name}</span>}
        </div>
        <div className="row">
          <button
            className="btn btn-primary"
            onClick={handleMistakesImport}
            disabled={mistakesImporting || !mistakesFile}
          >
            {mistakesImporting ? '处理中…' : '开始导入'}
          </button>
        </div>
        {mistakesError && <p className="muted">导入失败：{mistakesError}</p>}
        {mistakesResult && (
          <div className="stack">
            <p>导入 {mistakesResult.imported} 条</p>
            <ErrorList errors={mistakesResult.errors} />
          </div>
        )}
      </div>
    </div>
  );
}
