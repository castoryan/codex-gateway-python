# Codex Gateway Python

一个偏实用主义的 Python Gateway，目标是：

- 用一个上游 Codex / OpenAI 账号统一出网
- 给多个用户签发独立 API Key
- 支持 API Key 创建 / 删除 / 启停 / token 统计
- 支持 **OpenClaw 风格手动 OAuth 登录**：
  1. Gateway 生成授权 URL
  2. 你复制到浏览器登录
  3. 登录完成后把最终 callback URL 粘贴回来
  4. Gateway 自己完成 token exchange 并保存登录态
- 支持 Docker / Docker Compose 部署

---

## 1. 功能概览

### 已支持

- 多用户管理
- 每用户多 API Key
- API Key 创建 / 删除 / 启用 / 禁用
- 按 Key 统计：
  - request_count
  - prompt_tokens
  - completion_tokens
  - total_tokens
- 代理接口：
  - `/v1/chat/completions`
  - `/v1/responses`
  - `/v1/embeddings`
- 上游认证模式：
  - `oauth_manual`
  - `env_token`
  - `codex_auth_file`
  - `auto`
- OAuth 会话持久化
- access token / refresh token 持久化
- access token 到期前自动 refresh（若 refresh_token 可用）

### 当前最推荐的模式

```env
UPSTREAM_AUTH_MODE=oauth_manual
```

也就是你前面说的那种：

- Gateway 给出登录 URL
- 你自己去浏览器登录
- 然后把 callback URL 粘回来

---

## 2. 项目结构

```text
codex-gateway-python/
├── app/
│   ├── main.py
│   ├── models.py
│   ├── auth.py
│   ├── services.py
│   ├── oauth_manual.py
│   ├── codex_auth.py
│   ├── config.py
│   ├── db.py
│   ├── schemas.py
│   ├── oauth_schemas.py
│   └── admin_auth_schemas.py
├── .dockerignore
├── .env.example
├── .env.docker.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── README.md
└── requirements.txt
```

---

## 3. 环境变量说明

### 服务基础配置

- `APP_NAME`：应用名
- `HOST`：监听地址，默认 `0.0.0.0`
- `PORT`：监听端口，默认 `8080`
- `ADMIN_TOKEN`：管理员 token
- `DATABASE_URL`：数据库连接，默认 SQLite

### 上游基础配置

- `UPSTREAM_BASE_URL`：上游 API 地址，默认 `https://api.openai.com`
- `UPSTREAM_AUTH_MODE`：上游认证模式
- `UPSTREAM_BEARER_TOKEN`：当 `env_token` 模式时使用
- `UPSTREAM_TIMEOUT_SECONDS`：上游超时秒数

### OAuth / PKCE 配置

- `OAUTH_AUTHORIZE_URL`
- `OAUTH_TOKEN_URL`
- `OAUTH_CLIENT_ID`
- `OAUTH_CLIENT_SECRET`：可选
- `OAUTH_REDIRECT_URI`
- `OAUTH_SCOPE`
- `OAUTH_AUDIENCE`：可选
- `OAUTH_SESSION_TTL_MINUTES`

### CLI 桥接兼容配置

- `CODEX_COMMAND`
- `CODEX_LOGIN_COMMAND`
- `CODEX_HOME`
- `CODEX_AUTH_CREDENTIALS_STORE`
- `CODEX_LOGIN_LOG_FILE`

### 模型白名单

- `DEFAULT_ALLOWED_MODELS`

---

## 4. 上游认证模式说明

### 4.1 `oauth_manual`

推荐。

形态就是：

1. `POST /admin/auth/codex/oauth/start`
2. 返回 `auth_url`
3. 你去浏览器登录
4. 把最终回调 URL 粘给 `POST /admin/auth/codex/oauth/complete`
5. Gateway 保存 token

### 4.2 `env_token`

直接使用环境变量里的：

```env
UPSTREAM_BEARER_TOKEN=...
```

优点：
- 最稳定
- 最适合正式生产

缺点：
- 不是网页登录态

### 4.3 `codex_auth_file`

从 `CODEX_HOME/auth.json` 里尝试提取凭证。

优点：
- 兼容之前的 CLI 登录缓存思路

缺点：
- 不符合你现在更想要的产品形态

### 4.4 `auto`

优先顺序：

1. `UPSTREAM_BEARER_TOKEN`
2. 数据库里 OAuth 登录态
3. `CODEX_HOME/auth.json`

---

## 5. 本地直接运行

### 5.1 准备环境

```bash
cd codex-gateway-python
cp .env.example .env
```

### 5.2 修改关键配置

最少改这些：

