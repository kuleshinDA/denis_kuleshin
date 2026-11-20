from collections import Counter
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding='utf-8'))
frames = data['shared']['frames']
counts, app = Counter(), Counter()
all_samples = 0
for profile in data['profiles']:
    if profile['type'] != 'sampled':
        continue
    for stack in profile['samples']:
        if not stack:
            continue
        all_samples += 1
        counts[stack[-1]] += 1
        names = set()
        for idx in stack:
            f = frames[idx]
            file = f.get('file') or ''
            if '/app/main.py' in file or '/app/db.py' in file or '/app/rules.py' in file:
                names.add((f['name'], file))
        app.update(names)
if not all_samples:
    raise SystemExit('В профиле нет непустых снимков. Проверьте pyspy.log и время нагрузки.')
print(f'Непустых снимков по всем потокам: {all_samples}')
print('Функции своего приложения (доля стеков с функцией, включая дочерние вызовы):')
for (name, filename), n in app.most_common(15):
    print(f'{100 * n / all_samples:6.2f}%  {filename}  {name}')
print('Верхушки стеков (доли не пересекаются):')
for idx, n in counts.most_common(15):
    f = frames[idx]
    print(f"{100 * n / all_samples:6.2f}%  {f.get('file', '')}:{f.get('line', '')}  {f['name']}")
