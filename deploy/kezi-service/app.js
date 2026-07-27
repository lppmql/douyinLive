'use strict';

/**
 * 客资安全回填服务。
 *
 * 保留旧接口：
 * - POST /api/kezi：写入客资
 * - GET /api/douyinhao：增量拉取
 * - GET /api/stats：按主播和日期统计
 *
 * 安全变化：
 * 1. 所有客资接口都必须在 Authorization 请求头携带 Bearer 密钥；
 * 2. 读写使用不同密钥，写入方不能批量读取手机号；
 * 3. 日志不输出手机号、抖音号和密钥；
 * 4. 请求大小、频率和字段长度都有限制。
 */
require('dotenv').config();

const crypto = require('node:crypto');
const express = require('express');
const { rateLimit } = require('express-rate-limit');
const mysql = require('mysql2/promise');

const app = express();
app.disable('x-powered-by');
app.set('trust proxy', 1);
app.use(express.json({ limit: '16kb', strict: true }));

const requiredEnvironment = [
  'KEZI_DB_HOST',
  'KEZI_DB_USER',
  'KEZI_DB_PASSWORD',
  'KEZI_DB_NAME',
  'KEZI_WRITE_TOKEN',
  'KEZI_READ_TOKEN'
];
const missingEnvironment = requiredEnvironment.filter(name => !String(process.env[name] || '').trim());
if (missingEnvironment.length) {
  throw new Error(`缺少必要环境变量：${missingEnvironment.join(', ')}`);
}
if (process.env.KEZI_WRITE_TOKEN.length < 32 || process.env.KEZI_READ_TOKEN.length < 32) {
  throw new Error('KEZI_WRITE_TOKEN 和 KEZI_READ_TOKEN 必须至少 32 位');
}
if (process.env.KEZI_WRITE_TOKEN === process.env.KEZI_READ_TOKEN) {
  throw new Error('客资读密钥和写密钥不能相同');
}

const db = mysql.createPool({
  host: process.env.KEZI_DB_HOST,
  port: Number.parseInt(process.env.KEZI_DB_PORT || '3306', 10),
  user: process.env.KEZI_DB_USER,
  password: process.env.KEZI_DB_PASSWORD,
  database: process.env.KEZI_DB_NAME,
  waitForConnections: true,
  connectionLimit: 10,
  enableKeepAlive: true,
  charset: 'utf8mb4'
});

const apiLimiter = rateLimit({
  windowMs: 60 * 1000,
  limit: 120,
  standardHeaders: 'draft-8',
  legacyHeaders: false,
  message: { error: '请求过于频繁，请稍后再试' }
});
app.use('/api', apiLimiter);

function safeTokenEqual(actual, expected) {
  const actualBuffer = Buffer.from(actual || '', 'utf8');
  const expectedBuffer = Buffer.from(expected, 'utf8');
  return actualBuffer.length === expectedBuffer.length
    && crypto.timingSafeEqual(actualBuffer, expectedBuffer);
}

function requireToken(environmentName) {
  return (req, res, next) => {
    const authorization = String(req.headers.authorization || '');
    const token = authorization.startsWith('Bearer ') ? authorization.slice(7) : '';
    if (!safeTokenEqual(token, process.env[environmentName])) {
      return res.status(401).json({ error: '身份验证失败' });
    }
    return next();
  };
}

function cleanText(value, maxLength) {
  if (value === undefined || value === null) {
    return '';
  }
  if (typeof value !== 'string') {
    throw new TypeError('字段必须是字符串');
  }
  const cleaned = value.trim();
  if (cleaned.length > maxLength) {
    throw new RangeError(`字段长度不能超过 ${maxLength} 个字符`);
  }
  return cleaned;
}

function isValidPhone(value) {
  return value === '' || /^1[3-9]\d{9}$/.test(value);
}

function parseIntegerQuery(value, defaultValue, minimum, maximum, fieldName) {
  if (value === undefined) {
    return defaultValue;
  }
  if (typeof value !== 'string' || !/^\d+$/.test(value)) {
    throw new TypeError(`${fieldName} 必须是整数`);
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new RangeError(`${fieldName} 必须在 ${minimum} 到 ${maximum} 之间`);
  }
  return parsed;
}

function isValidDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

