"""Sequential warm-up and baseline measurements, not a load test."""
from http.cookiejar import CookieJar
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError
from pathlib import Path
from time import perf_counter
from math import ceil
import argparse
import csv
import json
import statistics

def percentile(values,p):
    return sorted(values)[ceil(p*len(values))-1]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--label',choices=['small','work'],required=True)
    p.add_argument('--base',default='http://127.0.0.1:8000')
    p.add_argument('--repeats',type=int,default=30)
    p.add_argument('--warmup',type=int,default=5)
    args=p.parse_args()
    if args.repeats<20 or args.warmup<1:p.error('Need at least 20 measured repetitions and warm-up')
    opener=build_opener(HTTPCookieProcessor(CookieJar()))

    def request(method,path,data=None):
        body=json.dumps(data).encode() if data is not None else None
        req=Request(args.base+path,body,{'Content-Type':'application/json'},method=method)
        start=perf_counter()
        try:
            with opener.open(req,timeout=120) as r:
                payload=r.read()
                total=(perf_counter()-start)*1000
                value=json.loads(payload)
                result={'http_ms':total,'app_ms':float(r.headers['X-App-Ms']),
                        'db_ms':float(r.headers['X-Db-Ms']),'queries':int(r.headers['X-Sql-Count']),
                        'status':r.status}
                result['code_ms']=result['app_ms']-result['db_ms']
                if result['code_ms'] < -0.01:raise RuntimeError('DB timing exceeds app timing')
                return value,result
        except HTTPError as e:
            raise RuntimeError(f'{method} {path}: HTTP {e.code}: {e.read().decode()}') from e

    def login():return request('POST','/api/login',{'username':'demo_staff','password':'demo'})
    def create():return request('POST','/api/tickets',{'title':'Замер ДЗ 1','body':'Заявка измерения','category_id':1})
    def change():
        item,_=create()  # Preparation is outside measured request.
        return request('PATCH',f"/api/tickets/{item['id']}/status",{'status':'in_progress'})
    def comment():
        item,_=create()
        return request('POST',f"/api/tickets/{item['id']}/comments",{'body':'Ответ сотрудника для замера'})
    def logout():
        login()  # Each measured logout starts with the same authorized account.
        return request('POST','/api/logout')

    login()
    operations=[
        ('POST /api/login',login),
        ('GET /api/categories',lambda:request('GET','/api/categories')),
        ('GET /api/tickets?status=new&page=1&size=20',lambda:request('GET','/api/tickets?status=new&page=1&size=20')),
        ('GET /api/tickets/1',lambda:request('GET','/api/tickets/1')),
        ('GET /api/summary',lambda:request('GET','/api/summary')),
        ('POST /api/tickets',create),
        ('PATCH /api/tickets/{id}/status',change),
        ('POST /api/tickets/{id}/comments',comment),
        ('POST /api/logout',logout),
    ]
    all_rows=[]; summary=[]; split=[]
    for name,call in operations:
        for _ in range(args.warmup):call()
        samples=[]
        for i in range(args.repeats):
            _,result=call()
            result.update(operation=name,sample=i+1)
            samples.append(result);all_rows.append(result)
        times=[r['http_ms'] for r in samples]
        s={'operation':name,'n':len(times),'p50_ms':round(statistics.median(times),3),
           'p95_ms':round(percentile(times,.95),3),'max_ms':round(max(times),3)}
        summary.append(s)
        # One actual request near the median server time; its components belong to the same request.
        representative=sorted(samples,key=lambda r:r['app_ms'])[len(samples)//2]
        split.append({k:representative[k] for k in ['operation','sample','app_ms','db_ms','code_ms','queries','http_ms']})
        print(f"{name}: n={s['n']} p50={s['p50_ms']} ms p95={s['p95_ms']} ms max={s['max_ms']} ms",flush=True)
    out=Path('results');out.mkdir(exist_ok=True)
    for suffix,rows in [('raw',all_rows),('summary',summary),('split',split)]:
        with (out/f'{args.label}_{suffix}.csv').open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(f'Warmed up {args.warmup} times per operation, excluded from metrics.')
    print(f'Test writes: tickets +{3*(args.warmup+args.repeats)}, comments +{args.warmup+args.repeats}; preparation included in these counts.')
    print(f'Results saved to results/{args.label}_*.csv')

if __name__=='__main__':main()
