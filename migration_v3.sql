-- 从 v2 升级到块编辑器版本；每个数据库执行一次。
USE `onboarding_db`;
ALTER TABLE `document`
    ADD COLUMN `content_json` LONGTEXT,
    ADD COLUMN `editor_version` INT DEFAULT 1;
