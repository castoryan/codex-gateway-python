# Codex Gateway Python

一个偏实用主义的 Python Gateway，目标是：

- 用一个上游 Codex / OpenAI 账号统一出网
- 默认按 OpenClaw 同款走 ChatGPT Codex backend：`https://chatgpt.com/backend-api/codex/responses`
- 给多个用户签发独立 API Key
- 支持 API Key 创建 / 删除 / 启停 / token 统计
- 支持 **OpenClaw 风格手动 OAuth 登录**
- 支持 Docker / Docker Compose 部署
- 提供一个本地管理员工具：`manage.py`

> 现在推荐的使用方式是：**优先用 `manage.py` 管理**，而不是手敲一堆 `curl`。

---

## 1. 你最需要理解的两件事

### 1.1 `ADMIN_TOKEN` 是什么？

它就是这个 Gateway 的**管理员口令**。

它不是平台发给你的，也不是 OpenAI 给的，而是**你自己在 `.env` 里设置的随机字符串**。

比如：

```env
ADMIN_TOKEN=1d84e2f2d0b8f1d5c9ab4f0b4f8a3e2d1a7c5f9e8b6a4c3d2e1f0a9b8c7d6e5
```

如果你要生成一个新的：

```bash
python manage.py generate-admin-token
```

然后把结果写进 `.env`，再重启容器。

### 1.2 为什么现在不用再敲很多 curl 了？

因为我已经给工程补了一个本地管理员工具：

```bash
python manage.py ...
```

你可以直接用它：

- 发起上游 OAuth 登录
- 提交 callback URL
- 创建用户
- 创建 API Key
- 查看用量
- 查看登录状态

---

## 2. 项目结构

```text
codex-gateway-python/
├── app/
├── .dockerignore
├── .env.example
├── .env.docker.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── manage.py
├── README.md
└── requirements.txt
```

---

## 3. `manage.py` 能做什么

### 3.1 常用命令

```bash
python manage.py doctor
python manage.py generate-admin-token
python manage.py auth-start
python manage.py auth-complete --session-id 1 --callback-url "http://localhost/callback?code=...&state=..."
python manage.py auth-status
python manage.py create-user alice --note "team-a"
python manage.py list-users
python manage.py create-key --user-id 1 --name alice-dev
python manage.py list-keys
python manage.py disable-key 1
python manage.py enable-key 1
python manage.py delete-key 1
python manage.py usage
```

### 3.2 在 Docker Compose 里怎么用

因为你现在已经 `docker compose up` 了，所以最方便的是这样用：

```bash
docker compose exec codex-gateway python manage.py doctor
```

后面的命令都可以照这个模式执行。

> 注意：如果你直接在宿主机执行 `python manage.py ...`，需要宿主机先安装 `requirements.txt` 里的依赖。对你当前场景，**直接在容器里执行是最省事的**。

---

## 4. 我建议你的实际使用顺序

你现在已经把容器跑起来了，所以直接按这个顺序来。

### 第一步：检查配置和当前状态

```bash
cd /home/ubuntu/codex-gateway-python
docker compose exec codex-gateway python manage.py doctor
```

这会告诉你：

- 当前 `UPSTREAM_AUTH_MODE`
- OAuth 配置有没有填
- 数据库里有没有用户、Key、OAuth 会话、上游凭证

---

## 5. 怎么登录 Codex / 上游账号

### 前提
你如果想走你最想要的那种“OpenClaw 风格网页登录”，需要 `.env` 至少已经配置：

```env
UPSTREAM_AUTH_MODE=oauth_manual
OAUTH_AUTHORIZE_URL=...
OAUTH_TOKEN_URL=...
OAUTH_CLIENT_ID=...
OAUTH_REDIRECT_URI=http://localhost/callback
```

这版已经默认内置了与 OpenClaw 相同的 Codex OAuth 常量：

