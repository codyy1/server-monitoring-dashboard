#!/usr/bin/env bash
# Run inside the VirtualBox Ubuntu Server VM to configure MySQL for remote WSL connections
set -euo pipefail

DB_NAME="${DB_NAME:-os_monitor}"
DB_USER="${DB_USER:-monitor_user}"
DB_PASS="${DB_PASSWORD:-monitor_pass}"

echo "[1/4] Ensuring mysql-server is installed and running..."
sudo apt-get update -y
sudo apt-get install -y mysql-server
sudo systemctl enable --now mysql

echo "[2/4] Binding MySQL to 0.0.0.0:3306 so WSL can connect..."
MYSQL_CNF="/etc/mysql/mysql.conf.d/mysqld.cnf"
if [ -f "$MYSQL_CNF" ]; then
  sudo sed -i 's/^bind-address\s*=.*/bind-address = 0.0.0.0/' "$MYSQL_CNF"
  sudo sed -i 's/^mysqlx-bind-address\s*=.*/mysqlx-bind-address = 0.0.0.0/' "$MYSQL_CNF"
  sudo systemctl restart mysql
fi

echo "[3/4] Creating database '${DB_NAME}' and user '${DB_USER}'..."
sudo mysql -e "CREATE DATABASE IF NOT EXISTS ${DB_NAME};"
sudo mysql -e "CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASS}';"
sudo mysql -e "GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'%';"
sudo mysql -e "FLUSH PRIVILEGES;"

echo "[4/4] Importing schema.sql..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/schema.sql" ]; then
  sudo mysql "${DB_NAME}" < "${SCRIPT_DIR}/schema.sql"
fi

echo "Done. VM MySQL is listening on port 3306."
