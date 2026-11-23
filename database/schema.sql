-- Database schema for the VirtualBox VM MySQL Server
CREATE DATABASE IF NOT EXISTS os_monitor
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE os_monitor;

CREATE TABLE IF NOT EXISTS servers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hostname VARCHAR(128) NOT NULL UNIQUE,
    os_distro VARCHAR(128) NOT NULL,
    kernel_version VARCHAR(128) NOT NULL,
    ip_address VARCHAR(64) NOT NULL,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metric_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    hostname VARCHAR(128) NOT NULL,
    cpu_percent DECIMAL(5,2) NOT NULL,
    load_1m DECIMAL(6,2) NOT NULL,
    mem_used_mb INT NOT NULL,
    mem_total_mb INT NOT NULL,
    mem_percent DECIMAL(5,2) NOT NULL,
    disk_used_gb DECIMAL(8,2) NOT NULL,
    disk_total_gb DECIMAL(8,2) NOT NULL,
    disk_percent DECIMAL(5,2) NOT NULL,
    process_count INT NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_recorded_at (recorded_at),
    INDEX idx_hostname (hostname)
);

CREATE TABLE IF NOT EXISTS alert_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    hostname VARCHAR(128) NOT NULL,
    severity ENUM('INFO', 'WARN', 'CRITICAL') NOT NULL,
    metric_name VARCHAR(64) NOT NULL,
    metric_value VARCHAR(64) NOT NULL,
    message VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
