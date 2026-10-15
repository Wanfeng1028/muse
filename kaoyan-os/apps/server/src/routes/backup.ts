import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { isSubjectKey } from '@kaoyan/shared';
import { todayStr, nowIso } from '../db';

interface BackupTableMap {
  plans: Record<string, unknown>[];
  focus_sessions: Record<string, unknown>[];
  mistakes: Record<string, unknown>[];
  words: Record<string, unknown>[];
  srs_state: Record<string, unknown>[];
  exam_records: Record<string, unknown>[];
  settings: Record<string, unknown>[];
}

interface BackupPayload {
  format: string;
  version: number;
  exportedAt: string;
  tables: BackupTableMap;
}

const TABLE_ORDER: (keyof BackupTableMap)[] = [
  'plans',
  'focus_sessions',
  'mistakes',
  'words',
  'srs_state',
  'exam_records',
  'settings',
];

type Row = Record<string, unknown>;

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function parseCsv(text: string): string[][] {
  let input = text;
  if (input.charCodeAt(0) === 0xfeff) {
    input = input.slice(1);
  }
  const rows: string[][] = [];
  let field = '';
  let row: string[] = [];
  let inQuotes = false;
  let i = 0;
  const len = input.length;

  const pushField = (): void => {
    row.push(field);
    field = '';
  };
  const pushRow = (): void => {
    pushField();
    rows.push(row);
    row = [];
  };

  while (i < len) {
    const ch = input[i];
    if (inQuotes) {
      if (ch === '"') {
        if (i + 1 < len && input[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i += 1;
        continue;
      }
      field += ch;
      i += 1;
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
      i += 1;
      continue;
    }
    if (ch === ',') {
      pushField();
      i += 1;
      continue;
    }
    if (ch === '\r') {
      if (i + 1 < len && input[i + 1] === '\n') {
        i += 1;
      }
      pushRow();
      i += 1;
      continue;
    }
    if (ch === '\n') {
      pushRow();
      i += 1;
      continue;
    }
    field += ch;
    i += 1;
  }

  if (field.length > 0 || row.length > 0 || inQuotes) {
    pushRow();
  }
  return rows;
}

function isBlankRow(cells: string[]): boolean {
  return cells.every((c) => c.trim() === '');
}

function normalizeHeader(cells: string[]): string[] {
  return cells.map((c) => c.trim().toLowerCase());
}

function buildHeaderIndex(header: string[]): Map<string, number> {
  const map = new Map<string, number>();
  for (let i = 0; i < header.length; i += 1) {
    const name = header[i];
    if (!map.has(name)) {
      map.set(name, i);
    }
  }
  return map;
}

function cellAt(cells: string[], idx: number | undefined): string {
  if (idx === undefined || idx < 0 || idx >= cells.length) {
    return '';
  }
  return cells[idx];
}

export function registerBackupRoutes(app: FastifyInstance, db: DatabaseSync): void {
  app.get('/api/backup/export', async (_req, reply) => {
    const tables = {
      plans: db.prepare('SELECT * FROM plans ORDER BY id ASC').all() as Row[],
      focus_sessions: db
        .prepare('SELECT * FROM focus_sessions ORDER BY id ASC')
        .all() as Row[],
      mistakes: db.prepare('SELECT * FROM mistakes ORDER BY id ASC').all() as Row[],
      words: db.prepare('SELECT * FROM words ORDER BY id ASC').all() as Row[],
      srs_state: db
        .prepare('SELECT * FROM srs_state ORDER BY word_id ASC')
        .all() as Row[],
      exam_records: db
        .prepare('SELECT * FROM exam_records ORDER BY id ASC')
        .all() as Row[],
      settings: db.prepare('SELECT * FROM settings ORDER BY key ASC').all() as Row[],
    };
    return reply.code(200).send({
      format: 'kaoyan-backup',
      version: 1,
      exportedAt: new Date().toISOString(),
      tables,
    });
  });

  app.post(
    '/api/backup/import',
    { bodyLimit: 20 * 1024 * 1024 },
    async (req, reply) => {
      const body = req.body as unknown;
      if (!isPlainObject(body)) {
        return reply.code(400).send({ error: '请求体无效' });
      }
      const data = body.data;
      const modeRaw = body.mode;
      let mode: 'replace' | 'merge';
      if (modeRaw === undefined) {
        mode = 'replace';
      } else if (modeRaw === 'replace' || modeRaw === 'merge') {
        mode = modeRaw;
      } else {
        return reply.code(400).send({ error: '无效的 mode' });
      }

      if (!isPlainObject(data)) {
        return reply.code(400).send({ error: 'data 无效' });
      }
      if (data.format !== 'kaoyan-backup') {
        return reply.code(400).send({ error: 'format 无效' });
      }
      if (data.version !== 1) {
        return reply.code(400).send({ error: 'version 无效' });
      }
      if (!isPlainObject(data.tables)) {
        return reply.code(400).send({ error: 'tables 无效' });
      }
      const tables = data.tables as Record<string, unknown>;

      const validated: Record<string, Row[]> = {};
      for (const name of TABLE_ORDER) {
        const t = tables[name];
        if (!Array.isArray(t)) {
          return reply.code(400).send({ error: `表 ${name} 不是数组` });
        }
        const rows: Row[] = [];
        for (let r = 0; r < t.length; r += 1) {
          const rawRow = t[r];
          if (!isPlainObject(rawRow)) {
            return reply
              .code(400)
              .send({ error: `表 ${name} 第 ${r + 1} 行不是对象` });
          }
          const rowNum = r + 1;
          const fail = (reason: string): { error: string } => ({
            error: `表 ${name} 第 ${rowNum} 行：${reason}`,
          });

          switch (name) {
            case 'plans': {
              const date = rawRow.date;
              const subject = rawRow.subject;
              const title = rawRow.title;
              if (typeof date !== 'string' || date.length === 0) {
                return reply.code(400).send(fail('date 缺失或类型不对'));
              }
              if (!isSubjectKey(subject)) {
                return reply.code(400).send(fail('subject 无效'));
              }
              if (typeof title !== 'string' || title.length === 0) {
                return reply.code(400).send(fail('title 缺失或类型不对'));
              }
              break;
            }
            case 'focus_sessions': {
              const subject = rawRow.subject;
              const startedAt = rawRow.started_at;
              if (!isSubjectKey(subject)) {
                return reply.code(400).send(fail('subject 无效'));
              }
              if (typeof startedAt !== 'string' || startedAt.length === 0) {
                return reply.code(400).send(fail('started_at 缺失或类型不对'));
              }
              break;
            }
            case 'mistakes': {
              const subject = rawRow.subject;
              const title = rawRow.title;
              if (!isSubjectKey(subject)) {
                return reply.code(400).send(fail('subject 无效'));
              }
              if (typeof title !== 'string' || title.length === 0) {
                return reply.code(400).send(fail('title 缺失或类型不对'));
              }
              break;
            }
            case 'words': {
              const word = rawRow.word;
              const meaning = rawRow.meaning;
              if (typeof word !== 'string' || word.length === 0) {
                return reply.code(400).send(fail('word 缺失或类型不对'));
              }
              if (typeof meaning !== 'string' || meaning.length === 0) {
                return reply.code(400).send(fail('meaning 缺失或类型不对'));
              }
              break;
            }
            case 'srs_state': {
              const wordId = rawRow.word_id;
              const dueDate = rawRow.due_date;
              if (typeof wordId !== 'number' || !Number.isFinite(wordId)) {
                return reply.code(400).send(fail('word_id 缺失或类型不对'));
              }
              if (typeof dueDate !== 'string' || dueDate.length === 0) {
                return reply.code(400).send(fail('due_date 缺失或类型不对'));
              }
              break;
            }
            case 'exam_records': {
              const subject = rawRow.subject;
              const paper = rawRow.paper;
              const takenAt = rawRow.taken_at;
              if (!isSubjectKey(subject)) {
                return reply.code(400).send(fail('subject 无效'));
              }
              if (typeof paper !== 'string' || paper.length === 0) {
                return reply.code(400).send(fail('paper 缺失或类型不对'));
              }
              if (typeof takenAt !== 'string' || takenAt.length === 0) {
                return reply.code(400).send(fail('taken_at 缺失或类型不对'));
              }
              break;
            }
            case 'settings': {
              const key = rawRow.key;
              const value = rawRow.value;
              if (typeof key !== 'string' || key.length === 0) {
                return reply.code(400).send(fail('key 缺失或类型不对'));
              }
              if (typeof value !== 'string') {
                return reply.code(400).send(fail('value 缺失或类型不对'));
              }
              break;
            }
            default:
              break;
          }
          rows.push(rawRow);
        }
        validated[name] = rows;
      }

      const imported = {
        plans: 0,
        focus_sessions: 0,
        mistakes: 0,
        words: 0,
        srs_state: 0,
        exam_records: 0,
        settings: 0,
      };
      const skipped = {
        plans: 0,
        focus_sessions: 0,
        mistakes: 0,
        words: 0,
        srs_state: 0,
        exam_records: 0,
        settings: 0,
      };

      if (mode === 'replace') {
        try {
          db.exec('BEGIN');
          try {
            db.exec('DELETE FROM srs_state');
            db.exec('DELETE FROM words');
            db.exec('DELETE FROM plans');
            db.exec('DELETE FROM focus_sessions');
            db.exec('DELETE FROM mistakes');
            db.exec('DELETE FROM exam_records');
            db.exec('DELETE FROM settings');

            const insertSettings = db.prepare(
              'INSERT INTO settings (key, value) VALUES (?, ?)'
            );
            for (const row of validated.settings) {
              insertSettings.run(row.key as string, row.value as string);
              imported.settings += 1;
            }

            const insertExam = db.prepare(
              'INSERT INTO exam_records (id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
            );
            for (const row of validated.exam_records) {
              insertExam.run(
                (row.id as number) ?? null,
                row.subject as string,
                row.paper as string,
                typeof row.score === 'number' ? row.score : 0,
                typeof row.total_score === 'number' ? row.total_score : 0,
                typeof row.duration_minutes === 'number' ? row.duration_minutes : 0,
                row.taken_at as string
              );
              imported.exam_records += 1;
            }

            const insertMistake = db.prepare(
              'INSERT INTO mistakes (id, subject, title, content, analysis, mastered, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
            );
            for (const row of validated.mistakes) {
              insertMistake.run(
                (row.id as number) ?? null,
                row.subject as string,
                row.title as string,
                typeof row.content === 'string' ? row.content : '',
                typeof row.analysis === 'string' ? row.analysis : '',
                typeof row.mastered === 'number' ? row.mastered : 0,
                typeof row.created_at === 'string'
                  ? row.created_at
                  : nowIso()
              );
              imported.mistakes += 1;
            }

            const insertFocus = db.prepare(
              'INSERT INTO focus_sessions (id, subject, minutes, started_at, note) VALUES (?, ?, ?, ?, ?)'
            );
            for (const row of validated.focus_sessions) {
              insertFocus.run(
                (row.id as number) ?? null,
                row.subject as string,
                typeof row.minutes === 'number' ? row.minutes : 0,
                row.started_at as string,
                row.note === null || row.note === undefined
                  ? null
                  : (row.note as string)
              );
              imported.focus_sessions += 1;
            }

            const insertPlan = db.prepare(
              'INSERT INTO plans (id, date, subject, title, planned_minutes, done, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
            );
            for (const row of validated.plans) {
              insertPlan.run(
                (row.id as number) ?? null,
                row.date as string,
                row.subject as string,
                row.title as string,
                typeof row.planned_minutes === 'number' ? row.planned_minutes : 0,
                typeof row.done === 'number' ? row.done : 0,
                typeof row.created_at === 'string' ? row.created_at : nowIso()
              );
              imported.plans += 1;
            }

            const insertWord = db.prepare(
              'INSERT INTO words (id, word, phonetic, meaning, example) VALUES (?, ?, ?, ?, ?)'
            );
            for (const row of validated.words) {
              insertWord.run(
                (row.id as number) ?? null,
                row.word as string,
                typeof row.phonetic === 'string' ? row.phonetic : '',
                row.meaning as string,
                typeof row.example === 'string' ? row.example : ''
              );
              imported.words += 1;
            }

            const insertSrs = db.prepare(
              'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)'
            );
            for (const row of validated.srs_state) {
              insertSrs.run(
                row.word_id as number,
                typeof row.ease === 'number' ? row.ease : 2.5,
                typeof row.interval_days === 'number' ? row.interval_days : 0,
                typeof row.repetitions === 'number' ? row.repetitions : 0,
                row.due_date as string
              );
              imported.srs_state += 1;
            }

            db.exec('COMMIT');
          } catch (err) {
            try {
              db.exec('ROLLBACK');
            } catch {
              /* ignore */
            }
            throw err;
          }
        } catch {
          return reply.code(500).send({ error: '导入失败' });
        }
      } else {
        // merge
        const findWord = db.prepare('SELECT id FROM words WHERE word = ?');
        const insertWord = db.prepare(
          'INSERT INTO words (word, phonetic, meaning, example) VALUES (?, ?, ?, ?)'
        );
        for (const row of validated.words) {
          const word = row.word as string;
          const existing = findWord.get(word) as { id: number } | undefined;
          if (existing) {
            skipped.words += 1;
            continue;
          }
          const info = insertWord.run(
            word,
            typeof row.phonetic === 'string' ? row.phonetic : '',
            row.meaning as string,
            typeof row.example === 'string' ? row.example : ''
          );
          if (info.lastInsertRowid !== undefined && info.lastInsertRowid !== null) {
            imported.words += 1;
          }
        }

        const wordExists = db.prepare('SELECT id FROM words WHERE id = ?');
        const upsertSrs = db.prepare(
          'INSERT OR REPLACE INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)'
        );
        for (const row of validated.srs_state) {
          const wordId = row.word_id as number;
          const found = wordExists.get(wordId) as { id: number } | undefined;
          if (!found) {
            skipped.srs_state += 1;
            continue;
          }
          upsertSrs.run(
            wordId,
            typeof row.ease === 'number' ? row.ease : 2.5,
            typeof row.interval_days === 'number' ? row.interval_days : 0,
            typeof row.repetitions === 'number' ? row.repetitions : 0,
            row.due_date as string
          );
          imported.srs_state += 1;
        }

        const insertPlan = db.prepare(
          'INSERT INTO plans (id, date, subject, title, planned_minutes, done, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
        );
        for (const row of validated.plans) {
          try {
            insertPlan.run(
              (row.id as number) ?? null,
              row.date as string,
              row.subject as string,
              row.title as string,
              typeof row.planned_minutes === 'number' ? row.planned_minutes : 0,
              typeof row.done === 'number' ? row.done : 0,
              typeof row.created_at === 'string' ? row.created_at : nowIso()
            );
            imported.plans += 1;
          } catch {
            skipped.plans += 1;
          }
        }

        const insertFocus = db.prepare(
          'INSERT INTO focus_sessions (id, subject, minutes, started_at, note) VALUES (?, ?, ?, ?, ?)'
        );
        for (const row of validated.focus_sessions) {
          try {
            insertFocus.run(
              (row.id as number) ?? null,
              row.subject as string,
              typeof row.minutes === 'number' ? row.minutes : 0,
              row.started_at as string,
              row.note === null || row.note === undefined
                ? null
                : (row.note as string)
            );
            imported.focus_sessions += 1;
          } catch {
            skipped.focus_sessions += 1;
          }
        }

        const insertMistake = db.prepare(
          'INSERT INTO mistakes (id, subject, title, content, analysis, mastered, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
        );
        for (const row of validated.mistakes) {
          try {
            insertMistake.run(
              (row.id as number) ?? null,
              row.subject as string,
              row.title as string,
              typeof row.content === 'string' ? row.content : '',
              typeof row.analysis === 'string' ? row.analysis : '',
              typeof row.mastered === 'number' ? row.mastered : 0,
              typeof row.created_at === 'string' ? row.created_at : nowIso()
            );
            imported.mistakes += 1;
          } catch {
            skipped.mistakes += 1;
          }
        }

        const insertExam = db.prepare(
          'INSERT INTO exam_records (id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
        );
        for (const row of validated.exam_records) {
          try {
            insertExam.run(
              (row.id as number) ?? null,
              row.subject as string,
              row.paper as string,
              typeof row.score === 'number' ? row.score : 0,
              typeof row.total_score === 'number' ? row.total_score : 0,
              typeof row.duration_minutes === 'number' ? row.duration_minutes : 0,
              row.taken_at as string
            );
            imported.exam_records += 1;
          } catch {
            skipped.exam_records += 1;
          }
        }

        const upsertSetting = db.prepare(
          'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)'
        );
        for (const row of validated.settings) {
          upsertSetting.run(row.key as string, row.value as string);
          imported.settings += 1;
        }
      }

      return reply.code(200).send({ mode, imported, skipped });
    }
  );

  app.post(
    '/api/import/words',
    { bodyLimit: 5 * 1024 * 1024 },
    async (req, reply) => {
      const body = req.body as unknown;
      if (!isPlainObject(body)) {
        return reply.code(400).send({ error: '请求体无效' });
      }
      const csv = body.csv;
      if (typeof csv !== 'string' || csv.trim() === '') {
        return reply.code(400).send({ error: 'csv 不能为空' });
      }

      const allRows = parseCsv(csv);
      let headerIdx = -1;
      for (let i = 0; i < allRows.length; i += 1) {
        if (!isBlankRow(allRows[i])) {
          headerIdx = i;
          break;
        }
      }
      if (headerIdx === -1) {
        return reply.code(400).send({ error: '缺少必需列：word / meaning' });
      }

      const header = normalizeHeader(allRows[headerIdx]);
      const headerMap = buildHeaderIndex(header);
      const wordIdx = headerMap.get('word');
      const meaningIdx = headerMap.get('meaning');
      if (wordIdx === undefined || meaningIdx === undefined) {
        return reply.code(400).send({ error: '缺少必需列：word / meaning' });
      }

      const findWord = db.prepare('SELECT id FROM words WHERE word = ?');
      const insertWord = db.prepare(
        'INSERT INTO words (word, phonetic, meaning, example) VALUES (?, ?, ?, ?)'
      );
      const insertSrs = db.prepare(
        'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)'
      );

      let imported = 0;
      let skippedEmpty = 0;
      let skippedExisting = 0;
      let errorRows = 0;
      const errors: { row: number; message: string }[] = [];

      for (let i = headerIdx + 1; i < allRows.length; i += 1) {
        const cells = allRows[i];
        if (isBlankRow(cells)) {
          continue;
        }
        const rowNum = i + 1;
        const word = cellAt(cells, wordIdx).trim();
        const meaning = cellAt(cells, meaningIdx).trim();

        if (word === '') {
          skippedEmpty += 1;
          continue;
        }
        if (meaning === '') {
          errorRows += 1;
          if (errors.length < 50) {
            errors.push({ row: rowNum, message: 'meaning 不能为空' });
          }
          continue;
        }
        const existing = findWord.get(word) as { id: number } | undefined;
        if (existing) {
          skippedExisting += 1;
          continue;
        }
        const phonetic = cellAt(cells, headerMap.get('phonetic')).trim();
        const example = cellAt(cells, headerMap.get('example')).trim();
        const info = insertWord.run(word, phonetic, meaning, example);
        const newId = info.lastInsertRowid as number;
        insertSrs.run(newId, 2.5, 0, 0, todayStr());
        imported += 1;
      }

      return reply.code(200).send({
        imported,
        skippedEmpty,
        skippedExisting,
        errors,
        errorRows,
      });
    }
  );

  app.post(
    '/api/import/mistakes',
    { bodyLimit: 5 * 1024 * 1024 },
    async (req, reply) => {
      const body = req.body as unknown;
      if (!isPlainObject(body)) {
        return reply.code(400).send({ error: '请求体无效' });
      }
      const csv = body.csv;
      if (typeof csv !== 'string' || csv.trim() === '') {
        return reply.code(400).send({ error: 'csv 不能为空' });
      }

      const allRows = parseCsv(csv);
      let headerIdx = -1;
      for (let i = 0; i < allRows.length; i += 1) {
        if (!isBlankRow(allRows[i])) {
          headerIdx = i;
          break;
        }
      }
      if (headerIdx === -1) {
        return reply.code(400).send({ error: '缺少必需列：subject / title' });
      }

      const header = normalizeHeader(allRows[headerIdx]);
      const headerMap = buildHeaderIndex(header);
      const subjectIdx = headerMap.get('subject');
      const titleIdx = headerMap.get('title');
      if (subjectIdx === undefined || titleIdx === undefined) {
        return reply.code(400).send({ error: '缺少必需列：subject / title' });
      }
      const contentIdx = headerMap.get('content');
      const analysisIdx = headerMap.get('analysis');

      const insertMistake = db.prepare(
        'INSERT INTO mistakes (subject, title, content, analysis, mastered, created_at) VALUES (?, ?, ?, ?, ?, ?)'
      );

      let imported = 0;
      let errorRows = 0;
      const errors: { row: number; message: string }[] = [];

      for (let i = headerIdx + 1; i < allRows.length; i += 1) {
        const cells = allRows[i];
        if (isBlankRow(cells)) {
          continue;
        }
        const rowNum = i + 1;
        const subject = cellAt(cells, subjectIdx).trim();
        const title = cellAt(cells, titleIdx).trim();

        if (!isSubjectKey(subject)) {
          errorRows += 1;
          if (errors.length < 50) {
            errors.push({ row: rowNum, message: '无效的 subject' });
          }
          continue;
        }
        if (title === '') {
          errorRows += 1;
          if (errors.length < 50) {
            errors.push({ row: rowNum, message: 'title 不能为空' });
          }
          continue;
        }
        const content = contentIdx === undefined ? '' : cellAt(cells, contentIdx);
        const analysis = analysisIdx === undefined ? '' : cellAt(cells, analysisIdx);
        insertMistake.run(subject, title, content, analysis, 0, nowIso());
        imported += 1;
      }

      return reply.code(200).send({ imported, errors, errorRows });
    }
  );
}
