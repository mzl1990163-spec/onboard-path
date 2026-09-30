CREATE DATABASE IF NOT EXISTS `onboarding_db` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `onboarding_db`;

CREATE TABLE IF NOT EXISTS `sys_config` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `login_bg_url` VARCHAR(255) DEFAULT '',
    `login_bg_color` VARCHAR(20) DEFAULT '#0f172a',
    `login_overlay_color` VARCHAR(20) DEFAULT '#0f172a',
    `login_overlay_opacity` INT DEFAULT 65,
    `login_welcome_title` VARCHAR(100) DEFAULT '欢迎新同事加入！',
    `login_welcome_subtitle` VARCHAR(255) DEFAULT '在开始办理入职配置前，请先登记您的基础个人信息',
    `login_button_text` VARCHAR(100) DEFAULT '开启我的入职指南 ➔',
    `header_bg_url` VARCHAR(255) DEFAULT '',
    `header_bg_color` VARCHAR(20) DEFAULT '#0f172a',
    `header_overlay_color` VARCHAR(20) DEFAULT '#0f172a',
    `header_overlay_opacity` INT DEFAULT 72,
    `header_title_color` VARCHAR(20) DEFAULT '#ffffff',
    `header_subtitle_color` VARCHAR(20) DEFAULT '#94a3b8',
    `header_title` VARCHAR(100) DEFAULT '新员工入职落地指引',
    `header_subtitle` VARCHAR(255) DEFAULT '欢迎加入！请按照下方指引完成首周账号、软件及配置准备。',
    `employee_expired_title` VARCHAR(120) DEFAULT '入职指引访问期已结束',
    `employee_expired_message` VARCHAR(500) DEFAULT '您的新员工入职指引访问期限已结束。如有相关问题，请联系 IT 部门，或者前往钉钉服务台进行咨询。',
    `employee_dingtalk_text` VARCHAR(80) DEFAULT '钉钉服务台',
    `employee_dingtalk_url` VARCHAR(500) DEFAULT '',
    `employee_not_found_message` VARCHAR(255) DEFAULT '未查询到员工信息，请确认姓名全拼或联系 IT 部门。',
    `employee_service_error_message` VARCHAR(255) DEFAULT '认证服务暂时不可用，请稍后重试或联系 IT 部门。'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `department` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(50) NOT NULL,
    `sort_order` INT DEFAULT 0,
    `is_active` TINYINT(1) DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `position` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(50) NOT NULL,
    `department_id` INT NOT NULL,
    `sort_order` INT DEFAULT 0,
    `is_active` TINYINT(1) DEFAULT 1,
    FOREIGN KEY (`department_id`) REFERENCES `department`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `category` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(50) NOT NULL,
    `sort_order` INT DEFAULT 0,
    `is_active` TINYINT(1) DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `auth_source` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL,
    `source_type` VARCHAR(20) NOT NULL DEFAULT 'ldap',
    `is_enabled` TINYINT(1) NOT NULL DEFAULT 1,
    `is_employee_default` TINYINT(1) NOT NULL DEFAULT 0,
    `host` VARCHAR(255) NOT NULL,
    `port` INT NOT NULL DEFAULT 389,
    `use_ssl` TINYINT(1) NOT NULL DEFAULT 0,
    `start_tls` TINYINT(1) NOT NULL DEFAULT 0,
    `base_dn` VARCHAR(255) NOT NULL,
    `bind_dn` VARCHAR(255) DEFAULT '',
    `bind_password_encrypted` TEXT,
    `user_search_base` VARCHAR(255) DEFAULT '',
    `user_filter` VARCHAR(500) DEFAULT '(&(objectClass=user)(sAMAccountName={username}))',
    `username_attribute` VARCHAR(80) DEFAULT 'sAMAccountName',
    `display_name_attribute` VARCHAR(80) DEFAULT 'displayName',
    `created_at_attribute` VARCHAR(80) DEFAULT 'whenCreated',
    `employee_valid_days` INT NOT NULL DEFAULT 14,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `admin_user` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(100) NOT NULL UNIQUE,
    `display_name` VARCHAR(100) DEFAULT '',
    `auth_type` VARCHAR(20) NOT NULL DEFAULT 'local',
    `auth_source_id` INT NULL,
    `external_id` VARCHAR(255) DEFAULT '',
    `password_hash` VARCHAR(500) DEFAULT '',
    `role` VARCHAR(20) NOT NULL DEFAULT 'admin',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `last_login_at` DATETIME NULL,
    FOREIGN KEY (`auth_source_id`) REFERENCES `auth_source`(`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `admin_user_category` (
    `user_id` INT NOT NULL,
    `category_id` INT NOT NULL,
    PRIMARY KEY (`user_id`, `category_id`),
    FOREIGN KEY (`user_id`) REFERENCES `admin_user`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`category_id`) REFERENCES `category`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `admin_session` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `token_hash` VARCHAR(64) NOT NULL UNIQUE,
    `user_id` INT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `expires_at` DATETIME NOT NULL,
    INDEX (`token_hash`),
    FOREIGN KEY (`user_id`) REFERENCES `admin_user`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `document` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `category_id` INT NULL,
    `title` VARCHAR(100) NOT NULL,
    `content_html` LONGTEXT,
    `content_json` LONGTEXT,
    `editor_version` INT DEFAULT 1,
    `dingtalk_url` VARCHAR(255) DEFAULT '',
    `software_name` VARCHAR(100) DEFAULT '',
    `software_sys` VARCHAR(50) DEFAULT 'Windows/Mac',
    `download_url` VARCHAR(255) DEFAULT '',
    `extract_code` VARCHAR(50) DEFAULT '',
    `is_all_positions` TINYINT(1) DEFAULT 1,
    `visibility_type` VARCHAR(20) DEFAULT 'all',
    `status` VARCHAR(20) DEFAULT 'published',
    `sort_order` INT DEFAULT 0,
    FOREIGN KEY (`category_id`) REFERENCES `category`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `document_position` (
    `document_id` INT NOT NULL,
    `position_id` INT NOT NULL,
    PRIMARY KEY (`document_id`, `position_id`),
    FOREIGN KEY (`document_id`) REFERENCES `document`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`position_id`) REFERENCES `position`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `document_department` (
    `document_id` INT NOT NULL,
    `department_id` INT NOT NULL,
    PRIMARY KEY (`document_id`, `department_id`),
    FOREIGN KEY (`document_id`) REFERENCES `document`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`department_id`) REFERENCES `department`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `sys_config` (`id`, `header_title`, `header_subtitle`)
VALUES (1, '新员工入职落地指引', '欢迎加入！请按照下方指引完成首周账号与环境配置。')
ON DUPLICATE KEY UPDATE `id`=`id`;
INSERT INTO `department` (`id`, `name`, `sort_order`) VALUES
(1, '技术部', 1), (2, '美术部', 2)
ON DUPLICATE KEY UPDATE `name`=VALUES(`name`), `sort_order`=VALUES(`sort_order`);
INSERT INTO `position` (`id`, `name`, `department_id`, `sort_order`) VALUES
(1, '后端开发', 1, 1), (2, '前端开发', 1, 2), (3, '原画师', 2, 1)
ON DUPLICATE KEY UPDATE `name`=VALUES(`name`), `department_id`=VALUES(`department_id`), `sort_order`=VALUES(`sort_order`);
INSERT INTO `category` (`id`, `name`, `sort_order`) VALUES
(1, 'IT 服务与网络类', 1), (2, '行政与设施类', 2),
(3, '人力资源（HR）类', 3), (4, '项目组与业务类', 4)
ON DUPLICATE KEY UPDATE `name`=VALUES(`name`), `sort_order`=VALUES(`sort_order`);
