import mysql from 'mysql2/promise'

interface Keyword {
  id: number
  keyword: string
  status: string
  auto_search: boolean
  search_interval: number
  last_search_time: string | null
  created_at: string
  updated_at: string
}

// 数据库配置
const dbConfig = {
  host: process.env.DB_HOST || '192.168.100.4',
  port: Number(process.env.DB_PORT) || 3306,
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || 'ulikem00n',
  database: process.env.DB_DATABASE || 'xhs_notes'
}

export default defineEventHandler(async (event) => {
  const connection = await mysql.createConnection(dbConfig)
  
  try {
    const sql = `
      SELECT id, keyword, status, auto_search, search_interval,
             last_search_time, created_at, updated_at
      FROM keywords
      ORDER BY created_at DESC
    `
    
    const [rows] = await connection.execute(sql)
    
    // 转换 boolean 字段
    const keywords: Keyword[] = (rows as any[]).map(row => ({
      ...row,
      auto_search: Boolean(row.auto_search)
    }))
    
    return {
      success: true,
      keywords
    }
  } catch (error: any) {
    return {
      success: false,
      error: error.message || '获取搜索词列表失败'
    }
  } finally {
    await connection.end()
  }
})