#!/bin/bash
# XHS Project 一键启动脚本
# 同时启动后端 API 和前端 Nuxt 应用

PROJECT_DIR="/xhs-project"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
LOG_DIR="$PROJECT_DIR/logs"

# 确保 logs 目录存在
mkdir -p "$LOG_DIR"

# 启动后端 FastAPI
echo "启动后端 API (端口 5020)..."
cd "$BACKEND_DIR"
source venv/bin/activate
nohup python main.py > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "后端 PID: $BACKEND_PID"

# 等待后端启动
sleep 2

# 启动前端 Nuxt
echo "启动前端 Nuxt (端口 3000)..."
cd "$FRONTEND_DIR"
nohup ./start.sh > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "前端 PID: $FRONTEND_PID"

echo ""
echo "服务启动完成!"
echo "- 后端 API: http://192.168.100.6:5020"
echo "- 前端 Web: http://192.168.100.6:5021"
echo "- 后端日志: $LOG_DIR/backend.log"
echo "- 前端日志: $LOG_DIR/frontend.log"
echo ""
echo "PIDs 已保存到 $PROJECT_DIR/.pids"
echo "$BACKEND_PID $FRONTEND_PID" > "$PROJECT_DIR/.pids"