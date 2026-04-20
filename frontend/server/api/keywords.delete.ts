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
  // 从查询参数或请求体获取关键词
  const query = getQuery(event)
  const body = await readBody(event).catch(() => null)
  
  const keyword = query.keyword || body?.keyword?.trim()
  
  if (!keyword) {
    return {
      success: false,
      error: '关键词不能为空'
    }
  }
  
  const connection = await mysql.createConnection(dbConfig)
  
  try {
    const deleteSql = 'DELETE FROM keywords WHERE keyword = ?'
    const [result] = await connection.execute(deleteSql, [keyword])
    
    const affectedRows = (result as any).affectedRows
    
    if (affectedRows > 0) {
      return {
        success: true,
        keyword,
        message: '关键词已删除'
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
      error: error.message || '删除关键词失败'
    }
  } finally {
    await connection.end()
  }
})