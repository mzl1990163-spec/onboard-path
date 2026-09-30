-- 从 v4 升级到支持未分类文档；每个数据库执行一次。
USE `onboarding_db`;
ALTER TABLE `document` MODIFY COLUMN `category_id` INT NULL;
