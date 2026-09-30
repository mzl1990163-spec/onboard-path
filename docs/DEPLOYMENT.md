# 部署说明

## 一、准备服务器

安装 Docker Engine 和 Docker Compose V2，并确认以下命令可用：

```bash
docker --version
docker compose version
```

## 二、下载并启动

```bash
git clone https://github.com/mzl1990163-spec/onboard-path.git
cd onboard-path
docker compose up -d
```

首次启动会执行以下操作：

1. 从 GitHub Container Registry 下载预构建的 OnboardPath 镜像。
2. 下载官方 `mysql:8.0` 镜像。
3. 创建持久化数据卷。
4. 等待 MySQL 健康检查通过。
5. 自动创建数据库表和初始超级管理员。
6. 在宿主机 `8001` 端口启动服务。

## 三、检查状态

```bash
docker compose ps
```

正常情况下，以下两个容器都应显示为 `healthy`：

- `onboard-path-app`
- `onboard-path-mysql`

如果应用未正常启动，可查看日志：

```bash
docker compose logs --tail=200 app
docker compose logs --tail=200 mysql
```

## 四、首次配置

1. 打开 `http://服务器IP:8001/admin`。
2. 使用 `admin / ChangeMe123!` 登录。
3. 立即修改初始管理员密码。
4. 创建部门和岗位。
5. 创建文档大类。
6. 配置 LDAP 认证源并测试连接。
7. 创建管理员并分配可管理的大类。
8. 创建并发布入职文档。

## 五、端口调整

默认端口映射为：

```yaml
ports:
  - "8001:8000"
```

如需使用其他端口，只修改冒号左侧的宿主机端口。例如使用 `8080`：

```yaml
ports:
  - "8080:8000"
```

修改后执行：

```bash
docker compose up -d
```

## 六、HTTPS 与反向代理

正式对外提供服务时，建议在应用前部署 Nginx、Caddy 或其他反向代理，并启用 HTTPS。

启用 HTTPS 后，应把 `compose.yaml` 中的配置改为：

```yaml
COOKIE_SECURE: "true"
```

随后重新创建应用容器：

```bash
docker compose up -d
```

## 七、更新版本

更新版本：

```bash
git pull
docker compose pull
docker compose up -d
```

更新容器不会删除数据卷。更新前仍建议先完成备份。

## 八、停止和卸载

只停止并移除容器，保留数据：

```bash
docker compose down
```

永久删除容器及全部数据：

```bash
docker compose down -v
```

第二条命令会删除数据库、上传文件和应用加密密钥，请仅在确认不再需要任何数据时使用。

