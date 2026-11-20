import argparse
import csv
from pathlib import Path
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument('folder', type=Path)
args = parser.parse_args()
rows = []
seen = set()
for path in sorted(args.folder.glob('*/row.csv')):
    with path.open(encoding='utf-8', newline='') as file:
        row = next(csv.DictReader(file))
    if row['slo'] == 'INVALID':
        print(f'Пропущена некорректная ступень: {path.parent.name}')
        continue
    if row['seconds'] != '30':
        print(f'Пропущен короткий запуск: {path.parent.name}')
        continue
    key = row['mode'], int(row['rate'])
    if key in seen:
        raise SystemExit(f'Дубликат: {key}. Разнесите повторы по отдельным папкам OUT_ROOT.')
    seen.add(key)
    rows.append(row)
if not rows:
    raise SystemExit('Нет подходящих ступеней по 30 секунд')
rows.sort(key=lambda r: (r['mode'] != 'mixed', int(r['rate'])))
with (args.folder / 'steps.csv').open('w', encoding='utf-8', newline='') as file:
    writer = csv.DictWriter(file, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

# Draw each p95 series without external Python packages.
for mode in ['mixed', 'heavy']:
    series = [r for r in rows if r['mode'] == mode]
    if not series:
        continue
    root = ET.Element('svg', xmlns='http://www.w3.org/2000/svg', width='840', height='440', viewBox='0 0 840 440')
    def add(kind, content=None, **attrs):
        el = ET.SubElement(root, kind, {k.replace('_', '-'): str(v) for k, v in attrs.items()})
        if content is not None:
            el.text = str(content)
    maxx = max(int(r['rate']) for r in series)
    maxy = max(550.0, 1.08 * max(float(r['p95_ms']) for r in series))
    x = lambda value: 78 + 716 * float(value) / maxx
    y = lambda value: 366 - 285 * float(value) / maxy
    add('rect', width=840, height=440, fill='white')
    add('text', f"denis_kuleshin · {'Смешанный профиль' if mode == 'mixed' else 'Сводка'}", x=78, y=35, font_family='Arial', font_size=23)
    for j in range(6):
        value = maxy * j / 5
        add('line', x1=78, y1=y(value), x2=794, y2=y(value), stroke='#d7dce0')
        add('text', f'{value:.0f}', x=68, y=y(value) + 4, text_anchor='end', font_size=13, font_family='Arial')
    for j in range(5):
        value = maxx * j / 4
        add('text', f'{value:g}', x=x(value), y=390, text_anchor='middle', font_size=13, font_family='Arial')
    add('line', x1=78, y1=y(500), x2=794, y2=y(500), stroke='#a54031', stroke_dasharray='6 4')
    add('text', '500 мс', x=86, y=y(500)-6, font_family='Arial', font_size=13, fill='#a54031')
    add('text', 'p95, мс', x=78, y=67, font_family='Arial', font_size=14)
    add('text', 'Заданная частота, зап/с', x=794, y=419, text_anchor='end', font_family='Arial', font_size=14)
    points = [(x(r['rate']), y(r['p95_ms'])) for r in series]
    add('polyline', points=' '.join(f'{a:.1f},{b:.1f}' for a,b in points), fill='none', stroke='#1f6096', stroke_width=3)
    for (a,b), r in zip(points, series):
        add('circle', cx=a, cy=b, r=4, fill='#1f6096' if r['slo']=='PASS' else '#a54031')
    ET.ElementTree(root).write(args.folder / f'p95-{mode}.svg', encoding='utf-8', xml_declaration=True)
