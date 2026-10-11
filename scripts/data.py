from pathlib import Path
from datetime import datetime, timezone, timedelta
import argparse
import hashlib
import json
import random
from app.db import connection
from app.rules import password_hash

TABLES = ('users', 'categories', 'tickets', 'comments')

def counts(conn):
    return {table: conn.execute(f'SELECT count(*) AS n FROM {table}').fetchone()['n'] for table in TABLES}

def seed(conn, size):
    conn.execute((Path(__file__).resolve().parent.parent / 'schema.sql').read_text(encoding='utf-8'))
    # Only the four tables in this project's named schema are reset.
    conn.execute('TRUNCATE comments,tickets,categories,users RESTART IDENTITY')
    n_users,n_categories,n_tickets = (50,5,300) if size=='small' else (3000,10,50000)
    rng = random.Random(20261008)
    origin = datetime(2026,10,1,tzinfo=timezone.utc)
    hashed = password_hash('demo')
    with conn.cursor().copy('COPY users(id,username,password_hash,is_staff) FROM STDIN') as cp:
        for i in range(1,n_users+1):
            cp.write_row((i,'demo_staff' if i==1 else 'demo_user' if i==2 else f'user_{i}',hashed,i==1 or i%5==0))
    with conn.cursor().copy('COPY categories(id,name,reaction_hours) FROM STDIN') as cp:
        for i in range(1,n_categories+1):cp.write_row((i,f'Категория {i}',[1,2,4,8,24][(i-1)%5]))
    ticket_data=[]
    with conn.cursor().copy('COPY tickets(id,user_id,category_id,title,body,status,created_at) FROM STDIN') as cp:
        for i in range(1,n_tickets+1):
            category=(i-1)%n_categories+1
            created=origin-timedelta(minutes=rng.randrange(30*24*60))
            status=('new','in_progress','closed')[(i-1)%3]
            cp.write_row((i,2+rng.randrange(n_users-1),category,f'Заявка {i}',f'Учебное описание заявки {i}',status,created))
            ticket_data.append((i,category,created))
    with conn.cursor().copy('COPY comments(id,ticket_id,user_id,body,created_at) FROM STDIN') as cp:
        for ticket_id,category,created in ticket_data:
            norm=[1,2,4,8,24][(category-1)%5]
            for j in range(3):
                # Mix user-only threads and first staff replies before/after the norm.
                author=1 if j==1 and ticket_id%4!=0 else 2
                hours=(norm*0.5 if ticket_id%2 else norm*1.5) if j==1 else (0.1 if j==0 else norm*2)
                cp.write_row(((ticket_id-1)*3+j+1,ticket_id,author,f'Комментарий {j+1} к заявке {ticket_id}',created+timedelta(hours=hours)))
    for table in TABLES:
        conn.execute(f"SELECT setval(pg_get_serial_sequence('{table}','id'),(SELECT max(id) FROM {table}),true)")
    return counts(conn)

def fingerprint(conn):
    result={}
    for table in TABLES:
        h=hashlib.sha256()
        # Fixed ordering and fixed time zone make identical rows produce identical hashes.
        with conn.cursor() as cur:
            cur.execute(f'SELECT * FROM {table} ORDER BY id')
            for row in cur:
                h.update((json.dumps(row,sort_keys=True,ensure_ascii=False,default=str)+'\n').encode())
        result[table]=h.hexdigest()
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['seed','counts','fingerprint'])
    parser.add_argument('--size',choices=['small','work'])
    args=parser.parse_args()
    with connection() as conn:
        conn.execute("SET TIME ZONE 'UTC'")
        if args.command=='seed':
            if not args.size:parser.error('seed requires --size')
            result=seed(conn,args.size)
        elif args.command=='counts':result=counts(conn)
        else:result=fingerprint(conn)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
