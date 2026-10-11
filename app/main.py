from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Literal
import os
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.sessions import SessionMiddleware
from app.db import Metrics, Store, connection
from app.rules import password_matches, reaction, valid_transition

app = FastAPI(title='denis_kuleshin Заявки в службу поддержки')
app.add_middleware(SessionMiddleware, secret_key=os.environ.get('SESSION_SECRET', 'test-only-secret'),
                   session_cookie='denis_kuleshin_session', same_site='strict')

@app.middleware('http')
async def measure_server(request: Request, call_next):
    request.state.metrics = Metrics()
    start = perf_counter()
    response = await call_next(request)
    response.headers['X-App-Ms'] = f'{(perf_counter()-start)*1000:.3f}'
    response.headers['X-Db-Ms'] = f'{request.state.metrics.db_ms:.3f}'
    response.headers['X-Sql-Count'] = str(request.state.metrics.queries)
    response.headers['Cache-Control'] = 'no-store'
    return response

def get_store(request: Request):
    with connection() as conn:
        yield Store(conn, request.state.metrics)

def account(request: Request):
    uid = request.session.get('uid')
    if not uid:
        raise HTTPException(401, 'Требуется вход')
    return {'id': uid, 'is_staff': request.session['is_staff']}

class Login(BaseModel):
    username: str
    password: str

class TicketInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    category_id: int = Field(gt=0)

    @field_validator('title', 'body')
    @classmethod
    def clean(cls, value):
        if not value.strip():
            raise ValueError('Пустой текст')
        return value.strip()

class CommentInput(BaseModel):
    body: str = Field(min_length=1, max_length=10000)

    @field_validator('body')
    @classmethod
    def clean(cls, value):
        if not value.strip():
            raise ValueError('Пустой текст')
        return value.strip()

class StatusInput(BaseModel):
    status: Literal['new', 'in_progress', 'closed']

@app.get('/', include_in_schema=False)
def ui():
    return FileResponse(Path(__file__).parent / 'index.html')

@app.post('/api/login')
def login(data: Login, request: Request, db=Depends(get_store)):
    user = db.one('SELECT * FROM users WHERE username=%s', (data.username,))
    if not user or not password_matches(data.password, user['password_hash']):
        raise HTTPException(401, 'Неверный логин или пароль')
    request.session.clear()
    request.session.update(uid=user['id'], is_staff=user['is_staff'])
    return {'username': user['username'], 'is_staff': user['is_staff'], 'prefix': 'denis_kuleshin'}

@app.post('/api/logout')
def logout(request: Request, user=Depends(account)):
    request.session.clear()
    return {'ok': True}

@app.get('/api/categories')
def categories(user=Depends(account), db=Depends(get_store)):
    return {'items': db.query('SELECT id,name,reaction_hours FROM categories ORDER BY id')}

@app.get('/api/tickets')
def tickets(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
            status: Literal['new','in_progress','closed'] | None = None,
            category_id: int | None = Query(None, gt=0), user=Depends(account), db=Depends(get_store)):
    where, params = [], []
    if status:
        where.append('t.status=%s'); params.append(status)
    if category_id:
        where.append('t.category_id=%s'); params.append(category_id)
    condition = (' WHERE ' + ' AND '.join(where)) if where else ''
    total = db.one('SELECT count(*) AS n FROM tickets t' + condition, params)['n']
    rows = db.query('SELECT t.id,t.title,t.status,t.created_at,c.name AS category,u.username '
                    'FROM tickets t JOIN categories c ON c.id=t.category_id JOIN users u ON u.id=t.user_id'
                    + condition + ' ORDER BY t.id LIMIT %s OFFSET %s',
                    [*params, size, (page-1)*size])
    return {'items': rows, 'total': total, 'page': page, 'size': size}

def ticket_row(ticket_id, db):
    row = db.one('SELECT t.*,c.name AS category,c.reaction_hours,u.username '
                 'FROM tickets t JOIN categories c ON c.id=t.category_id JOIN users u ON u.id=t.user_id '
                 'WHERE t.id=%s', (ticket_id,))
    if not row:
        raise HTTPException(404, 'Заявка не найдена')
    return row

@app.get('/api/tickets/{ticket_id}')
def ticket(ticket_id: int, user=Depends(account), db=Depends(get_store)):
    row = ticket_row(ticket_id, db)
    comments = db.query('SELECT c.id,c.body,c.created_at,u.username,u.is_staff '
                        'FROM comments c JOIN users u ON u.id=c.user_id WHERE c.ticket_id=%s ORDER BY c.created_at,c.id',
                        (ticket_id,))
    return {'ticket': row, 'comments': comments,
            'reaction': reaction(row['created_at'], comments, row['reaction_hours'], datetime.now(timezone.utc))}

@app.post('/api/tickets', status_code=201)
def create_ticket(data: TicketInput, user=Depends(account), db=Depends(get_store)):
    if not db.one('SELECT id FROM categories WHERE id=%s', (data.category_id,)):
        raise HTTPException(404, 'Категория не найдена')
    return db.one("INSERT INTO tickets(user_id,category_id,title,body,status,created_at) "
                   "VALUES(%s,%s,%s,%s,'new',now()) RETURNING *",
                   (user['id'], data.category_id, data.title, data.body))

@app.patch('/api/tickets/{ticket_id}/status')
def change_status(ticket_id: int, data: StatusInput, user=Depends(account), db=Depends(get_store)):
    row = ticket_row(ticket_id, db)
    if not valid_transition(row['status'], data.status):
        raise HTTPException(400, 'Допустимы переходы new → in_progress → closed')
    changed = db.one('UPDATE tickets SET status=%s WHERE id=%s AND status=%s RETURNING *',
                     (data.status, ticket_id, row['status']))
    if not changed:
        raise HTTPException(409, 'Статус изменился одновременно с запросом')
    return changed

@app.post('/api/tickets/{ticket_id}/comments', status_code=201)
def add_comment(ticket_id: int, data: CommentInput, user=Depends(account), db=Depends(get_store)):
    ticket_row(ticket_id, db)
    return db.one('INSERT INTO comments(ticket_id,user_id,body,created_at) VALUES(%s,%s,%s,now()) RETURNING *',
                   (ticket_id, user['id'], data.body))

@app.get('/api/summary')
def summary(user=Depends(account), db=Depends(get_store)):
    rows = db.query("""WITH first_reply AS (
      SELECT c.ticket_id, min(c.created_at) AS replied_at
      FROM comments c JOIN users u ON u.id=c.user_id
      WHERE u.is_staff GROUP BY c.ticket_id
    )
    SELECT cat.id,cat.name,cat.reaction_hours,
      count(t.id) FILTER (WHERE t.status<>'closed') AS open_count,
      count(t.id) FILTER (WHERE t.status<>'closed' AND
        COALESCE(f.replied_at,now())-t.created_at > make_interval(hours=>cat.reaction_hours)) AS violated_count
    FROM categories cat LEFT JOIN tickets t ON t.category_id=cat.id
    LEFT JOIN first_reply f ON f.ticket_id=t.id
    GROUP BY cat.id,cat.name,cat.reaction_hours ORDER BY cat.id""")
    for r in rows:
        r['violated_share'] = round(r['violated_count']/r['open_count'], 4) if r['open_count'] else 0
    return {'items': rows, 'definition': 'Доля нарушений среди открытых заявок каждой категории'}
