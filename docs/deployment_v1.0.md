# 生产部署说明 v1.0

系统采用 Nginx + FastAPI + PostgreSQL 的三容器部署方式，默认对外端口为 `8088`。Nginx 提供静态资源、API 反向代理、安全响应头和限流；平台使用应用登录、Token 和租户成员关系进行鉴权，API 与数据库不直接暴露公网端口。

模型配置通过平台“模型配置”页面维护。API Key 使用服务端 Fernet 主密钥加密后写入数据库，接口不会返回明文密钥。平台默认内置模拟模型，未配置外部密钥时仍可演示完整治理流程。

部署前从 `.env.example` 生成 `.env`，至少设置数据库密码、Fernet 密钥和平台登录密码。`.env` 不进入源码或发布压缩包之外的共享文档。

启动与检查：

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 api web
```

数据库使用命名卷 `postgres_data`，执行容器更新或重建不会删除业务数据。删除数据卷属于破坏性操作，生产环境禁止使用 `docker compose down -v`。
