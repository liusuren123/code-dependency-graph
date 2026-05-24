---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 304402202ba283dcbe8aa8d7f4939d3c68f9e7683f24f848edbecb9f5493a2f26f03e70f02201766b633a59cbf18bd24c61715d0cee55587e946926f2dd40fa2516d9c2d1676
    ReservedCode2: 3045022018f16cd2263ac4212639d5060a761806a2ec143859107596d8dbe3b898d4679c022100fbec6ac3101e7cf5997957044bf51ff9ecf354bc9fbb0150d55445485668e967
---

# 维护指南

## 数据库管理

### 备份数据库

```bash
# 停止服务
cd backend

# 备份
cp data/dependency.db data/backup_$(date +%Y%m%d).db

# 或使用 sqlite3
sqlite3 data/dependency.db ".backup data/backup_$(date +%Y%m%d).db"
```

### 恢复数据库

```bash
# 停止服务
pkill -f "python main.py"

# 恢复
cp data/backup_20240115.db data/dependency.db

# 重启服务
python main.py
```

### 清理过期数据

如果需要清理旧的仓库和符号数据：

```python
# 在 Python 中执行
from database import Database
db = Database()

# 删除特定仓库
db.delete_repository(repo_id)

# 或手动清理整个数据库
import os
os.remove("data/dependency.db")
# 重启服务会自动创建新数据库
```

## 日志管理

### 日志位置

日志文件位于 `backend/../logs/app.log`，默认同时输出到控制台。

### 日志格式

```
2024-01-15 10:30:00 | INFO     | code-dependency-graph | 创建仓库: name=MyProject, layer=LOGIC, path=/path/to/project
2024-01-15 10:30:01 | INFO     | code-dependency-graph | 开始解析仓库: id=1, name=MyProject
2024-01-15 10:30:15 | INFO     | code-dependency-graph | VS解析完成: id=1, 耗时=14.32s, 符号数=150, 依赖数=320
```

### 日志级别

- `INFO`: 正常操作记录（仓库创建、解析进度、完成统计）
- `WARNING`: 警告信息（解析失败、降级处理）
- `DEBUG`: 详细调试信息（项目文件解析详情）

### 实时查看日志

```bash
# 实时跟踪日志
tail -f logs/app.log

# 查看最近 100 行
tail -n 100 logs/app.log

# 搜索关键词
grep "ERROR" logs/app.log
grep "解析完成" logs/app.log
```

### 日志轮转（生产环境建议）

如果日志文件过大，可以使用 logrotate 配置：

```bash
# /etc/logrotate.d/code-dependency-graph
/workspace/code-dependency-graph/logs/app.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

## 监控

### 检查服务状态

```bash
# 检查进程
ps aux | grep "python main.py" | grep -v grep

# 检查端口
netstat -tlnp | grep 8000

# 或
lsof -i :8000
```

### 检查数据库

```bash
sqlite3 backend/data/dependency.db

# 查看表
sqlite> .tables

# 查看记录数
sqlite> SELECT COUNT(*) FROM repositories;
sqlite> SELECT COUNT(*) FROM symbols;
sqlite> SELECT COUNT(*) FROM dependencies;
```

## 性能优化

### 1. 大仓库解析

对于大型仓库（>10000 个文件），建议：

```python
# 分批解析
# 在 parser.py 中添加进度回调
def parse_with_progress(repo, callback):
    files = collect_files(repo.path)
    total = len(files)
    for i, f in enumerate(files):
        parse_file(f)
        callback(i + 1, total)
```

### 2. 数据库索引

确认索引存在：
```sql
CREATE INDEX IF NOT EXISTS idx_symbols_repo ON symbols(repository_id);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_hash ON symbols(hash_value);
CREATE INDEX IF NOT EXISTS idx_deps_source ON dependencies(source_symbol_id);
CREATE INDEX IF NOT EXISTS idx_deps_target ON dependencies(target_symbol_id);
```

### 3. 内存优化

如果内存不足，可以限制并发解析：
```python
# 在 parser.py 中
MAX_CONCURRENT = 4
```

## 常见问题排查

### 1. 符号搜索无结果

检查：
1. 仓库是否已解析：`GET /api/repositories/{id}`
2. 符号表是否有数据：直接查询 SQLite
3. 层级是否正确：`GET /api/layers`

### 2. VS 解析失败

可能原因：
1. .sln 文件路径不存在
2. .vcxproj 文件格式变化
3. 权限问题

排查：
```python
# 在 Python 中测试
from parser import VSProjectResolver

# 查找 .sln 文件
sln_files = VSProjectResolver.find_solution_files("/path/to/project")

# 解析特定文件
projects = VSProjectResolver.parse_solution("/path/to/xxx.sln")
```

### 3. 前端无法连接

检查：
1. 后端是否运行：`curl http://localhost:8000/api/health`
2. CORS 配置：检查 main.py 中的 CORSMiddleware
3. 浏览器控制台错误

### 4. 依赖关系不准确

原因可能是：
1. `#include` 路径解析问题
2. Tree-sitter 解析错误

排查：查看日志中的警告信息
```bash
grep "解析失败" logs/app.log
grep "降级" logs/app.log
```

## 代码更新

### 更新后端

```bash
cd backend

# 拉取最新代码
git pull

# 更新依赖
pip install -r requirements.txt

# 重启服务
pkill -f "python main.py"
python main.py
```

### 更新前端

前端已部署到云端，如需更新本地：

```bash
# 编辑 static/index.html
# 或重新构建 React 版本（如果有）

# 部署
# 方式 1: 替换静态文件到 Nginx
cp -r static/* /var/www/html/

# 方式 2: 使用部署命令
# 当前系统支持自动部署
```

## 数据库迁移

### 添加新字段

如果需要为 `repositories` 表添加新字段：

```python
# 在 database.py 的 _init_database() 中
cursor.execute("""
    ALTER TABLE repositories ADD COLUMN new_column TEXT DEFAULT ''
""")
```

### 数据迁移脚本

```python
# migrate.py
from database import Database
db = Database()

# 示例：批量更新符号
symbols = db.list_symbols(limit=10000)
for sym in symbols:
    # 更新逻辑
    pass
```

## 安全建议

1. **限制 CORS**：生产环境不要使用 `allow_origins=["*"]`
2. **添加认证**：当前无认证，建议添加 API Key 或 JWT
3. **限制上传**：如果支持远程仓库拉取，验证 URL
4. **清理敏感信息**：不要在日志中打印路径等敏感信息

## 联系支持

如有问题，请提供：
1. 错误日志
2. 复现步骤
3. 环境信息（Python 版本、操作系统）