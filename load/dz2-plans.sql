\set ON_ERROR_STOP on
\pset pager off
SET search_path TO denis_kuleshin;
\echo 'Сводка: запрос из app/main.py, функция summary'
EXPLAIN (ANALYZE, BUFFERS)
WITH first_reply AS (
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
GROUP BY cat.id,cat.name,cat.reaction_hours ORDER BY cat.id;

\echo 'Карточка: запрос комментариев из ticket, ID 1 как в ДЗ1'
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.id,c.body,c.created_at,u.username,u.is_staff
FROM comments c JOIN users u ON u.id=c.user_id
WHERE c.ticket_id=1 ORDER BY c.created_at,c.id;

\echo 'Список: подсчёт со статусом new из tickets'
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*) AS n FROM tickets t WHERE t.status='new';

\echo 'Список: выдача первой страницы из tickets'
EXPLAIN (ANALYZE, BUFFERS)
SELECT t.id,t.title,t.status,t.created_at,c.name AS category,u.username
FROM tickets t JOIN categories c ON c.id=t.category_id JOIN users u ON u.id=t.user_id
WHERE t.status='new' ORDER BY t.id LIMIT 20 OFFSET 0;
