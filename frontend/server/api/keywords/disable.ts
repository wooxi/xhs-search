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
  const body = await readBody(event)
  const keyword = body.keyword?.trim()
  
  if (!keyword) {
    return {
      success: false,
      error: '关键词不能为空'
    }
  }
  
  const connection = await mysql.createConnection(dbConfig)
  
  try {
    const updateSql = `
      UPDATE keywords 
      SET auto_search = FALSE
      WHERE keyword = ?
    `
    const [result] = await connection.execute(updateSql, [keyword])
    
    const affectedRows = (result as any).affectedRows
    
    if (affectedRows > 0) {
      return {
        success: true,
        keyword,
        auto_search: false,
        message: '已禁用自动搜索'
      }
    } else {
      return {
        success: false,
        error: '关键词不存在'
      }
    }
  } catch (error: any) {
    return {
      success: false,
      error: error.message || '禁用失败'
    }
  } finally {
    await connection.end()
  }
})