import mysql from 'mysql2/promise'

// 数据库配置
const dbConfig = {
  host: process.env.DB_HOST || '192.168.100.4',
  port: Number(process.env.DB_PORT) || 3306,
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || 'ulikem00n',
  database: process.env.DB_DATABASE || 'xhs_notes'
}

export default defineEventHandler(async (event) => {
  // 读取请求体
  const body = await readBody(event)
  const keyword = body.keyword?.trim()
  const auto_search = body.auto_search ?? false
  const search_interval = body.search_interval ?? 24
  
  if (!keyword) {
    return {
      success: false,
      error: '关键词不能为空'
    }
  }
  
  const connection = await mysql.createConnection(dbConfig)
  
  try {
    // 检查是否已存在
    const checkSql = 'SELECT id FROM keywords WHERE keyword = ?'
    const [existing] = await connection.execute(checkSql, [keyword])
    
    if ((existing as any[]).length > 0) {
      return {
        success: false,
        error: '关键词已存在'
      }
    }
    
    // 插入新关键词
    const insertSql = `
      INSERT INTO keywords (keyword, auto_search, search_interval)
      VALUES (?, ?, ?)
    `
    const [result] = await connection.execute(insertSql, [keyword, auto_search, search_interval])
    
    return {
      success: true,
      id: (result as any).insertId,
      keyword,
      auto_search,
      search_interval
    }
  } catch (error: any) {
    return {
      success: false,
      error: error.message || '添加关键词失败'
    }
  } finally {
    await connection.end()
  }
})