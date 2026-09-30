# OnboardPath

OnboardPath 是一个面向企业新员工的入职指引系统。管理员可以按部门、岗位和大类维护入职文档；员工使用姓名全拼完成验证后，只会看到与自己部门和岗位相关的内容。

## 主要功能

- 新员工入职指引页面
- 部门与岗位管理
- 大类和文档排序
- 富文本/块编辑器，支持标题、列表、图片、表格、引用和代码等内容
- 文档可见范围控制：全体员工、指定部门或指定岗位
- 本地管理员与 LDAP 管理员认证
- LDAP 员工账号创建时间校验，默认有效期为 14 天
- 超级管理员与按大类授权的普通管理员
- 登录页和员工端 Header 外观配置
- 登录背景和 Header 背景图片上传
- Docker Compose 两容器部署

## 系统架构

默认使用两个容器：

1. `onboard-path-app`：OnboardPath 应用
2. `onboard-path-mysql`：MySQL 8.0 数据库

MySQL 不向宿主机开放端口，只允许应用容器通过 Docker 内部网络访问。

## 环境要求

- Docker Engine 24 或更高版本
- Docker Compose V2
- 建议至少 2 GB 可用内存

不需要在宿主机单独安装 Python、MySQL 或 Nginx。

## 快速开始

```bash
git clone https://github.com/mzl1990163-spec/onboard-path.git
cd onboard-path
docker compose up -d
```

第一次启动时，Docker Compose 会自动下载 GitHub 构建好的 OnboardPath 镜像和 MySQL 官方镜像、创建数据库表并启动服务。

查看运行状态：

```bash
docker compose ps
```

访问地址：

- 员工端：`http://服务器IP:8001`
- 管理后台：`http://服务器IP:8001/admin`

初始管理员：

```text
用户名：admin
密码：admin@123
```

> **重要：** 首次登录管理后台后，请立即在“用户与权限”中修改初始管理员密码。

## 常用命令

启动：

```bash
docker compose up -d
```

查看状态：

```bash
docker compose ps
```

查看应用日志：

```bash
docker compose logs -f app
```

停止服务：

```bash
docker compose down
```

更新项目：

```bash
git pull
docker compose pull
docker compose up -d
```

> 不要随意执行 `docker compose down -v`，其中的 `-v` 会删除数据库和上传文件所在的数据卷。

## 数据持久化

以下数据保存在 Docker 数据卷中，重新创建容器不会丢失：

| 数据卷 | 用途 |
| --- | --- |
| `mysql_data` | MySQL 数据库 |
| `uploads_data` | 文档图片和背景图片 |
| `app_data` | 自动生成的应用加密密钥 |

`app_data` 中的加密密钥用于保护 LDAP 查询账号密码。备份或迁移系统时，必须同时保留数据库、上传文件和 `app_data`。

详细操作请参阅：

- [部署说明](docs/DEPLOYMENT.md)
- [备份与恢复](docs/BACKUP_RESTORE.md)
- [安全建议](SECURITY.md)
- [版本记录](CHANGELOG.md)

## LDAP 使用说明

- 普通员工不会自动获得后台管理权限。
- 员工端只根据姓名全拼查询 LDAP 用户及账号创建时间。
- 默认允许账号创建后 14 天内访问入职指引。
- LDAP 管理员必须先由超级管理员在“用户与权限”中添加并授权。
- LDAP 管理员的密码仍由 LDAP 验证，本系统不保存其登录密码。

## GitHub 镜像发布

仓库包含 GitHub Actions 配置。代码推送到 `main` 分支或推送 `v*` 版本标签后，会自动根据 `Dockerfile` 构建镜像并发布到：

```text
ghcr.io/mzl1990163-spec/onboard-path
```

`compose.yaml` 已指向这个预构建镜像。首次发布后，需要在 GitHub 的 Package 设置中将镜像设为公开，其他用户才能在未登录 GitHub 的情况下直接拉取。

需要在本地修改或调试源码时，可以手动构建：

```bash
docker build -t ghcr.io/mzl1990163-spec/onboard-path:latest .
docker compose up -d
```

## 开源许可

本项目使用 [MIT License](LICENSE)。

