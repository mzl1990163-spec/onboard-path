USE `onboarding_db`;

ALTER TABLE `sys_config`
    ADD COLUMN `employee_expired_title` VARCHAR(120) DEFAULT '入职指引访问期已结束',
    ADD COLUMN `employee_expired_message` VARCHAR(500) DEFAULT '您的新员工入职指引访问期限已结束。如有相关问题，请联系 IT 部门，或者前往钉钉服务台进行咨询。',
    ADD COLUMN `employee_dingtalk_text` VARCHAR(80) DEFAULT '钉钉服务台',
    ADD COLUMN `employee_dingtalk_url` VARCHAR(500) DEFAULT '',
    ADD COLUMN `employee_not_found_message` VARCHAR(255) DEFAULT '未查询到员工信息，请确认用户名或联系 IT 部门。',
    ADD COLUMN `employee_service_error_message` VARCHAR(255) DEFAULT '认证服务暂时不可用，请稍后重试或联系 IT 部门。';

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
    CONSTRAINT `fk_admin_user_auth_source` FOREIGN KEY (`auth_source_id`) REFERENCES `auth_source`(`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `admin_user_category` (
    `user_id` INT NOT NULL,
    `category_id` INT NOT NULL,
    PRIMARY KEY (`user_id`, `category_id`),
    CONSTRAINT `fk_user_category_user` FOREIGN KEY (`user_id`) REFERENCES `admin_user`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_user_category_category` FOREIGN KEY (`category_id`) REFERENCES `category`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `admin_session` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `token_hash` VARCHAR(64) NOT NULL UNIQUE,
    `user_id` INT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `expires_at` DATETIME NOT NULL,
    INDEX `idx_admin_session_token` (`token_hash`),
    CONSTRAINT `fk_admin_session_user` FOREIGN KEY (`user_id`) REFERENCES `admin_user`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