```env
ADMIN_TOKEN=change_me_admin_token
UPSTREAM_BASE_URL=https://api.openai.com
UPSTREAM_AUTH_MODE=oauth_manual

OAUTH_AUTHORIZE_URL=
OAUTH_TOKEN_URL=
OAUTH_CLIENT_ID=
OAUTH_REDIRECT_URI=http://localhost/callback
```

### 5.3 安装依赖

```bash
pip install -r requirements.txt
```

### 5.4 启动

```bash
python -m app.main
```

或：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### 5.5 健康检查

```bash
curl http://127.0.0.1:8080/healthz
```

---

## 6. Docker 部署

### 6.1 复制 Docker 环境文件

```bash
cp .env.docker.example .env
```

### 6.2 修改 `.env`

至少改这些：

```env
ADMIN_TOKEN=your_admin_token
UPSTREAM_AUTH_MODE=oauth_manual
OAUTH_AUTHORIZE_URL=
OAUTH_TOKEN_URL=
OAUTH_CLIENT_ID=
OAUTH_REDIRECT_URI=http://localhost/callback
```

如果你想用静态 token：

```env
UPSTREAM_AUTH_MODE=env_token
UPSTREAM_BEARER_TOKEN=your_upstream_token
```

### 6.3 构建镜像

```bash
docker build -t codex-gateway-python:latest .
```

### 6.4 启动容器

```bash
docker run -d \
  --name codex-gateway-python \
  --restart unless-stopped \
  --env-file .env \
  -p 8080:8080 \
  -v $(pwd)/data:/app/data \
  codex-gateway-python:latest
```

### 6.5 查看日志

```bash
docker logs -f codex-gateway-python
```

---

## 7. Docker Compose 部署

### 7.1 启动

```bash
cp .env.docker.example .env
docker compose up -d --build
```

### 7.2 查看状态

```bash
docker compose ps
```

### 7.3 查看日志

```bash
docker compose logs -f
```

### 7.4 停止

```bash
docker compose down
```

### 7.5 持久化说明

compose 默认挂载：

- `./data:/app/data`

这里会保存：

- SQLite 数据库
- 登录日志
- 运行期数据

如果你还想兼容 `codex_auth_file` 模式，可以自行把宿主机某个绝对路径挂到：

```text
/root/.codex
```

但对你当前诉求来说，**优先还是 `oauth_manual`**，这样根本不需要依赖宿主机先 `codex login`。

---

## 8. OpenClaw 风格 OAuth 登录流程

### 8.1 发起授权

```bash
curl -X POST http://127.0.0.1:8080/admin/auth/codex/oauth/start \
  -H 'Authorization: Bearer your_admin_token'
```

示例返回：

```json
{
  "session_id": 1,
  "auth_url": "https://auth.example.com/oauth/authorize?...",
  "state": "abc123",
  "expires_at": "2026-04-20T14:50:00Z",
  "instructions": "在浏览器打开 auth_url，完成登录后，把最终跳转后的完整 callback URL 粘贴到 /admin/auth/codex/oauth/complete"
}
```

### 8.2 浏览器打开 `auth_url`

你自己登录。

### 8.3 复制回调 URL

浏览器最后通常会跳到：

```text
http://localhost/callback?code=xxx&state=abc123
```

把这个完整 URL 复制出来。

### 8.4 提交 callback URL

```bash
curl -X POST http://127.0.0.1:8080/admin/auth/codex/oauth/complete \
  -H 'Authorization: Bearer your_admin_token' \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id": 1,
    "callback_url": "http://localhost/callback?code=xxx&state=abc123"
  }'
```

### 8.5 查看当前认证状态

```bash
curl http://127.0.0.1:8080/admin/auth/upstream \
  -H 'Authorization: Bearer your_admin_token'
```

### 8.6 查看当前绑定账号信息

```bash
curl http://127.0.0.1:8080/admin/auth/codex/account \
  -H 'Authorization: Bearer your_admin_token'
```

### 8.7 登出 / 清除上游登录态

```bash
curl -X POST http://127.0.0.1:8080/admin/auth/codex/logout \
  -H 'Authorization: Bearer your_admin_token'
```

---

## 9. 用户和 API Key 管理

### 创建用户

```bash
curl -X POST http://127.0.0.1:8080/admin/users \
  -H 'Authorization: Bearer your_admin_token' \
  -H 'Content-Type: application/json' \
  -d '{"name":"alice","note":"team-a"}'
```

### 查看用户列表

```bash
curl http://127.0.0.1:8080/admin/users \
  -H 'Authorization: Bearer your_admin_token'
```

### 创建 API Key

