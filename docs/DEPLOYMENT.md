# 部署文档

本文档保证**他人可独立复现**：从零环境到可访问地址，逐条命令给出。

---

## 1. 环境依赖

| 项 | 要求 | 说明 |
| --- | --- | --- |
| 操作系统 | macOS / Linux / Windows | 已在 macOS 14（Python 3.9.6）验证 |
| Python | **3.8 及以上** | 仅使用标准库：`http.server`、`json`、`urllib`、`argparse` 等 |
| 第三方依赖 | **无** | 不需要 `pip install`，无需虚拟环境，内网离线可用；`requirements.txt` 为空依赖清单（仅作显式声明） |
| 浏览器 | Chrome / Edge / Safari 近两年版本 | 前端为原生 ES5+ JS，无构建步骤 |
| 网络 | 可选 | 平台自身离线可用；仅"点击跳转官方文档"和 `--check-links` 巡检需要外网 |

验证环境：

```bash
python3 -V      # 期望 >= 3.8
```

---

## 2. 获取代码

```bash
# 方式一：从 GitHub clone（推荐）
git clone <仓库地址> multicloud-search && cd multicloud-search

# 方式二：拷贝目录 / 解压压缩包
cp -r 课题一 /opt/multicloud-search && cd /opt/multicloud-search
```

目录内 `data/`、`core/`、`server/`、`web/` 为运行必需，`docs/`、`tools/` 为文档与运维脚本。

### 2.1 移交后必做：一键初始化

```bash
python3 tools/init_project.py
```

它会依次完成：

1. 检查 Python 版本（>= 3.8）与关键文件、数据完整性；
2. **生成本机 MCP 配置 `config/mcp.local.json`**（MCP 协议要求绝对路径；入库的 `config/mcp.example.json` 只含占位符，`mcp.local.json` 已在 `.gitignore` 中，不会泄露本地路径）；
3. 构建零后端单文件版本 `dist/index.html`（仓库不含该产物，需本地生成）；
4. 打印人工 / Agent 两种场景的下一步命令，以及可直接粘贴的 MCP 配置。

指定解释器（`python3` 不在 PATH 时）：

```bash
python3 tools/init_project.py --python /usr/local/bin/python3
```

> 除该配置文件外，所有代码均使用 `__file__` 相对定位，项目目录可任意移动、任意改名。
> 已实测两种场景：① 整包复制到另一路径 ② 模拟刚 clone（无 `mcp.local.json`、无 `dist/`）——
> `python3 tools/verify_all.py` 均为 **70/70 通过**。

---

## 3. 形态 A：后端服务模式（推荐）

### 3.1 启动

```bash
cd <项目根目录>
python3 server/app.py
```

预期输出：

```
数据加载完成：176 个产品 / 20 条价格记录（产品快照 2026-08-12，价格快照 2026-08-12）
服务已启动： http://127.0.0.1:8787
API 健康检查： http://127.0.0.1:8787/api/health
```

### 3.2 访问地址

| 用途 | 地址 |
| --- | --- |
| 平台首页（文档搜索 / 价格对比 / 同类对照 / API 说明） | <http://127.0.0.1:8787> |
| 健康检查 | <http://127.0.0.1:8787/api/health> |
| 搜索接口 | <http://127.0.0.1:8787/api/search?q=%E5%AF%B9%E8%B1%A1%E5%AD%98%E5%82%A8> |
| 价格接口 | <http://127.0.0.1:8787/api/prices/ecs?region=cn-beijing&vcpu=4&memory=8> |

### 3.3 配置项（环境变量或命令行参数）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MCS_HOST` / `--host` | `127.0.0.1` | 监听地址。对外提供服务需显式设为 `0.0.0.0` |
| `MCS_PORT` / `--port` | `8787` | 监听端口 |
| `MCS_DATA_DIR` | `<项目>/data` | 数据目录，可指向共享盘统一维护 |
| `MCS_ALLOW_ORIGIN` | 空（关闭跨域） | 前后端分离时设为确切来源，如 `https://sa.woa.com`；**不要设 `*`** |

示例：

```bash
MCS_HOST=0.0.0.0 MCS_PORT=8080 python3 server/app.py
```

### 3.4 后台常驻（Linux systemd）

