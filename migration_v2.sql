-- 仅用于从旧版数据库升级到 v2；每个数据库执行一次。
USE `onboarding_db`;
ALTER TABLE `department`
    ADD COLUMN `sort_order` INT DEFAULT 0,
    ADD COLUMN `is_active` TINYINT(1) DEFAULT 1;
ALTER TABLE `position`
    ADD COLUMN `sort_order` INT DEFAULT 0,
    ADD COLUMN `is_active` TINYINT(1) DEFAULT 1;
ALTER TABLE `category` ADD COLUMN `is_active` TINYINT(1) DEFAULT 1;
ALTER TABLE `document`
    ADD COLUMN `visibility_type` VARCHAR(20) DEFAULT 'all',
    ADD COLUMN `status` VARCHAR(20) DEFAULT 'published';
CREATE TABLE `document_department` (
    `document_id` INT NOT NULL,
    `department_id` INT NOT NULL,
    PRIMARY KEY (`document_id`, `department_id`),
    FOREIGN KEY (`document_id`) REFERENCES `document`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`department_id`) REFERENCES `department`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
UPDATE `document`
SET `visibility_type` = CASE WHEN `is_all_positions` = 1 THEN 'all' ELSE 'position' END
WHERE `visibility_type` IS NULL OR `visibility_type` = '';
UPDATE `document` SET `status` = 'published' WHERE `status` IS NULL OR `status` = '';
