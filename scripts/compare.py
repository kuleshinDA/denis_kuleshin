from pathlib import Path
import csv
import json

def read(name):
    with (Path('results')/name).open(encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def main():
    small={r['operation']:r for r in read('small_summary.csv')}
    rows=[]
    for r in read('work_summary.csv'):
        s=small[r['operation']]
        result={'operation':r['operation'],
                'p50_small_ms':s['p50_ms'],'p95_small_ms':s['p95_ms'],'max_small_ms':s['max_ms'],
                'p50_work_ms':r['p50_ms'],'p95_work_ms':r['p95_ms'],'max_work_ms':r['max_ms'],
                'growth_p50':round(float(r['p50_ms'])/float(s['p50_ms']),3)}
        rows.append(result)
        print(f"{r['operation']}: p50 {s['p50_ms']} → {r['p50_ms']} ms; growth {result['growth_p50']}x")
    with Path('results/comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('\nTable 6 candidates: actual individual requests on working dataset')
    for r in read('work_split.csv'):
        print(f"{r['operation']}: app={r['app_ms']} ms, DB={r['db_ms']} ms, other={r['code_ms']} ms, SQL={r['queries']}, sample={r['sample']}")
    print('\nTable 4: record counts BEFORE timing runs')
    for label in ['small','work']:
        p=Path(f'results/{label}_before.json')
        if p.exists():print(label,json.loads(p.read_text()))

if __name__=='__main__':main()