```env
OAUTH_AUTHORIZE_URL=https://auth.openai.com/oauth/authorize
OAUTH_TOKEN_URL=https://auth.openai.com/oauth/token
OAUTH_CLIENT_ID=app_EMoamEEZ73f0CkXaXp7hrann
OAUTH_REDIRECT_URI=http://localhost:1455/auth/callback
OAUTH_SCOPE=openid profile email offline_access
OAUTH_ORIGINATOR=pi
OAUTH_CODEX_CLI_SIMPLIFIED_FLOW=true
OAUTH_ID_TOKEN_ADD_ORGANIZATIONS=true
```

所以通常你不需要再自己查这几个值了，保持默认即可。

### 5.1 发起登录

```bash
docker compose exec codex-gateway python manage.py auth-start
```

它会输出一段 JSON，里面有：

- `session_id`
- `auth_url`
- `state`
- `expires_at`

同时还会提示你下一步命令。

### 5.2 浏览器打开 `auth_url`

把 `auth_url` 整个复制到你自己的浏览器里，完成登录。

### 5.3 复制最终回调 URL

登录完成后，浏览器会跳到类似：

```text
http://localhost/callback?code=xxx&state=yyy
```

把这个完整 URL 复制出来。

### 5.4 完成登录

```bash
docker compose exec codex-gateway python manage.py auth-complete \
  --session-id 1 \
  --callback-url "http://localhost/callback?code=xxx&state=yyy"
```

### 5.5 查看登录状态

```bash
docker compose exec codex-gateway python manage.py auth-status
```

如果成功，你会看到当前已有 `current_credential`。

---

## 6. 怎么创建用户

比如你要创建一个叫 `alice` 的用户：

```bash
docker compose exec codex-gateway python manage.py create-user alice --note "team-a"
```

然后列出用户：

```bash
docker compose exec codex-gateway python manage.py list-users
```

你会看到类似：

```json
[
  {
    "id": 1,
    "name": "alice",
    "note": "team-a"
  }
]
```

记住这个 `id`。

---

## 7. 怎么生成新的 API Key

比如给 `user_id=1` 创建一个叫 `alice-dev` 的 Key：

```bash
docker compose exec codex-gateway python manage.py create-key --user-id 1 --name alice-dev
```

它会输出类似：

```json
{
  "id": 1,
  "user_id": 1,
  "name": "alice-dev",
  "api_key": "gtw_xxxxxxxxx",
  "key_preview": "gtw_xx...xxxx",
  "enabled": true
}
```

### 注意
`api_key` 明文只会显示这一次，你要自己保存好。

---

## 8. 怎么查看和管理 API Key

### 查看所有 keys

```bash
docker compose exec codex-gateway python manage.py list-keys
```

### 禁用 key

```bash
docker compose exec codex-gateway python manage.py disable-key 1
```

### 启用 key

```bash
docker compose exec codex-gateway python manage.py enable-key 1
```

### 删除 key

```bash
docker compose exec codex-gateway python manage.py delete-key 1
```

---

## 9. 怎么看 token 用量统计

```bash
docker compose exec codex-gateway python manage.py usage
```

会看到：

- 每个 key 的 request_count
- prompt_tokens
- completion_tokens
- total_tokens
- 总汇总 totals

---

## 10. 拿新 API Key 怎么调用模型

假设你刚拿到：

```text
gtw_xxxxxxxxx
```

那么调用方式是：

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H 'Authorization: Bearer gtw_xxxxxxxxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-4.1-mini",
    "messages": [
      {"role": "user", "content": "hello"}
    ]
  }'
