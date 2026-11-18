-- Однократная подготовка PostgreSQL для всех лабораторных (от имени суперпользователя):
--   psql -U postgres -f setup_db.sql
-- Создаёт пользователя ips (пароль ips) и базы lab1, lab2, lab3. Повторный запуск безопасен.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ips') THEN
        CREATE ROLE ips LOGIN PASSWORD 'ips';
    END IF;
END $$;

SELECT format('CREATE DATABASE %I OWNER ips ENCODING ''UTF8'' TEMPLATE template0', db)
FROM unnest(ARRAY['lab1', 'lab2', 'lab3']) AS db
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = db)\gexec
