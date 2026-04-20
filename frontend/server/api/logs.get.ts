import mysql from 'mysql2/promise'

interface SearchLog {
  id: number
  keyword: string
  posts_found: number
  posts_inserted: number
  posts_skipped: number
  images_found: number
  images_uploaded: number
  images_failed: number
  duration_seconds: number
  error_message: string | null
  created_at: string
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
  const query = getQuery(event)
  const keyword = query.keyword as string | undefined
  const limit = Number(query.limit) || 50
  
  const connection = await mysql.createConnection(dbConfig)
  
  try {
    let sql: string
    let params: string[] = []
    
    if (keyword && keyword.trim()) {
      sql = `
        SELECT id, keyword, posts_found, posts_inserted, posts_skipped,
               images_found, images_uploaded, images_failed,
               duration_seconds, error_message, created_at
        FROM search_logs
        WHERE keyword = ?
        ORDER BY created_at DESC
        LIMIT ${limit}
      `
      params = [keyword.trim()]
    } else {
      sql = `
        SELECT id, keyword, posts_found, posts_inserted, posts_skipped,
               images_found, images_uploaded, images_failed,
               duration_seconds, error_message, created_at
        FROM search_logs
        ORDER BY created_at DESC
        LIMIT ${limit}
      `
    }
    
    const [rows] = await connection.execute(sql, params)
    
    // 格式化时间
    const logs: SearchLog[] = (rows as any[]).map(row => ({
      ...row,
      created_at: row.created_at instanceof Date 
        ? row.created_at.toISOString() 
        : String(row.created_at)
    }))
    
    return {
      success: true,
      logs,
      total: logs.length
    }
  } catch (error: any) {
    return {
      success: false,
      error: error.message || '获取搜索日志失败'
    }
  } finally {
    await connection.end()
  }
})