```

这里的 `gtw_xxxxxxxxx` 就是你发给下游脚本 / 用户的 Gateway API Key。

他们**不需要知道 `ADMIN_TOKEN`**。

---

## 11. Docker / Compose 用法

### 11.1 首次启动

```bash
cd /home/ubuntu/codex-gateway-python
cp .env.docker.example .env
docker compose up -d --build
```

### 11.2 重启

```bash
docker compose down
docker compose up -d --build
```

### 11.3 看日志

```bash
docker compose logs -f
```

---

## 12. `.env` 最关键的配置

### 如果你要走网页登录 OAuth

```env
ADMIN_TOKEN=你自己生成的随机字符串
UPSTREAM_AUTH_MODE=oauth_manual
OAUTH_AUTHORIZE_URL=https://auth.openai.com/oauth/authorize
OAUTH_TOKEN_URL=https://auth.openai.com/oauth/token
OAUTH_CLIENT_ID=app_EMoamEEZ73f0CkXaXp7hrann
OAUTH_REDIRECT_URI=http://localhost:1455/auth/callback
OAUTH_SCOPE=openid profile email offline_access
OAUTH_ORIGINATOR=pi
OAUTH_CODEX_CLI_SIMPLIFIED_FLOW=true
OAUTH_ID_TOKEN_ADD_ORGANIZATIONS=true
```

### 上游默认请求层

这版现在默认不再把 OAuth 登录态转发到 `api.openai.com/v1/chat/completions`，而是改成更接近 OpenClaw 的上游：

```text
POST https://chatgpt.com/backend-api/codex/responses
```

并自动带上这些关键头：

- `Authorization: Bearer <oauth access token>`
- `chatgpt-account-id: <从token里提取>`
- `OpenAI-Beta: responses=experimental`
- `originator: pi`

### 如果你暂时只想先跑通，不管网页登录

```env
ADMIN_TOKEN=你自己生成的随机字符串
UPSTREAM_AUTH_MODE=env_token
UPSTREAM_BEARER_TOKEN=你的上游token
```

注意：`env_token` 更适合标准 OpenAI API Key 路线；而你现在如果想复用 Codex / ChatGPT OAuth 登录态，就应该保留 `oauth_manual`。

---

## 13. 常见问题

### Q1：`ADMIN_TOKEN` 从哪里来？
你自己生成，自己写进 `.env`。

可以直接生成：

```bash
python manage.py generate-admin-token
```

### Q2：如果我都用 `manage.py` 了，还需要 `ADMIN_TOKEN` 吗？
`manage.py` 本地直连数据库和业务逻辑，**平时你自己管理时其实不依赖 HTTP 鉴权**。

但服务端的管理接口仍然需要 `ADMIN_TOKEN`，因为那是给 HTTP 管理接口做保护用的。

所以：
- **你本地用 `manage.py` 时，几乎不用关心它**
- **服务本身仍然应该配置它**

### Q3：`auth-start` 报 `missing oauth config`
说明 `.env` 里这些至少有空的：

- `OAUTH_AUTHORIZE_URL`
- `OAUTH_TOKEN_URL`
- `OAUTH_CLIENT_ID`
- `OAUTH_REDIRECT_URI`

### Q4：`auth-complete` 报 `oauth state mismatch`
说明你粘回来的 callback URL 不是同一次登录会话的结果，或者复制错了。

### Q5：`create-key` 成功，但模型调用失败
通常是：

- 上游还没登录成功
- 上游 token 无效
- model 名称不对
- 上游接口本身报错

先执行：

```bash
docker compose exec codex-gateway python manage.py auth-status
```

看上游凭证是否真的存在。

---

## 14. 我建议你现在就这样做

按顺序执行：

```bash
cd /home/ubuntu/codex-gateway-python
```

### 先看状态

```bash
docker compose exec codex-gateway python manage.py doctor
```

### 如果 OAuth 参数已经填好，就登录

```bash
docker compose exec codex-gateway python manage.py auth-start
```

然后浏览器登录，再执行：

```bash
docker compose exec codex-gateway python manage.py auth-complete --session-id 1 --callback-url "你的完整回调URL"
```

### 然后创建用户

```bash
docker compose exec codex-gateway python manage.py create-user alice --note "team-a"
```

### 创建 key

```bash
docker compose exec codex-gateway python manage.py create-key --user-id 1 --name alice-dev
```

### 查看状态和统计

```bash
docker compose exec codex-gateway python manage.py auth-status
docker compose exec codex-gateway python manage.py usage
```

---

## 15. 后续建议

接下来最值得补的不是更多 curl 示例，而是：

1. 管理后台 Web UI
2. 上游凭证加密存储
3. SSE 流式代理
4. per-key 配额 / 限流

但至少现在，`manage.py` 这一层已经把“手敲 curl 很烦”这件事解决掉了。