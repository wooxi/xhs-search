# XHS Project - 小红书搜索系统

整合小红书数据抓取与前端展示的全栈项目。

## 项目结构

```
/xhs-project/
├── .env              # 共享配置（数据库、CDP、图床）
├── start.sh          # 一键启动脚本
├── stop.sh           # 停止脚本
├── README.md         # 本文档
├── backend/          # 后端 Python FastAPI
│   ├── main.py       # API 入口
│   ├── db.py         # 数据库操作
│   ├── scheduler.py  # 定时任务
│   ├── upload_images.py  # 图床上传
│   ├── xhs_search_cdp.py # CDP 搜索脚本
│   ├── venv/         # Python 虚拟环境
│   └── requirements.txt
├── frontend/         # 前端 Nuxt 应用
│   ├── app/          # Vue 页面组件
│   ├── server/       # Nuxt server API
│   ├── nuxt.config.ts
│   └── package.json
└── logs/             # 运行日志
```

## 快速启动

```bash
cd /xhs-project
./start.sh
```

## 访问地址

- **后端 API**: http://192.168.100.6:5020
- **前端 Web**: http://192.168.100.6:5021

## 停止服务

```bash
./stop.sh
```

## 配置说明

编辑 `.env` 文件：

```env
# MySQL 数据库
DB_HOST=192.168.100.4
DB_PORT=3306
DB_USER=root
DB_PASSWORD=ulikem00n
DB_DATABASE=xhs_notes

# CDP 浏览器
CDP_HOST=127.0.0.1
CDP_PORT=9222

# Lsky Pro 图床
LSKY_PRO_URL=http://192.168.100.4:5021
LSKY_PRO_TOKEN=<your_token>
```

## 后端 API 端点

| 端点 | 说明 |
|------|------|
| `/` | 健康检查 |
| `/search?keyword=xxx` | 执行搜索任务 |
| `/tasks` | 查看搜索任务列表 |
| `/start-scheduler` | 启动定时任务 |

## 维护命令

```bash
# 查看后端日志
tail -f logs/backend.log

# 查看前端日志  
tail -f logs/frontend.log

# 重启后端
cd backend && source venv/bin/activate && python main.py

# 重启前端
cd frontend && ./start.sh
```