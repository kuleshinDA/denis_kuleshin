import http from 'k6/http';
import exec from 'k6/execution';
import { Counter, Rate, Trend } from 'k6/metrics';

const mode = __ENV.MODE || 'mixed';
const rate = Number(__ENV.RATE || '2');
const seconds = Number(__ENV.SECONDS || '30');
const vus = Number(__ENV.VUS || Math.max(20, rate));
const base = __ENV.BASE || 'http://127.0.0.1:8082';
const user = __ENV.TEST_USER || 'demo_staff';
const password = __ENV.TEST_PASSWORD || 'demo';
if (!['mixed', 'heavy'].includes(mode) || ![rate, seconds, vus].every(n => Number.isInteger(n) && n > 0)) {
  throw new Error('Укажите MODE=mixed|heavy, RATE, SECONDS и VUS — положительные целые числа');
}
if (mode === 'mixed' && Math.ceil(rate * seconds / 100) * 12 > 16667) {
  throw new Error('Не хватает уникальных заявок со статусом new на эту ступень');
}

const sent = new Counter('dz2_sent');
const done = new Counter('dz2_done');
const failed = new Rate('dz2_errors');
const latency = new Trend('dz2_latency', true);
const appMs = new Trend('dz2_app_ms', true);
const dbMs = new Trend('dz2_db_ms', true);
const scenario = { executor: 'constant-arrival-rate', rate, timeUnit: '1s',
  duration: `${seconds}s`, preAllocatedVUs: vus, gracefulStop: '12s' };
export const options = {
  scenarios: mode === 'mixed' ? { mixed: { ...scenario, exec: 'mixed' } }
                              : { heavy: { ...scenario, exec: 'heavy' } },
  thresholds: { dz2_latency: ['p(95)<500'], dz2_errors: ['rate<0.01'] },
  summaryTrendStats: ['med', 'p(95)', 'max'],
};

export function setup() {
  const res = http.post(`${base}/api/login`, JSON.stringify({ username: user, password }), {
    headers: { 'Content-Type': 'application/json' }, redirects: 0, timeout: '10s',
    tags: { phase: 'setup', name: 'login' },
  });
  const cookie = res.cookies.denis_kuleshin_session;
  if (res.status !== 200 || !cookie || !cookie.length) throw new Error(`Вход: HTTP ${res.status}`);
  if (res.json('prefix') !== 'denis_kuleshin') throw new Error('Проверьте адрес: это не стенд denis_kuleshin');
  return { session: cookie[0].value };
}

function request(session, method, path, operation, status, body = null) {
  const tags = { operation, name: operation, phase: 'load' };
  sent.add(1, tags);
  const start = Date.now();
  const res = http.request(method, `${base}${path}`, body === null ? null : JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    cookies: { denis_kuleshin_session: { value: session, replace: true } },
    redirects: 0, timeout: '10s', tags, responseCallback: http.expectedStatuses(status),
  });
  latency.add(Date.now() - start, tags);
  done.add(1, tags);
  failed.add(res.status !== status, tags);
  for (const [header, trend] of [['X-App-Ms', appMs], ['X-Db-Ms', dbMs]]) {
    const value = res.headers[header];
    if (value !== undefined && Number.isFinite(Number(value))) trend.add(Number(value), tags);
  }
  if (res.status !== status) console.warn(`${operation}: HTTP ${res.status}, ожидался ${status}, ${res.error || ''}`);
}

export function mixed({ session }) {
  const i = exec.scenario.iterationInTest;
  const pick = (37 * (i % 100) + 17) % 100;
  const id = 1 + ((i * 31) % 50000);
  if (pick < 35) return request(session, 'GET', '/api/tickets?status=new&page=1&size=20', 'list', 200);
  if (pick < 60) return request(session, 'GET', `/api/tickets/${id}`, 'detail', 200);
  if (pick < 75) return request(session, 'POST', `/api/tickets/${id}/comments`, 'comment', 201,
    { body: `Замер ДЗ2 ${i}` });
  if (pick < 87) {
    // Unique seeded tickets with status new; one PATCH per ticket.
    const patchId = 1 + 3 * (12 * Math.floor(i / 100) + pick - 75);
    return request(session, 'PATCH', `/api/tickets/${patchId}/status`, 'status', 200, { status: 'in_progress' });
  }
  if (pick < 95) return request(session, 'POST', '/api/tickets', 'create', 201,
    { title: `Замер ДЗ2 ${i}`, body: 'Учебная заявка', category_id: 1 + i % 10 });
  if (pick < 98) return request(session, 'GET', '/api/categories', 'categories', 200);
  return heavy({ session });
}

export function heavy({ session }) {
  return request(session, 'GET', '/api/summary', 'summary', 200);
}

export function handleSummary(data) {
  function metrics(name) { return (data.metrics[name] || { values: {} }).values; }
  const t = metrics('dz2_latency');
  const transmitted = metrics('dz2_sent').count || 0;
  const completed = metrics('dz2_done').count || 0;
  const dropped = metrics('dropped_iterations').count || 0;
  const err = metrics('dz2_errors');
  const passed = t['p(95)'] < 500 && err.rate < 0.01;
  const complete = completed > 0 && completed === transmitted;
  const row = [mode, rate, seconds, t.med, t['p(95)'], t.max, err.rate === undefined ? '' : err.rate * 100,
    dropped, transmitted / seconds, transmitted, completed, complete ? (passed ? 'PASS' : 'FAIL') : 'INVALID'];
  return {
    stdout: `denis_kuleshin | ${mode} | цель ${rate} req/s | факт ${(transmitted / seconds).toFixed(2)} req/s | p50=${t.med} ms | p95=${t['p(95)']} ms | max=${t.max} ms | error=${row[6]}% | dropped=${dropped} | ${row[11]}\n`,
    '/out/k6-summary.json': JSON.stringify(data, null, 2),
    '/out/row.csv': 'mode,rate,seconds,p50_ms,p95_ms,max_ms,errors_pct,dropped,actual_rps,sent,completed,slo\n' + row.join(',') + '\n',
  };
}