```bash
curl -X POST http://127.0.0.1:8080/admin/keys \
  -H 'Authorization: Bearer your_admin_token' \
  -H 'Content-Type: application/json' \
  -d '{"user_id":1,"name":"alice-dev"}'
```

### 查看 API Keys

```bash
curl http://127.0.0.1:8080/admin/keys \
  -H 'Authorization: Bearer your_admin_token'
```

### 禁用 Key

```bash
curl -X POST http://127.0.0.1:8080/admin/keys/1/disable \
  -H 'Authorization: Bearer your_admin_token'
```

### 启用 Key

```bash
curl -X POST http://127.0.0.1:8080/admin/keys/1/enable \
  -H 'Authorization: Bearer your_admin_token'
```

### 删除 Key

```bash
curl -X DELETE http://127.0.0.1:8080/admin/keys/1 \
  -H 'Authorization: Bearer your_admin_token'
```

### 查看 token 汇总

```bash
curl http://127.0.0.1:8080/admin/usage/summary \
  -H 'Authorization: Bearer your_admin_token'
```

---

## 10. 调用模型示例

### `/v1/chat/completions`

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H 'Authorization: Bearer gtw_xxxxxxxxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-4.1-mini",
    "messages": [{"role": "user", "content": "hello"}]
  }'
```

### `/v1/responses`

```bash
curl http://127.0.0.1:8080/v1/responses \
  -H 'Authorization: Bearer gtw_xxxxxxxxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-4.1-mini",
    "input": "hello"
  }'
```

### `/v1/embeddings`

```bash
curl http://127.0.0.1:8080/v1/embeddings \
  -H 'Authorization: Bearer gtw_xxxxxxxxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "text-embedding-3-small",
    "input": "hello world"
  }'
```

---

## 11. 数据持久化

当前默认数据库：

```text
sqlite+aiosqlite:///./data/gateway.db
```

主要表：

- `users`
- `api_keys`
- `usage_logs`
- `oauth_sessions`
- `upstream_credentials`

SQLite 适合：
- 单机部署
- 小团队内部使用
- MVP / 原型阶段

如果后面你要更稳，我建议迁 PostgreSQL。

---

## 12. 常见问题

### Q1：返回 `missing oauth config`
说明 `.env` 里至少有这些没填：

- `OAUTH_AUTHORIZE_URL`
- `OAUTH_TOKEN_URL`
- `OAUTH_CLIENT_ID`
- `OAUTH_REDIRECT_URI`

### Q2：返回 `oauth state mismatch`
说明你提交回来的 callback URL 不是同一次会话的结果，或者手工复制错了。

### Q3：返回 `oauth session expired`
默认 OAuth session 15 分钟过期，重新发起一次即可。

### Q4：返回 `no active oauth credential; start login first`
说明还没完成 OAuth 登录，或者已被 logout 清掉。

### Q5：容器里 healthcheck 失败
先检查服务本身是否起来：

```bash
docker logs -f codex-gateway-python
```

然后在宿主机测：

```bash
curl http://127.0.0.1:8080/healthz
```

### Q6：为什么我没有把 OpenAI/Codex OAuth endpoint 写死？
因为我没找到官方公开、稳定、明确允许第三方服务端直接复用的完整参数文档。硬写死一套来源不稳的参数，后面更容易炸。

所以这版是：

- 标准 OAuth 2.0 + PKCE 框架已经完整
- 只等你补真实参数

---

## 13. 生产建议

如果你认真上线，我建议：

- 前面放 Nginx / Caddy
- 只暴露内网 / VPN
- 配 HTTPS
- `ADMIN_TOKEN` 放强随机值
- 给 `data/` 目录做备份
- 日志接集中平台
- 后续迁移到 PostgreSQL
- 上游凭证做加密存储

---

## 14. 当前限制

这版是可运行的 MVP，不是假文档，但也不是最终完整版。

还没做：

- 凭证明文加密存储
- 流式 SSE 转发
- per-key 额度 / 限流
- 多上游账号切换
- 管理后台前端
- PostgreSQL / Alembic

---

## 15. 快速命令汇总

### 本地启动

```bash
cp .env.example .env
pip install -r requirements.txt
python -m app.main
```

### Docker 启动

```bash
cp .env.docker.example .env
docker build -t codex-gateway-python:latest .
docker run -d --name codex-gateway-python --restart unless-stopped --env-file .env -p 8080:8080 -v $(pwd)/data:/app/data codex-gateway-python:latest
```

### Compose 启动

```bash
cp .env.docker.example .env
docker compose up -d --build
```

### 看日志

```bash
docker logs -f codex-gateway-python
```

### 健康检查

```bash
curl http://127.0.0.1:8080/healthz
```
