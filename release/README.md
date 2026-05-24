# Code Dependency Graph

C++ 代码依赖分析与可视化工具。

## 快速开始

### 方式一：一键部署

1. 解压压缩包
2. 双击运行 `scripts\build.bat`（首次运行）
3. 双击运行 `scripts\start.bat`
4. 打开浏览器访问 http://localhost:8000

### 方式二：手动部署

```bash
# 1. 安装 Python 依赖
cd backend
pip install -r requirements.txt

# 2. 启动服务
python main.py
```

## 功能特性

- **调用树分析** - 查看函数的调用关系树
- **依赖图可视化** - D3.js 力导向图展示符号关系
- **影响分析** - 分析修改某函数会影响的调用者
- **多层架构** - 支持 SDK/LOGIC/BUSINESS/UI 分层
- **VS 项目解析** - 支持 Visual Studio 解决方案解析

## 目录结构

```
code-dependency-graph/
├── backend/          # Python FastAPI 后端
│   ├── main.py      # 主服务入口
│   ├── database.py  # SQLite 数据库
│   ├── parser.py    # C++ 解析器
│   └── requirements.txt
├── frontend/dist/    # React 前端（已构建）
├── data/            # 数据库存储
├── logs/            # 日志文件
└── scripts/         # 部署脚本
    ├── build.bat   # 构建脚本
    ├── start.bat   # 启动脚本
    └── stop.bat    # 停止脚本
```

## 系统要求

- Python 3.8+
- Windows 10/11
- 内存 4GB+
- 磁盘 500MB+

## 使用说明

1. **添加仓库** - 点击"仓库管理"添加代码仓库
2. **解析代码** - 选择仓库后点击"解析"按钮
3. **浏览符号** - 在左侧面板浏览类和函数
4. **查看调用树** - 点击符号查看 Call Tree
5. **影响分析** - 切换到 Analysis 视图

## 技术栈

- **后端**: Python 3.8+, FastAPI, SQLite, Tree-sitter
- **前端**: React 18, TypeScript, D3.js, Vite
- **数据库**: SQLite

## 常见问题

Q: 服务无法启动？
A: 检查 8000 端口是否被占用，尝试运行 stop.bat 清理旧进程

Q: 解析失败？
A: 确保代码仓库路径正确，支持 .sln/.vcxproj 或直接扫描源码

Q: 调用关系为空？
A: 检查是否正确解析，外部库函数不会被追踪

## 许可证

MIT License