```ini
# /etc/systemd/system/multicloud-search.service
[Unit]
Description=Multi-Cloud Product Search Platform
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/multicloud-search
Environment=MCS_HOST=127.0.0.1
Environment=MCS_PORT=8787
ExecStart=/usr/bin/python3 /opt/multicloud-search/server/app.py
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadOnlyPaths=/opt/multicloud-search

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now multicloud-search
sudo systemctl status multicloud-search
```

macOS 临时后台运行：

```bash
nohup python3 server/app.py > /tmp/mcs.log 2>&1 &
tail -f /tmp/mcs.log
```

### 3.5 Nginx 反向代理（公网 / woa 内网发布）

```nginx
server {
    listen 80;
    server_name mcs.example.com;          # 或 woa 内网域名

    location / {
        proxy_pass http://127.0.0.1:8787;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 30s;
    }
}
```

对外发布建议：配置 HTTPS 证书；如需内部访问控制，在 Nginx 层加 `auth_basic` 或对接内网统一登录（平台自身不含账号体系，为只读查询服务）。

---

## 4. 形态 B：单文件 HTML（零后端）

适合发到静态托管、丢进 woa 内网静态目录，或直接发给同事双击打开。

```bash
python3 tools/build_static.py
# 已生成单文件版本：<项目>/dist/index.html（约 104 KB）
```

`dist/index.html` 已把 `data/*.json` 内联，**无网络请求、无跨域问题**。

发布到对象存储静态网站（任选一家）：

```bash
# 腾讯云 COS（coscli）
coscli cp dist/index.html cos://<bucket>/index.html

# 阿里云 OSS（ossutil）
ossutil cp dist/index.html oss://<bucket>/index.html

# 华为云 OBS（obsutil）
obsutil cp dist/index.html obs://<bucket>/index.html
```

访问地址即为对应存储桶静态网站域名，例如 `https://<bucket>.cos-website.ap-guangzhou.myqcloud.com/`。

> 注意：单文件版本不提供 REST API。需要 API/MCP 时用形态 A 或 C。

---

## 5. 形态 C：Docker

```bash
docker build -t multicloud-search .
docker run -d --name mcs -p 8787:8787 --restart unless-stopped multicloud-search
curl http://127.0.0.1:8787/api/health     # {"status":"ok","version":"1.0.0"}
```

数据热更新（把数据目录挂载出来，改完即生效，无需重启）：

```bash
docker run -d --name mcs -p 8787:8787 \
  -v $(pwd)/data:/app/data:ro \
  multicloud-search
```

---

## 6. MCP Server 部署（供 Codebuddy 等 Agent 调用）

MCP 走 stdio，不需要常驻端口，由客户端拉起。先执行 `python3 tools/init_project.py` 生成本机配置
**`config/mcp.local.json`**（入库的 `config/mcp.example.json` 只含占位符，避免泄露本地路径），
再把其中 `mcpServers` 内容复制到 Codebuddy 的 MCP 配置（IDE 设置 → MCP）或其他客户端的 mcp 配置文件：

```json
{
  "mcpServers": {
    "multicloud-search": {
      "command": "python3",
      "args": ["/opt/multicloud-search/mcp/multicloud_mcp_server.py"],
      "env": { "MCS_DATA_DIR": "/opt/multicloud-search/data" }
    }
  }
}
```

> 迁移目录后需同步修改路径；若 `python3` 不在 PATH，把 `command` 换成 `which python3` 输出的绝对路径。

自测（无需客户端）：

```bash
python3 tools/mcp_selftest.py            # 期望：18 项检查，0 项失败
python3 tools/mcp_selftest.py --verbose  # 打印工具真实返回内容
```

详细接口定义与调用示例见 [`MCP_USAGE.md`](MCP_USAGE.md)。

---

## 7. Codebuddy Skill 部署

技能定义已随项目提供：`.codebuddy/skills/multicloud-lookup/SKILL.md`。

- 在 Codebuddy 中打开本项目即可被识别；
- 若要全局可用，复制到用户级技能目录：

```bash
mkdir -p ~/.codebuddy/skills/multicloud-lookup
cp .codebuddy/skills/multicloud-lookup/SKILL.md ~/.codebuddy/skills/multicloud-lookup/
```

> 注意：Skill 内命令以项目根目录为工作目录执行（`cli.py` 所在目录）。若复制到用户级目录，请把 SKILL.md 中的命令改为绝对路径，例如 `python3 /opt/multicloud-search/cli.py docs "对象存储"`。

