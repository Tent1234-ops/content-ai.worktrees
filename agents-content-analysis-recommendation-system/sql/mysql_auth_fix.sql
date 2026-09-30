-- Run this only if PyMySQL cannot connect because MySQL uses
-- caching_sha2_password / sha256_password and your Python environment
-- cannot install the cryptography package.
--
-- Execute in MySQL Workbench as an administrative user:
-- 1. Open a SQL tab.
-- 2. Run the statements below.
-- 3. Restart your FastAPI app and test again.

ALTER USER 'root'@'localhost'
IDENTIFIED WITH mysql_native_password BY '1234';

ALTER USER 'root'@'127.0.0.1'
IDENTIFIED WITH mysql_native_password BY '1234';

FLUSH PRIVILEGES;
