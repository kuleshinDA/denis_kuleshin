CREATE SCHEMA IF NOT EXISTS denis_kuleshin;
SET search_path TO denis_kuleshin;
CREATE TABLE IF NOT EXISTS users (
  id bigserial PRIMARY KEY,
  username text NOT NULL,
  password_hash text NOT NULL,
  is_staff boolean NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (
  id bigserial PRIMARY KEY,
  name text NOT NULL,
  reaction_hours integer NOT NULL CHECK (reaction_hours > 0)
);
CREATE TABLE IF NOT EXISTS tickets (
  id bigserial PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id),
  category_id bigint NOT NULL REFERENCES categories(id),
  title text NOT NULL,
  body text NOT NULL,
  status text NOT NULL CHECK (status IN ('new', 'in_progress', 'closed')),
  created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS comments (
  id bigserial PRIMARY KEY,
  ticket_id bigint NOT NULL REFERENCES tickets(id),
  user_id bigint NOT NULL REFERENCES users(id),
  body text NOT NULL,
  created_at timestamptz NOT NULL
);
