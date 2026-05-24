---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 3046022100a4a88a67d375d275d45cd05f0ff9bdb958a599816e6271a4e91c89c2e2afc5cc0221008c1bdb1e62d270f063a6c44748a8dabee4a5b5a99a5754dcf8b1327665188820
    ReservedCode2: 3045022040e860e023a93b1557bfaef75a12051013fdec70680cefa33b1a45972d84aff6022100b0eb08a67b1f0d315b218a0f376528f72b52deccdb422ad4d4ef9b6a5afe98b5
---

# 部署指南

## 环境要求

- Python 3.10+
- SQLite3
- 现代浏览器 (Chrome/Firefox/Edge)

## 后端部署

### 1. 准备环境

```bash
# 创建项目目录
mkdir -p /opt/code-dependency-graph
cd /opt/code-dependency-graph

# 克隆或复制项目
git clone <your-repo> .  # 或手动复制文件
```

### 2. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

**requirements.txt 内容**：
```
fastapi>=0.100.0
uvicorn>=0.23.0
tree-sitter>=0.20.0
tree-sitter-languages>=1.10.0
pydantic>=2.0.0
```

### 3. 启动服务

#### 开发环境

```bash
cd backend
python main.py
# 服务运行在 http://0.0.0.0:8000
```

#### 生产环境

使用 uvicorn 进程管理器：

```bash
# 安装进程管理器
pip install gunicorn

# 启动服务
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000
```

或使用 systemd 服务：

```bash
# /etc/systemd/system/code-dependency-graph.service
[Unit]
Description=Code Dependency Graph Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/code-dependency-graph/backend
ExecStart=/usr/bin/python3 main.py --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable code-dependency-graph
sudo systemctl start code-dependency-graph
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8000/api/health

# 预期输出
{"status": "ok", "database": "/opt/code-dependency-graph/data/dependency.db"}
```

## 前端部署

前端是纯静态文件，可部署到任意 HTTP 服务器。

### 方式 1: Nginx 部署

```nginx
# /etc/nginx/sites-available/code-dependency-graph

server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    location / {
        root /opt/code-dependency-graph/static;
        index index.html;
        try_files $uri $uri/ =404;
    }

    # API 反向代理
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/code-dependency-graph /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 方式 2: 使用已部署的静态文件

当前前端已部署到云端，可直接访问：
- https://3ov7r3r6kjys.space.minimaxi.com

但需确保后端服务在 `http://localhost:8000` 运行。

## Docker 部署 (可选)

### Dockerfile

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# 创建数据目录
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "main.py"]
```

### 构建和运行

```bash
docker build -t code-dependency-graph .
docker run -d -p 8000:8000 -v $(pwd)/data:/app/data code-dependency-graph
```

## 数据目录

数据库默认位置：
- 开发环境：`backend/../data/dependency.db`
- Docker：`/app/data/dependency.db`

## 防火墙配置

如果部署在服务器上，确保开放端口：

```bash
# Ubuntu/Debian
sudo ufw allow 8000/tcp

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

## 常见问题

### 1. 后端启动失败

检查 Python 版本：
```bash
python --version  # 需要 3.10+
```

检查依赖：
```bash
pip list | grep -E "fastapi|uvicorn|tree-sitter"
```

### 2. 前端无法连接后端

检查 CORS 配置（main.py）：
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议限制
    ...
)
```

### 3. 解析超时

大仓库解析可能需要较长时间，可使用后台任务：
```bash
# 在 main.py 中添加 BackgroundTasks
```

### 4. 数据库锁定

SQLite 并发写入有限，生产环境建议：
- 使用只读副本
- 添加连接池
- 或迁移到 PostgreSQL