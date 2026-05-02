-- vpoRAG local Jira mirror database
-- Run once in MySQL Workbench to set up the local DB.
-- After this, use sync_local_db.py to pull data from the MCP server.

CREATE DATABASE IF NOT EXISTS jira_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE jira_db;

CREATE TABLE IF NOT EXISTS `dpstriage` (
  `Key` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `Issue_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Status` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Assignee` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Summary` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Description` text COLLATE utf8mb4_unicode_ci,
  `Created` datetime DEFAULT NULL,
  `Updated` datetime DEFAULT NULL,
  `Priority` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Platform_Affected` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Root_Cause` text COLLATE utf8mb4_unicode_ci,
  `Resolution_Category` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Requesting_Organization` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Environment_HE_Controller` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Customer_Type` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Customer_Impact` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Last_Comment` text COLLATE utf8mb4_unicode_ci,
  `Resolution_Mitigation` text COLLATE utf8mb4_unicode_ci,
  `Vertical` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Labels` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`Key`),
  KEY `idx_status` (`Status`(191)),
  KEY `idx_assignee` (`Assignee`),
  KEY `idx_created` (`Created`),
  KEY `idx_labels` (`Labels`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `postrca` (
  `Key` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `Issue_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Status` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Assignee` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Summary` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Description` text COLLATE utf8mb4_unicode_ci,
  `Created` datetime DEFAULT NULL,
  `Updated` datetime DEFAULT NULL,
  `Priority` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Platform_Affected` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Root_Cause` text COLLATE utf8mb4_unicode_ci,
  `Resolution_Category` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Requesting_Organization` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Environment_HE_Controller` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Customer_Type` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Customer_Impact` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Last_Comment` text COLLATE utf8mb4_unicode_ci,
  `Resolution_Mitigation` text COLLATE utf8mb4_unicode_ci,
  `Vertical` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Labels` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`Key`),
  KEY `idx_status` (`Status`(191)),
  KEY `idx_assignee` (`Assignee`),
  KEY `idx_created` (`Created`),
  KEY `idx_labels` (`Labels`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `csv_imports` (
  `id` int NOT NULL AUTO_INCREMENT,
  `filename` varchar(256) DEFAULT NULL,
  `ticket_type` enum('dpstriage','postrca') DEFAULT NULL,
  `imported_at` datetime DEFAULT NULL,
  `rows_inserted` int DEFAULT NULL,
  `rows_updated` int DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Local sync tracking: records each pull from the remote server
CREATE TABLE IF NOT EXISTS `sync_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `synced_at` datetime DEFAULT NULL,
  `remote_host` varchar(64) DEFAULT NULL,
  `dps_rows` int DEFAULT NULL,
  `rca_rows` int DEFAULT NULL,
  `duration_sec` float DEFAULT NULL,
  `status` varchar(16) DEFAULT NULL,
  `error` text DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