---

## 8. 冒烟测试清单（部署后逐条验证）

```bash
# 0. 一键验收（推荐先跑，覆盖数据/搜索/价格/API/安全/MCP/Skill/Agent/前端/文档共 70 项）
python3 tools/verify_all.py

# 1. 数据完整性 + 四家覆盖矩阵（期望：结构校验通过，覆盖完整）
python3 tools/check_data.py

# 2. 文档链接巡检（腾讯云 44 条期望全 200）
python3 tools/check_data.py --check-links --vendor tencent --report reports/link_check.csv

# 3. CLI 查询
python3 cli.py docs "对象存储"
python3 cli.py price --vcpu 4 --memory 8

# 4. API（需先启动服务）
curl -s "http://127.0.0.1:8787/api/health"
curl -s "http://127.0.0.1:8787/api/search?q=Kubernetes&limit=4" | head -c 400

# 5. MCP
python3 tools/mcp_selftest.py

# 6. 单文件构建
python3 tools/build_static.py
```

浏览器侧验证点：

1. 首页右上角标签显示运行模式（"后端服务模式" / "静态内联数据"）；
2. 搜索 `对象存储` → 出现 4 张卡片，分别带腾讯云/阿里云/华为云/火山引擎徽章；
3. 点击卡片「官方文档 ↗」→ 新窗口打开厂商文档；
4. 切到「ECS 价格对比」→ 选 4C8G → 表格出现 4 行，最低价行高亮并给出价差结论；
5. 点「复制为 Markdown」→ 粘贴得到表格；点「导出 CSV」→ 下载文件；
6. 切到「跨云同类对照」→ 输入 `CVM` → 输出四家对位产品表。

---

## 9. 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `Address already in use` | 8787 端口被占用 | `python3 server/app.py --port 8888` 或 `lsof -i:8787` 后释放 |
| 命令报 `unrecognized arguments: # ...` | macOS 默认 shell 是 **zsh**，交互模式下默认不识别行尾 `#` 注释（bash 才默认识别），把注释当成了参数 | 只复制命令本身、不带注释；或先执行 `setopt interactive_comments`（可写入 `~/.zshrc` 永久生效） |
| 浏览器显示"数据加载失败：Failed to fetch" | ① 直接用 `file://` 双击打开了 `web/index.html`（浏览器禁止本地 fetch）；② 用 IDE / 其他静态服务器托管，站点根只暴露了 `web/` 目录，取不到 `data/*.json` | 用形态 A 启动服务后访问 <http://127.0.0.1:8787>；或用 `python3 tools/build_static.py` 生成 `dist/index.html` 双击打开。页面已内置排障指引与单文件版直达链接 |
| `web/index.html` 与 `dist/index.html` 该用哪个 | `web/` 版需后端托管（走 `/data/*.json`，附带 REST API）；`dist/` 版数据已内联，零后端 | 演示/发给同事 → `dist/index.html`；需要 API/MCP 或数据热更新 → 形态 A |
| 页面能打开但无数据、控制台 404 | `MCS_DATA_DIR` 指向错误 | 确认 `data/products.json`、`data/ecs_prices.json` 存在且可读 |
| 前后端分离部署时接口报 CORS | 跨域默认关闭 | 设置 `MCS_ALLOW_ORIGIN=https://你的前端域名` |
| MCP 在客户端里不出现工具 | 路径不是绝对路径 / Python 不在 PATH | 用绝对路径，并把 `command` 换成 `python3` 的完整路径（`which python3`） |
| 链接巡检出现 `ERR` | 本机无外网或被代理拦截 | 巡检非必需，可跳过；或配置 `https_proxy` 后重试 |
| 价格与官网不一致 | 数据为人工快照 | 按 [`DATA_SOURCES.md`](DATA_SOURCES.md) 的刷新 SOP 更新 `data/ecs_prices.json` |

---

## 10. 升级与回滚

平台无状态、无数据库，升级即替换文件：

```bash
# 备份数据
cp data/products.json data/products.json.bak
cp data/ecs_prices.json data/ecs_prices.json.bak

# 替换代码后自检并重启
python3 tools/check_data.py && sudo systemctl restart multicloud-search
```

数据文件支持**热更新**：`core/engine.py` 按文件 mtime 自动重载，改完 `data/*.json` 无需重启服务（单文件 HTML 版本需重新 `build_static.py`）。
