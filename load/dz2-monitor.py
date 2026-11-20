import csv
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys
from threading import Event, Thread
from time import monotonic

api, db, folder = sys.argv[1:]
folder = Path(folder)
stop = Event()
signal.signal(signal.SIGTERM, lambda *_: stop.set())
signal.signal(signal.SIGINT, lambda *_: stop.set())

def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

def connections():
    sql = """SELECT count(*), count(*) FILTER (WHERE state='active'),
                     count(*) FILTER (WHERE state='active' AND wait_event_type='Lock')
              FROM pg_stat_activity WHERE datname='denis_kuleshin'
              AND backend_type='client backend' AND pid<>pg_backend_pid();"""
    cmd = ['docker', 'exec', db, 'psql', '-XAt', '-F', '\t', '-U', 'denis_kuleshin',
           '-d', 'denis_kuleshin', '-v', 'ON_ERROR_STOP=1', '-c', sql]
    with (folder / 'connections.tsv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['utc', 'total', 'active', 'active_waiting_for_lock'])
        while not stop.is_set():
            tick = monotonic()
            try:
                res = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=2)
                writer.writerow([timestamp(), *res.stdout.strip().split('\t')])
                f.flush()
            except (subprocess.SubprocessError, OSError) as e:
                print(f'{timestamp()} pg_stat_activity: {e}', file=sys.stderr)
            stop.wait(max(0, 1.5 - (monotonic() - tick)))

thread = Thread(target=connections, daemon=True)
thread.start()
fmt = '{{.ID}}\t{{.CPUPerc}}\t{{.MemUsage}}'
with (folder / 'resources.tsv').open('w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f, delimiter='\t')
    writer.writerow(['utc', 'service', 'cpu_pct', 'memory_used_limit'])
    while not stop.is_set():
        tick = monotonic()
        try:
            result = subprocess.run(['docker', 'stats', '--no-stream', '--format', fmt, api, db],
                                    capture_output=True, check=True, text=True, timeout=4)
            now = timestamp()
            for line in result.stdout.splitlines():
                cid, cpu, mem = line.split('\t')
                if cpu != '--':
                    writer.writerow([now, 'api' if api.startswith(cid) else 'db', cpu.strip('%'), mem])
            f.flush()
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            print(f'{timestamp()} docker stats: {e}', file=sys.stderr)
        stop.wait(max(0, 1.5 - (monotonic() - tick)))
thread.join(timeout=3)
