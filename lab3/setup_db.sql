-- Однократная подготовка базы данных (выполняется от имени суперпользователя):
--   psql -U postgres -f setup_db.sql
-- Пользователь ips создаётся, только если его ещё нет (в ЛР №1 он уже создан).
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ips') THEN
        CREATE ROLE ips LOGIN PASSWORD 'ips';
    END IF;
END $$;

SELECT 'CREATE DATABASE lab3 OWNER ips ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'lab3')\gexec
