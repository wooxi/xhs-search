import mysql from 'mysql2/promise'
import { spawn } from 'child_process'

// 数据库配置
const dbConfig = {
  host: process.env.DB_HOST || '192.168.100.4',
  port: Number(process.env.DB_PORT) || 3306,
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || 'ulikem00n',
  database: process.env.DB_DATABASE || 'xhs_notes'
}

export default defineEventHandler(async (event) => {
  const body = await readBody(event)
  const keyword = body.keyword?.trim()
  const limit = body.limit ?? 10
  
  if (!keyword) {
    return {
      success: false,
      error: '关键词不能为空'
    }
  }
  
  // 调用 xhs-db 的搜索脚本
  // 注意：这个 API 会触发搜索脚本，可能需要较长时间
  try {
    // 更新上次搜索时间
    const connection = await mysql.createConnection(dbConfig)
    await connection.execute(
      'UPDATE keywords SET last_search_time = NOW() WHERE keyword = ?',
      [keyword]
    )
    await connection.end()
    
    // 执行搜索脚本（后台运行）
    const scriptPath = '/xhs-project/backend/main.py'
    const child = spawn('python3', [scriptPath, 'search', keyword, '--limit', String(limit)], {
      cwd: '/xhs-project/backend',
      env: process.env,
      detached: true,
      stdio: 'ignore'
    })
    child.unref()
    
    return {
      success: true,
      keyword,
      limit,
      message: '搜索任务已启动',
      note: '搜索将在后台运行，结果会自动入库'
    }
  } catch (error: any) {
    return {
      success: false,
      error: error.message || '触发搜索失败'
    }
  }
})