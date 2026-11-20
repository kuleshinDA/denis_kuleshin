# Сервис заявок в службу поддержки

Учебный сервис ДЗ 1, вариант 2. Автор — Кулешин Денис Алексеевич,
БИСТ-24-ПО-2. Префикс — `denis_kuleshin`.
Сервис создаёт заявки с категорией, переводит их по статусам и хранит переписку.
Карточка считает срок до первого ответа сотрудника и сравнивает его с нормативом
категории. Сводка считает открытые заявки и долю нарушений по всем данным.

## Требования

Ubuntu в WSL и работающий Docker с Docker Compose. Подходит Docker Engine,
установленный внутри Ubuntu, либо Docker Desktop с Linux containers и интеграцией
Ubuntu.
Для всех сравниваемых замеров используйте один и тот же движок и его ресурсы.
В контейнерах: Python 3.12.10, FastAPI 0.115.12, PostgreSQL 16.8, Psycopg 3.2.6.
Остальные зависимости закреплены в requirements.txt. 

## Установка и запуск

Из корня проекта в терминале Ubuntu:

```bash
docker version
docker run --rm python:3.12.10-slim python -c 'import secrets; print("DB_PASSWORD="+secrets.token_hex(16)); print("SESSION_SECRET="+secrets.token_hex(32)); print("APP_PORT=8082")' > .env
docker compose config --quiet
docker compose up -d --build
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U denis_kuleshin -d denis_kuleshin < schema.sql
docker compose exec -T api python -m scripts.data seed --size small
```

Команда создания `.env` нужна один раз при первом запуске. При повторном запуске
используйте уже созданный файл: пароль в существующем томе PostgreSQL не меняется
от перезаписи `.env`.

Наполнение **заменяет данные четырёх таблиц схемы denis_kuleshin**. Это отдельная
база и отдельный том этого проекта. Не используйте команду для другой базы.

```bash
docker compose exec -T api python -m scripts.data seed --size work
docker compose exec -T api python -m scripts.data counts
```

Остановка с сохранением данных: `docker compose down`. Не добавляйте `-v`:
эта опция удаляет том с базой.

## Переменные окружения

| Переменная | Назначение | Пример |
|---|---|---|
| DB_PASSWORD | Пароль отдельной учебной базы | changeme |
| SESSION_SECRET | Подпись сессионной cookie | changeme |
| APP_PORT | Порт интерфейса на Windows | 8082 |

Имя проекта Compose, имя БД и имя схемы — `denis_kuleshin`. Доступ к данным —
прямые параметризованные SQL-запросы через Psycopg; ORM нет.
Реальный `.env` в Git не попадает. `.env.example` содержит только примеры.

## Проверка работоспособности и тесты

Интерфейс: http://localhost:8082. Учётная запись замеров: `demo_staff` / `demo`.
Для проверки переписки от обычного пользователя: `demo_user` / `demo`.
Есть список с фильтром и пагинацией, карточка со связанными данными и сводка.
Условия перехода статусов этого сервиса: `new → in_progress → closed`.
Пустой текст, неизвестная категория и недопустимый переход отклоняются.
Норматив нарушен, когда время до первого ответа сотрудника больше норматива;
при отсутствии ответа сравнивается уже прошедшее ожидание. Ровно на границе
нарушения нет. В сводке знаменатель — открытые заявки категории.

```bash
docker compose exec -T api python -m pytest -q
```

Тесты правил и контракта используют подготовленные данные и не требуют ручного
наполнения базы. Тесты контракта подменяют доступ к БД; SQL и интерфейс дополнительно
проверяются на реальном PostgreSQL после запуска. Не выдавайте модульный прогон
за проверку всего развёртывания.

## Измерение и повторяемость

```bash
mkdir -p results screenshots
docker compose exec -T api python -m scripts.data seed --size small
docker compose exec -T api python -m scripts.data fingerprint > results/first.sha256
docker compose exec -T api python -m scripts.data seed --size small
docker compose exec -T api python -m scripts.data fingerprint > results/second.sha256
diff -u results/first.sha256 results/second.sha256
```

Сначала создайте малое наполнение, затем снимайте первый fingerprint. Если до
него выполняли операции записи вручную, отпечатки сравнят разные данные.
Полный порядок сброса перед сериями приведён в гайде.

```bash
docker compose exec -T api python -m scripts.data counts > results/small_before.json
docker compose exec -T api python -m scripts.measure --label small --warmup 5 --repeats 30
docker compose exec -T api python -m scripts.data counts > results/small_after.json
docker compose exec -T api python -m scripts.data seed --size work
docker compose exec -T api python -m scripts.data counts > results/work_before.json
docker compose exec -T api python -m scripts.measure --label work --warmup 5 --repeats 30
docker compose exec -T api python -m scripts.data counts > results/work_after.json
docker compose exec -T api python -m scripts.compare
```

Для каждой из 9 API-операций выполняются 5 прогревочных запросов и 30 измеряемых
последовательных повторов. Прогрев не входит в p50/p95/max. Авторизация одинакова
в обеих сериях. Для смены статуса и комментария заранее создаётся новая заявка;
подготовка не входит во время целевого запроса, но её записи учитываются.
За полную серию добавляются 105 заявок и 35 комментариев. Список, карточка и
сводка измеряются до этих записей. Для повторной серии восстановите наполнение.

