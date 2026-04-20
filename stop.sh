#!/bin/bash
# XHS Project 停止脚本

PROJECT_DIR="/xhs-project"
PID_FILE="$PROJECT_DIR/.pids"

if [ -f "$PID_FILE" ]; then
    read BACKEND_PID FRONTEND_PID < "$PID_FILE"
    
    echo "停止后端 (PID: $BACKEND_PID)..."
    kill $BACKEND_PID 2>/dev/null
    
    echo "停止前端 (PID: $FRONTEND_PID)..."
    kill $FRONTEND_PID 2>/dev/null
    
    # 同时杀掉可能的子进程
    pkill -f "python main.py" 2>/dev/null
    pkill -f "node.*nuxt" 2>/dev/null
    
    rm -f "$PID_FILE"
    echo "服务已停止"
else
    echo "未找到 PID 文件，尝试按进程名停止..."
    pkill -f "python main.py" 2>/dev/null
    pkill -f "node.*nuxt" 2>/dev/null
    echo "已尝试停止相关进程"
fi