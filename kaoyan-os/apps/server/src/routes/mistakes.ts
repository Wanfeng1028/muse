import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import {
  isSubjectKey,
  type Mistake,
  type CreateMistakeInput,
  type UpdateMistakeInput,
} from '@kaoyan/shared';
import { nowIso } from '../db';

// 数据库行结构
interface MistakeRow {
  id: number;
  subject: string;
  title: string;
  content: string;
  analysis: string;
  mastered: number;
  created_at: string;
}

// 行 -> 契约对象
function rowToMistake(row: MistakeRow): Mistake {
  return {
    id: row.id,
    subject: row.subject as Mistake['subject'],
    title: row.title,
    content: row.content,
    analysis: row.analysis,
    mastered: row.mastered === 1,
    createdAt: row.created_at,
  };
}

export function registerMistakesRoutes(app: FastifyInstance, db: DatabaseSync): void {
  // 列表：可选 subject、mastered、q
  app.get('/api/mistakes', async (request, reply) => {
    const query = request.query as {
      subject?: string;
      mastered?: string;
      q?: string;
    };

    const conditions: string[] = [];
    const params: (string | number)[] = [];

    if (query.subject !== undefined && query.subject !== '') {
      if (!isSubjectKey(query.subject)) {
        return reply.code(400).send({ error: '无效的 subject' });
      }
      conditions.push('subject = ?');
      params.push(query.subject);
    }

    if (query.mastered !== undefined && query.mastered !== '') {
      if (query.mastered !== '0' && query.mastered !== '1') {
        return reply.code(400).send({ error: 'mastered 必须为 0 或 1' });
      }
      conditions.push('mastered = ?');
      params.push(query.mastered === '1' ? 1 : 0);
    }

    if (query.q !== undefined && query.q !== '') {
      const like = `%${query.q}%`;
      conditions.push('(title LIKE ? OR content LIKE ?)');
      params.push(like, like);
    }

    const where = conditions.length > 0 ? ` WHERE ${conditions.join(' AND ')}` : '';
    const rows = db
      .prepare(`SELECT * FROM mistakes${where} ORDER BY id DESC`)
      .all(...params) as unknown as MistakeRow[];

    return reply.send(rows.map(rowToMistake));
  });

  // 创建
  app.post('/api/mistakes', async (request, reply) => {
    const body = request.body as Partial<CreateMistakeInput> | undefined;
    if (!body || typeof body !== 'object') {
      return reply.code(400).send({ error: '请求体无效' });
    }

    if (!isSubjectKey(body.subject)) {
      return reply.code(400).send({ error: 'subject 非法' });
    }
    if (typeof body.title !== 'string' || body.title.trim() === '') {
      return reply.code(400).send({ error: 'title 不能为空' });
    }

    const title = body.title.trim();
    const content = typeof body.content === 'string' ? body.content : '';
    const analysis = typeof body.analysis === 'string' ? body.analysis : '';
    const createdAt = nowIso();

    const result = db
      .prepare(
        `INSERT INTO mistakes (subject, title, content, analysis, mastered, created_at)
         VALUES (?, ?, ?, ?, 0, ?)`
      )
      .run(body.subject, title, content, analysis, createdAt);

    const id = Number(result.lastInsertRowid);
    const row = db
      .prepare('SELECT * FROM mistakes WHERE id = ?')
      .get(id) as unknown as MistakeRow;

    return reply.code(201).send(rowToMistake(row));
  });

  // 更新（逐字段可选）
  app.patch('/api/mistakes/:id', async (request, reply) => {
    const params = request.params as { id: string };
    const id = Number(params.id);
    if (!Number.isInteger(id) || id <= 0) {
      return reply.code(400).send({ error: 'id 非法' });
    }

    const existing = db
      .prepare('SELECT * FROM mistakes WHERE id = ?')
      .get(id) as unknown as MistakeRow | undefined;
    if (!existing) {
      return reply.code(404).send({ error: '错题不存在' });
    }

    const body = request.body as Partial<UpdateMistakeInput> | undefined;
    if (!body || typeof body !== 'object') {
      return reply.code(400).send({ error: '请求体无效' });
    }

    const sets: string[] = [];
    const values: (string | number)[] = [];

    if (body.subject !== undefined) {
      if (!isSubjectKey(body.subject)) {
        return reply.code(400).send({ error: 'subject 非法' });
      }
      sets.push('subject = ?');
      values.push(body.subject);
    }

    if (body.title !== undefined) {
      if (typeof body.title !== 'string' || body.title.trim() === '') {
        return reply.code(400).send({ error: 'title 不能为空' });
      }
      sets.push('title = ?');
      values.push(body.title.trim());
    }

    if (body.content !== undefined) {
      if (typeof body.content !== 'string') {
        return reply.code(400).send({ error: 'content 非法' });
      }
      sets.push('content = ?');
      values.push(body.content);
    }

    if (body.analysis !== undefined) {
      if (typeof body.analysis !== 'string') {
        return reply.code(400).send({ error: 'analysis 非法' });
      }
      sets.push('analysis = ?');
      values.push(body.analysis);
    }

    if (body.mastered !== undefined) {
      if (typeof body.mastered !== 'boolean') {
        return reply.code(400).send({ error: 'mastered 非法' });
      }
      sets.push('mastered = ?');
      values.push(body.mastered ? 1 : 0);
    }

    if (sets.length > 0) {
      values.push(id);
      db.prepare(`UPDATE mistakes SET ${sets.join(', ')} WHERE id = ?`).run(...values);
    }

    const updated = db
      .prepare('SELECT * FROM mistakes WHERE id = ?')
      .get(id) as unknown as MistakeRow;

    return reply.send(rowToMistake(updated));
  });

  // 删除
  app.delete('/api/mistakes/:id', async (request, reply) => {
    const params = request.params as { id: string };
    const id = Number(params.id);
    if (!Number.isInteger(id) || id <= 0) {
      return reply.code(400).send({ error: 'id 非法' });
    }

    const existing = db
      .prepare('SELECT id FROM mistakes WHERE id = ?')
      .get(id);
    if (!existing) {
      return reply.code(404).send({ error: '错题不存在' });
    }

    db.prepare('DELETE FROM mistakes WHERE id = ?').run(id);
    return reply.send({ ok: true });
  });
}