`*_raw.csv` — все 30 запросов, `*_summary.csv` — p50/p95/max,
`comparison.csv` — два объёма и рост p50. P50 — медиана; p95 — значение с номером
ceil(0.95 × N) в отсортированном ряду. На 30 повторах это 29-е значение.

`*_split.csv` содержит по одной реальной операции около медианы серверного времени:
`app_ms` — весь измеряемый интервал внутри приложения, `db_ms` — сумма интервалов
execute/fetch, `code_ms = app_ms - db_ms`, `queries` — количество SQL-запросов.
Они взяты из одного запроса; нельзя вычитать p95 БД из p95 HTTP.
DB-время этого способа включает обмен с драйвером и получение строк и не является
чистым CPU-временем PostgreSQL. Остаток включает установку соединения, код,
сериализацию и прочие накладные расходы внутри приложения. HTTP-время таблицы 5
измеряется отдельно клиентом и включает передачу ответа.

## Программный интерфейс

Данные запросов записи — JSON. Успешный вход устанавливает сессионную cookie.
Другие API-операции требуют её; без входа — 401. Некорректные типы/параметры — 422.

| Метод и путь | Параметры | Ответ | Ошибки |
|---|---|---|---|
| POST /api/login | username, password | 200: username, is_staff, prefix; cookie | 401, 422 |
| POST /api/logout | нет | 200: {"ok": true}; удаление сессии | 401 |
| GET /api/categories | нет | 200: items с id, name, reaction_hours | 401 |
| GET /api/tickets | page≥1, size=1..100, status, category_id | 200: items, total, page, size | 401, 422 |
| GET /api/tickets/{id} | id | 200: ticket, comments, reaction | 401, 404, 422 |
| POST /api/tickets | title, body, category_id | 201: созданная заявка, status=new | 401, 404, 422 |
| PATCH /api/tickets/{id}/status | status | 200: изменённая заявка | 400, 401, 404, 409, 422 |
| POST /api/tickets/{id}/comments | body | 201: созданный комментарий | 401, 404, 422 |
| GET /api/summary | нет | 200: items с open_count, violated_count, violated_share | 401 |

`GET /` отдаёт клиентскую страницу; вычисления экранов выполняют описанные API-
операции. Автоматические /docs и /openapi.json — служебная документация, не операции
предметного контракта и не отдельные целевые замеры.

## Файлы проекта

`schema.sql` — четыре таблицы и связи. `app/rules.py` — срок реакции и переходы
статусов. `app/db.py` — доступ к PostgreSQL и счётчик запросов. `app/main.py` — API,
сессия и диагностика времени. `app/index.html` — клиентская часть.
`scripts/data.py` — два наполнения, счётчики, хеши. `scripts/measure.py` — замеры.
`scripts/compare.py` — сопоставление. `tests/` — правила и контракт.
Специальные индексы, кеширование, фоновые очереди и внешнее хранение файлов не
используются. README описывает учебный пример, его команды и правила.

## ДЗ 2: нагрузочное испытание

Испытание проводится на рабочем наполнении в Ubuntu с Docker Engine. Ступень заменяет данные в отдельной учебной БД `denis_kuleshin`. Не запускайте две ступени одновременно. Скрипт использует образ `grafana/k6:0.55.0`, вход `demo_staff`, адрес `http://127.0.0.1:8082`; при нестандартном порте можно задать `BASE`.

```bash
docker compose up -d --build --wait
bash load/dz2-stage.sh mixed 2
bash load/dz2-stage.sh heavy 2
python3 load/dz2-results.py results/dz2
```

Аргументы ступени: режим (`mixed` или `heavy`), запросы/с, длительность в секундах (по умолчанию 30). Вход выполняется до начала нагрузки. Пороги записаны в `load/dz2.js`: p95 < 500 мс, доля неожиданных HTTP-результатов < 1%. Каждая ступень сохраняет строку CSV, метрики k6, ряд ресурсов, соединения PostgreSQL и логи в `results/dz2/`. Между ступенями дождитесь возврата CPU к простою. Для отдельной диагностической серии задайте `OUT_ROOT`; для проверки запаса виртуальных пользователей — `VUS`.

Профиль сводки для отчёта снят на последней пройденной ступени: 128 зап/с.
Чтобы повторить замер, запустите тест на 30 секунд с записью профиля на 15 секунд.
В этом запуске py-spy снимает стеки с частотой 19 Гц в неблокирующем режиме.

```bash
docker build -t denis_kuleshin-pyspy:0.4.1 - < load/dz2-pyspy.Dockerfile
PROFILE=1 OUT_ROOT=results/dz2-profile-light bash -c "$(sed 's/--rate 99/--rate 19 --nonblocking/' load/dz2-stage.sh)" load/dz2-stage.sh heavy 128
```

Профиль в формате Speedscope сохраняется как `profile.json` в каталоге запуска,
путь к которому выводится после теста.
