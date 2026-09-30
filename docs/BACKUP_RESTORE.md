# 备份与恢复

OnboardPath 的完整备份包含三部分：

1. MySQL 数据库
2. 文档图片和背景图片
3. 应用加密密钥

只备份数据库并不完整。LDAP 查询账号密码经过加密，恢复时还需要原来的应用加密密钥。

## 推荐方式：备份 Docker 数据卷

先查看实际的数据卷名称：

```bash
docker volume ls | grep onboard
```

通常可以看到以下数据卷：

- `onboard-path_mysql_data`
- `onboard-path_uploads_data`
- `onboard-path_app_data`

实际名称可能因项目目录名称不同而变化，请以服务器显示结果为准。

创建备份目录：

```bash
mkdir -p backup
```

停止服务，避免备份过程中数据发生变化：

```bash
docker compose down
```

分别备份三个数据卷，将下面的数据卷名称替换为服务器上的实际名称：

```bash
docker run --rm -v onboard-path_mysql_data:/data -v "$PWD/backup":/backup alpine \
  tar czf /backup/mysql_data.tar.gz -C /data .

docker run --rm -v onboard-path_uploads_data:/data -v "$PWD/backup":/backup alpine \
  tar czf /backup/uploads_data.tar.gz -C /data .

docker run --rm -v onboard-path_app_data:/data -v "$PWD/backup":/backup alpine \
  tar czf /backup/app_data.tar.gz -C /data .
```

备份完成后重新启动：

```bash
docker compose up -d
```

## 恢复

在全新服务器上先创建空数据卷：

```bash
docker compose create
```

确认三个数据卷的实际名称后，将备份恢复进去：

```bash
docker run --rm -v onboard-path_mysql_data:/data -v "$PWD/backup":/backup alpine \
  sh -c 'rm -rf /data/* && tar xzf /backup/mysql_data.tar.gz -C /data'

docker run --rm -v onboard-path_uploads_data:/data -v "$PWD/backup":/backup alpine \
  sh -c 'rm -rf /data/* && tar xzf /backup/uploads_data.tar.gz -C /data'

docker run --rm -v onboard-path_app_data:/data -v "$PWD/backup":/backup alpine \
  sh -c 'rm -rf /data/* && tar xzf /backup/app_data.tar.gz -C /data'
```

恢复完成后启动服务：

```bash
docker compose up -d
```

最后检查容器状态、后台登录、图片和 LDAP 连接是否正常。

## 重要提醒

- 备份文件中包含业务数据和加密密钥，应放在安全位置。
- 不要把备份文件提交到 GitHub。
- 不要只迁移 MySQL 数据而遗失 `app_data`。
- 建议在每次升级前创建完整备份。

