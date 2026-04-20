import mysql from 'mysql2/promise'

interface Post {
  id: number
  title: string
  content: string
  url: string
  images: string[]
  likes: number
  collects: number
  comments: number
  author_name: string
  keyword: string
  publish_time: string
}

// 数据库配置 - 直接从环境变量读取
const dbConfig = {
  host: process.env.DB_HOST || '192.168.100.4',
  port: Number(process.env.DB_PORT) || 3306,
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || 'ulikem00n',
  database: process.env.DB_DATABASE || 'xhs_notes'
}

export default defineEventHandler(async (event) => {
  // 获取查询参数
  const query = getQuery(event)
  const page = Number(query.page) || 1
  const pageSize = Number(query.pageSize) || 20
  const keyword = (query.keyword as string) || ''
  
  const offset = (page - 1) * pageSize
  
  // 创建数据库连接
  const connection = await mysql.createConnection(dbConfig)
  
  try {
    // 构建基础查询
    let baseWhere = ''
    let params: any[] = []
    
    if (keyword && keyword.trim()) {
      const kw = keyword.trim()
      baseWhere = 'WHERE title LIKE ? OR keyword LIKE ? OR author_name LIKE ?'
      params = [`%${kw}%`, `%${kw}%`, `%${kw}%`]
    }
    
    // 查询总数
    const countSql = `SELECT COUNT(*) as total FROM notes ${baseWhere}`
    const [countRows] = await connection.execute(countSql, params)
    const total = (countRows as any[])[0].total
    
    // 查询数据 - LIMIT OFFSET 直接拼接（安全数字）
    const dataSql = `SELECT 
      id, title, content, url, images, 
      likes, collects, comments, author_name, 
      keyword, publish_time
     FROM notes 
     ${baseWhere}
     ORDER BY publish_time DESC 
     LIMIT ${pageSize} OFFSET ${offset}`
    
    const [rows] = await connection.execute(dataSql, params)
    
    // 处理 images JSON 字段
    const posts: Post[] = (rows as any[]).map(row => ({
      ...row,
      images: typeof row.images === 'string' ? JSON.parse(row.images || '[]') : row.images || []
    }))
    
    return {
      posts,
      total,
      page,
      pageSize
    }
  } finally {
    await connection.end()
  }
})