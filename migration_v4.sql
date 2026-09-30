-- 从 v3 升级到页面外观增强版本；每个数据库执行一次。
USE `onboarding_db`;
ALTER TABLE `sys_config`
    ADD COLUMN `login_bg_color` VARCHAR(20) DEFAULT '#0f172a',
    ADD COLUMN `login_overlay_color` VARCHAR(20) DEFAULT '#0f172a',
    ADD COLUMN `login_overlay_opacity` INT DEFAULT 65,
    ADD COLUMN `login_welcome_title` VARCHAR(100) DEFAULT '欢迎新同事加入！',
    ADD COLUMN `login_welcome_subtitle` VARCHAR(255) DEFAULT '在开始办理入职配置前，请先登记您的基础个人信息',
    ADD COLUMN `login_button_text` VARCHAR(100) DEFAULT '开启我的入职指南 ➔',
    ADD COLUMN `header_bg_color` VARCHAR(20) DEFAULT '#0f172a',
    ADD COLUMN `header_overlay_color` VARCHAR(20) DEFAULT '#0f172a',
    ADD COLUMN `header_overlay_opacity` INT DEFAULT 72,
    ADD COLUMN `header_title_color` VARCHAR(20) DEFAULT '#ffffff',
    ADD COLUMN `header_subtitle_color` VARCHAR(20) DEFAULT '#94a3b8';