app.post('/api/kezi', requireToken('KEZI_WRITE_TOKEN'), async (req, res) => {
  let phone;
  let douyinId;
  let anchor;
  try {
    phone = cleanText(req.body?.phone, 20);
    douyinId = cleanText(req.body?.douyinId, 100);
    anchor = cleanText(req.body?.anchor, 100);
  } catch (error) {
    return res.status(400).json({ error: error.message });
  }
  const received = { phone, douyinId, anchor };

  if (!isValidPhone(phone)) {
    return res.status(400).json({ error: '手机号格式不正确' });
  }
  if (!phone && !douyinId) {
    return res.status(200).json({ message: '接收成功（无有效数据，未写入）', received });
  }

  try {
    await db.execute(
      'INSERT INTO users (phone, douyin_account, anchor) VALUES (?, ?, ?)',
      [phone, douyinId, anchor]
    );
    console.info('客资写入成功');
    return res.json({ message: '接收成功', received });
  } catch (error) {
    console.error('客资数据库写入失败', { code: error.code || 'UNKNOWN' });
    return res.status(500).json({ error: '服务器内部错误' });
  }
});

app.get('/api/douyinhao', requireToken('KEZI_READ_TOKEN'), async (req, res) => {
  let lastId;
  let limit;
  let anchor;
  try {
    lastId = parseIntegerQuery(req.query.lastId, 0, 0, Number.MAX_SAFE_INTEGER, 'lastId');
    limit = parseIntegerQuery(req.query.limit, 100, 1, 500, 'limit');
    anchor = cleanText(req.query.anchor, 100);
  } catch (error) {
    return res.status(400).json({ error: error.message });
  }

  const where = ['id > ?', 'douyin_account != ""'];
  const params = [lastId];
  if (anchor) {
    where.push('anchor = ?');
    params.push(anchor);
  }
  params.push(limit);

  try {
    const [rows] = await db.execute(
      `SELECT id, phone, douyin_account, anchor, created_at
       FROM users
       WHERE ${where.join(' AND ')}
       ORDER BY id ASC
       LIMIT ?`,
      params
    );
    const nextLastId = rows.length ? rows[rows.length - 1].id : lastId;
    return res.json({
      lastId: nextLastId,
      count: rows.length,
      hasMore: rows.length === limit,
      data: rows.map(row => ({
        sourceId: row.id,
        phone: row.phone || '',
        douyinId: row.douyin_account || '',
        anchor: row.anchor || '',
        createdAt: row.created_at
      }))
    });
  } catch (error) {
    console.error('客资增量查询失败', { code: error.code || 'UNKNOWN' });
    return res.status(500).json({ error: '服务器内部错误' });
  }
});

app.get('/api/stats', requireToken('KEZI_READ_TOKEN'), async (req, res) => {
  let anchor;
  let startDate;
  let endDate;
  try {
    anchor = cleanText(req.query.anchor, 100);
    startDate = cleanText(req.query.startDate, 10);
    endDate = cleanText(req.query.endDate, 10);
  } catch (error) {
    return res.status(400).json({ error: error.message });
  }
  if ((startDate && !isValidDate(startDate)) || (endDate && !isValidDate(endDate))) {
    return res.status(400).json({ error: '日期必须是有效的 YYYY-MM-DD' });
  }
  if (startDate && endDate && startDate > endDate) {
    return res.status(400).json({ error: 'startDate 不能晚于 endDate' });
  }

  const where = [];
  const params = [];
  if (anchor) {
    where.push('anchor = ?');
    params.push(anchor);
  }
  if (startDate) {
    where.push('DATE(created_at) >= ?');
    params.push(startDate);
  }
  if (endDate) {
    where.push('DATE(created_at) <= ?');
    params.push(endDate);
  }
  const whereSql = where.length ? `WHERE ${where.join(' AND ')}` : '';

  try {
    let sql;
    if (anchor) {
      sql = `SELECT ? AS anchor, COUNT(*) AS count FROM users ${whereSql}`;
      params.unshift(anchor);
    } else {
      sql = `SELECT anchor, COUNT(*) AS count FROM users ${whereSql}
             GROUP BY anchor ORDER BY count DESC`;
    }
    const [rows] = await db.execute(sql, params);
    return res.json({
      filters: { anchor, startDate, endDate },
      data: rows
    });
  } catch (error) {
    console.error('客资统计查询失败', { code: error.code || 'UNKNOWN' });
    return res.status(500).json({ error: '服务器内部错误' });
  }
});

app.use((error, _req, res, _next) => {
  console.error('客资服务请求处理失败', { type: error.name || 'Error' });
  res.status(error.type === 'entity.too.large' ? 413 : 400).json({ error: '请求格式不正确' });
});

const host = process.env.KEZI_HOST || '127.0.0.1';
const port = Number.parseInt(process.env.KEZI_PORT || '3001', 10);
app.listen(port, host, () => {
  console.info(`客资服务已启动：http://${host}:${port}`);
});
