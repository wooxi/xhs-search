"""MySQL 数据库连接和操作模块。

功能：
1. 自动检测并创建数据库
2. 创建帖子数据表
3. 插入/查询帖子记录
"""

import os
import json
import re
from typing import Optional, List, Dict, Any
from datetime import datetime

import mysql.connector
from mysql.connector import Error, pooling

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def convert_chinese_number(value: Any) -> int:
    """转换中文数字格式到整数。
    
    支持格式：
    - '1.5万' → 15000
    - '2万' → 20000
    - '1.2k' → 1200
    - 数字 → 直接返回
    """
    if value is None:
        return 0
    
    if isinstance(value, (int, float)):
        return int(value)
    
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return 0
        
        # 尝试直接转换数字
        try:
            return int(value)
        except ValueError:
            pass
        
        # 处理中文单位
        match = re.match(r'^([\d.]+)(万|w|W)$', value)
        if match:
            num = float(match.group(1))
            return int(num * 10000)
        
        match = re.match(r'^([\d.]+)(k|K|千)$', value)
        if match:
            num = float(match.group(1))
            return int(num * 1000)
        
        return 0
    
    return 0


class DatabaseConfig:
    """数据库配置。"""

    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = int(os.getenv("DB_PORT", "3306"))
        self.user = os.getenv("DB_USER", "root")
        self.password = os.getenv("DB_PASSWORD", "")
        self.database = os.getenv("DB_DATABASE", "xhs_notes")

    def get_connection_params(self) -> dict:
        """获取连接参数（不含 database，用于创建数据库）。"""
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
        }

    def get_full_connection_params(self) -> dict:
        """获取完整连接参数（含 database）。"""
        params = self.get_connection_params()
        params["database"] = self.database
        return params


class XhsDatabase:
    """小红书数据库操作类。"""

    def __init__(self, config: Optional[DatabaseConfig] = None):
        self.config = config or DatabaseConfig()
        self._pool: Optional[pooling.MySQLConnectionPool] = None

    def init_database(self) -> bool:
        """初始化数据库：检测是否存在，不存在则创建。"""
        try:
            # 先连接到 MySQL（不指定数据库）
            conn = mysql.connector.connect(**self.config.get_connection_params())
            cursor = conn.cursor()

            # 检查数据库是否存在
            cursor.execute(
                "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
                (self.config.database,)
            )
            result = cursor.fetchone()

            if not result:
                # 创建数据库
                print(f"[db] 创建数据库: {self.config.database}")
                cursor.execute(
                    f"CREATE DATABASE {self.config.database} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
                print(f"[db] 数据库已创建: {self.config.database}")
            else:
                print(f"[db] 数据库已存在: {self.config.database}")

            cursor.close()
            conn.close()

            # 创建连接池
            self._create_pool()

            # 创建数据表
            self._create_tables()

            return True

        except Error as e:
            print(f"[db] 初始化数据库失败: {e}")
            return False

    def _create_pool(self):
        """创建连接池。"""
        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name="xhs_pool",
                pool_size=5,
                **self.config.get_full_connection_params()
            )
            print("[db] 连接池已创建")
        except Error as e:
            print(f"[db] 创建连接池失败: {e}")
            raise

    def _get_connection(self) -> mysql.connector.MySQLConnection:
        """从连接池获取连接。"""
        if not self._pool:
            self._create_pool()
        return self._pool.get_connection()

    def _create_tables(self):
        """创建数据表。"""
        # 帖子表
        create_notes_sql = """
        CREATE TABLE IF NOT EXISTS notes (
            id VARCHAR(24) PRIMARY KEY COMMENT '帖子ID',
            title VARCHAR(500) COMMENT '标题',
            content TEXT COMMENT '内容描述',
            url VARCHAR(1000) COMMENT '帖子链接',
            type VARCHAR(20) DEFAULT 'normal' COMMENT '类型(normal/video)',
            images JSON COMMENT '图片链接数组',
            video VARCHAR(1000) COMMENT '视频链接',
            video_cover VARCHAR(1000) COMMENT '视频封面',
            video_duration INT DEFAULT 0 COMMENT '视频时长(秒)',
            likes INT DEFAULT 0 COMMENT '点赞数',
            collects INT DEFAULT 0 COMMENT '收藏数',
            comments INT DEFAULT 0 COMMENT '评论数',
            shares INT DEFAULT 0 COMMENT '分享数',
            author_id VARCHAR(50) COMMENT '作者ID',
            author_name VARCHAR(200) COMMENT '作者昵称',
            author_avatar VARCHAR(500) COMMENT '作者头像',
            ip_location VARCHAR(100) COMMENT 'IP归属地',
            publish_time BIGINT DEFAULT 0 COMMENT '发布时间戳',
            xsec_token VARCHAR(500) COMMENT '安全Token',
            keyword VARCHAR(200) COMMENT '搜索关键词',
            search_sort VARCHAR(20) COMMENT '搜索排序方式',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='小红书帖子表';
        """

        # 搜索词配置表
        create_keywords_sql = """
        CREATE TABLE IF NOT EXISTS keywords (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT '配置ID',
            keyword VARCHAR(100) NOT NULL COMMENT '搜索关键词',
            status VARCHAR(20) DEFAULT 'active' COMMENT '状态(active/paused)',
            auto_search BOOLEAN DEFAULT FALSE COMMENT '是否自动搜索',
            search_interval INT DEFAULT 0 COMMENT '自动搜索间隔(小时)',
            last_search_time DATETIME COMMENT '上次搜索时间',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='搜索词配置表';
        """

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(create_notes_sql)
            cursor.execute(create_keywords_sql)
            cursor.close()
            conn.close()
            print("[db] 数据表已创建: notes, keywords")

            # 创建搜索日志表
            self._create_search_logs_table()
        except Error as e:
            print(f"[db] 创建数据表失败: {e}")
            raise

    def insert_note(self, note: Dict[str, Any], keyword: str = "", search_sort: str = "general") -> bool:
        """插入单个帖子记录。"""
        insert_sql = """
        INSERT INTO notes (
            id, title, content, url, type, images, video, video_cover, video_duration,
            likes, collects, comments, shares, author_id, author_name, author_avatar,
            ip_location, publish_time, xsec_token, keyword, search_sort
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            title = VALUES(title),
            content = VALUES(content),
            likes = VALUES(likes),
            collects = VALUES(collects),
            comments = VALUES(comments),
            shares = VALUES(shares),
            images = VALUES(images),
            video = VALUES(video),
            video_cover = VALUES(video_cover),
            video_duration = VALUES(video_duration),
            author_name = VALUES(author_name),
            author_avatar = VALUES(author_avatar),
            updated_at = CURRENT_TIMESTAMP
        """

        # 提取作者信息
        author = note.get("author", {})
        author_id = author.get("id", "")
        author_name = author.get("name", "")
        author_avatar = author.get("avatar", "")

        # 提取图片和视频
        images_json = json.dumps(note.get("images", [])) if note.get("images") else None
        video_url = note.get("video", "")
        video_cover = note.get("video_cover", "")
        video_duration = note.get("video_duration", 0)

        # 提取互动数据（可能是字符串或数字，支持中文格式如 '1.5万')
        likes = convert_chinese_number(note.get("likes", 0))
        collects = convert_chinese_number(note.get("collects", 0))
        comments = convert_chinese_number(note.get("comments", 0))
        shares = convert_chinese_number(note.get("shares", 0))

        params = (
            note.get("id", ""),
            note.get("title", ""),
            note.get("content", ""),
            note.get("url", ""),
            note.get("type", "normal"),
            images_json,
            video_url,
            video_cover,
            video_duration,
            likes,
            collects,
            comments,
            shares,
            author_id,
            author_name,
            author_avatar,
            note.get("ip_location", ""),
            note.get("time", 0) or note.get("publish_time", 0) or 0,
            note.get("xsec_token", ""),
            keyword,
            search_sort,
        )

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(insert_sql, params)
            conn.commit()
            affected_rows = cursor.rowcount
            cursor.close()
            conn.close()

            if affected_rows > 0:
                print(f"[db] 已插入/更新帖子: {note.get('id', '')}")
                return True
            return False

        except Error as e:
            print(f"[db] 插入帖子失败: {e}")
            return False

    def insert_notes_batch(self, notes: List[Dict[str, Any]], keyword: str = "", search_sort: str = "general") -> int:
        """批量插入帖子记录。"""
        success_count = 0
        for note in notes:
            if self.insert_note(note, keyword, search_sort):
                success_count += 1
        return success_count

    def query_notes(self, keyword: str = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """查询帖子记录。"""
        query_sql = """
        SELECT id, title, content, url, type, images, likes, collects, comments,
               author_id, author_name, keyword, created_at
        FROM notes
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """

        if keyword:
            query_sql = """
            SELECT id, title, content, url, type, images, likes, collects, comments,
                   author_id, author_name, keyword, created_at
            FROM notes
            WHERE keyword = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """

        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            if keyword:
                cursor.execute(query_sql, (keyword, limit, offset))
            else:
                cursor.execute(query_sql, (limit, offset))

            results = cursor.fetchall()
            cursor.close()
            conn.close()

            # 解析 images JSON
            for row in results:
                if row.get("images"):
                    row["images"] = json.loads(row["images"])

            return results

        except Error as e:
            print(f"[db] 查询帖子失败: {e}")
            return []

    def get_note_by_id(self, note_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 查询帖子。"""
        query_sql = """
        SELECT * FROM notes WHERE id = %s
        """

        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query_sql, (note_id,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()

            if result and result.get("images"):
                result["images"] = json.loads(result["images"])

            return result

        except Error as e:
            print(f"[db] 查询帖子失败: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息。"""
        stats_sql = """
        SELECT
            COUNT(*) as total_notes,
            COUNT(DISTINCT keyword) as total_keywords,
            COUNT(DISTINCT author_id) as total_authors,
            SUM(likes) as total_likes,
            SUM(collects) as total_collects
        FROM notes
        """

        keyword_sql = """
        SELECT keyword, COUNT(*) as count
        FROM notes
        GROUP BY keyword
        ORDER BY count DESC
        LIMIT 10
        """

        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)

            # 总统计
            cursor.execute(stats_sql)
            stats = cursor.fetchone()

            # 关键词统计
            cursor.execute(keyword_sql)
            keywords = cursor.fetchall()

            cursor.close()
            conn.close()

            # 将 Decimal 转换为 int
            return {
                "total_notes": int(stats.get("total_notes", 0) or 0),
                "total_keywords": int(stats.get("total_keywords", 0) or 0),
                "total_authors": int(stats.get("total_authors", 0) or 0),
                "total_likes": int(stats.get("total_likes", 0) or 0),
                "total_collects": int(stats.get("total_collects", 0) or 0),
                "top_keywords": [{"keyword": k.get("keyword"), "count": int(k.get("count", 0) or 0)} for k in keywords],
            }

        except Error as e:
            print(f"[db] 获取统计信息失败: {e}")
            return {}

    # ==================== Keywords 管理 ====================

    def get_keywords(self) -> List[Dict[str, Any]]:
        """获取所有搜索词配置。"""
        query_sql = """
        SELECT id, keyword, status, auto_search, search_interval,
               last_search_time, created_at, updated_at
        FROM keywords
        ORDER BY created_at DESC
        """

        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query_sql)
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            # 转换 datetime 为字符串
            for row in results:
                if row.get('last_search_time'):
                    row['last_search_time'] = row['last_search_time'].isoformat() if hasattr(row['last_search_time'], 'isoformat') else str(row['last_search_time'])
                if row.get('created_at'):
                    row['created_at'] = row['created_at'].isoformat() if hasattr(row['created_at'], 'isoformat') else str(row['created_at'])
                if row.get('updated_at'):
                    row['updated_at'] = row['updated_at'].isoformat() if hasattr(row['updated_at'], 'isoformat') else str(row['updated_at'])
                # 转换 auto_search 为 boolean
                row['auto_search'] = bool(row.get('auto_search', 0))
            return results
        except Error as e:
            print(f"[db] 获取搜索词配置失败: {e}")
            return []

    def add_keyword(self, keyword: str, auto_search: bool = False, search_interval: int = 0) -> Dict[str, Any]:
        """添加搜索词配置。"""
        insert_sql = """
        INSERT INTO keywords (keyword, auto_search, search_interval)
        VALUES (%s, %s, %s)
        """

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(insert_sql, (keyword, auto_search, search_interval))
            conn.commit()
            keyword_id = cursor.lastrowid
            cursor.close()
            conn.close()
            print(f"[db] 已添加搜索词: {keyword}")
            return {"success": True, "id": keyword_id, "keyword": keyword}
        except Error as e:
            print(f"[db] 添加搜索词失败: {e}")
            return {"success": False, "error": str(e)}

    def remove_keyword(self, keyword: str) -> Dict[str, Any]:
        """删除搜索词配置。"""
        delete_sql = "DELETE FROM keywords WHERE keyword = %s"

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(delete_sql, (keyword,))
            conn.commit()
            affected = cursor.rowcount
            cursor.close()
            conn.close()
            if affected > 0:
                print(f"[db] 已删除搜索词: {keyword}")
                return {"success": True, "keyword": keyword}
            else:
                return {"success": False, "error": "搜索词不存在"}
        except Error as e:
            print(f"[db] 删除搜索词失败: {e}")
            return {"success": False, "error": str(e)}

    def update_keyword_status(self, keyword: str, status: str) -> Dict[str, Any]:
        """更新搜索词状态 (active/paused)。"""
        update_sql = "UPDATE keywords SET status = %s WHERE keyword = %s"

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(update_sql, (status, keyword))
            conn.commit()
            affected = cursor.rowcount
            cursor.close()
            conn.close()
            if affected > 0:
                print(f"[db] 已更新搜索词状态: {keyword} -> {status}")
                return {"success": True, "keyword": keyword, "status": status}
            else:
                return {"success": False, "error": "搜索词不存在"}
        except Error as e:
            print(f"[db] 更新搜索词状态失败: {e}")
            return {"success": False, "error": str(e)}

    def enable_auto_search(self, keyword: str, search_interval: int = 24) -> Dict[str, Any]:
        """启用自动搜索。"""
        update_sql = """
        UPDATE keywords SET auto_search = TRUE, search_interval = %s, status = 'active'
        WHERE keyword = %s
        """

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(update_sql, (search_interval, keyword))
            conn.commit()
            affected = cursor.rowcount
            cursor.close()
            conn.close()
            if affected > 0:
                print(f"[db] 已启用自动搜索: {keyword}，间隔 {search_interval} 小时")
                return {"success": True, "keyword": keyword, "auto_search": True, "search_interval": search_interval}
            else:
                return {"success": False, "error": "搜索词不存在"}
        except Error as e:
            print(f"[db] 启用自动搜索失败: {e}")
            return {"success": False, "error": str(e)}

    def disable_auto_search(self, keyword: str) -> Dict[str, Any]:
        """禁用自动搜索。"""
        update_sql = "UPDATE keywords SET auto_search = FALSE WHERE keyword = %s"

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(update_sql, (keyword,))
            conn.commit()
            affected = cursor.rowcount
            cursor.close()
            conn.close()
            if affected > 0:
                print(f"[db] 已禁用自动搜索: {keyword}")
                return {"success": True, "keyword": keyword, "auto_search": False}
            else:
                return {"success": False, "error": "搜索词不存在"}
        except Error as e:
            print(f"[db] 禁用自动搜索失败: {e}")
            return {"success": False, "error": str(e)}

    def update_last_search_time(self, keyword: str) -> bool:
        """更新上次搜索时间。"""
        update_sql = "UPDATE keywords SET last_search_time = NOW() WHERE keyword = %s"

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(update_sql, (keyword,))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Error as e:
            print(f"[db] 更新上次搜索时间失败: {e}")
            return False

    # ==================== 帖子重复检查 ====================

    def is_note_exists(self, note_id: str = None, url: str = None) -> bool:
        """检查帖子是否已存在。

        Args:
            note_id: 帖子ID（优先使用）
            url: 帖子链接（备选）

        Returns:
            True: 已存在，False: 不存在
        """
        if note_id:
            query_sql = "SELECT id FROM notes WHERE id = %s LIMIT 1"
            param = note_id
        elif url:
            query_sql = "SELECT id FROM notes WHERE url = %s LIMIT 1"
            param = url
        else:
            return False

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(query_sql, (param,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            return result is not None
        except Error as e:
            print(f"[db] 检查帖子存在失败: {e}")
            return False

    # ==================== 搜索日志 ====================

    def _create_search_logs_table(self):
        """创建搜索日志表。"""
        create_sql = """
        CREATE TABLE IF NOT EXISTS search_logs (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT '日志ID',
            keyword VARCHAR(100) COMMENT '搜索关键词',
            posts_found INT DEFAULT 0 COMMENT '发现的帖子数',
            posts_inserted INT DEFAULT 0 COMMENT '成功入库数',
            posts_skipped INT DEFAULT 0 COMMENT '跳过的重复帖子数',
            images_found INT DEFAULT 0 COMMENT '发现的图片数',
            images_uploaded INT DEFAULT 0 COMMENT '上传成功的图片数',
            images_failed INT DEFAULT 0 COMMENT '上传失败的图片数',
            duration_seconds INT DEFAULT 0 COMMENT '执行耗时（秒）',
            error_message TEXT COMMENT '错误信息',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录时间'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='搜索执行日志表';
        """

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(create_sql)
            cursor.close()
            conn.close()
            print("[db] 数据表已创建: search_logs")
        except Error as e:
            print(f"[db] 创建搜索日志表失败: {e}")
            raise

    def log_search_result(
        self,
        keyword: str,
        posts_found: int = 0,
        posts_inserted: int = 0,
        posts_skipped: int = 0,
        images_found: int = 0,
        images_uploaded: int = 0,
        images_failed: int = 0,
        duration_seconds: int = 0,
        error_message: str = None,
    ) -> bool:
        """记录搜索执行日志。"""
        insert_sql = """
        INSERT INTO search_logs (
            keyword, posts_found, posts_inserted, posts_skipped,
            images_found, images_uploaded, images_failed,
            duration_seconds, error_message
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(insert_sql, (
                keyword, posts_found, posts_inserted, posts_skipped,
                images_found, images_uploaded, images_failed,
                duration_seconds, error_message
            ))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Error as e:
            print(f"[db] 记录搜索日志失败: {e}")
            return False

    def get_search_logs(self, keyword: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取搜索日志记录。"""
        if keyword:
            query_sql = """
            SELECT * FROM search_logs WHERE keyword = %s
            ORDER BY created_at DESC LIMIT %s
            """
            params = (keyword, limit)
        else:
            query_sql = """
            SELECT * FROM search_logs
            ORDER BY created_at DESC LIMIT %s
            """
            params = (limit,)

        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query_sql, params)
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            # 转换 datetime
            for row in results:
                if row.get('created_at'):
                    row['created_at'] = row['created_at'].isoformat() if hasattr(row['created_at'], 'isoformat') else str(row['created_at'])
            return results
        except Error as e:
            print(f"[db] 获取搜索日志失败: {e}")
            return []

    def get_auto_search_keywords(self) -> List[Dict[str, Any]]:
        """获取需要自动搜索的搜索词（auto_search=True 且 status=active）。"""
        query_sql = """
        SELECT id, keyword, search_interval, last_search_time
        FROM keywords
        WHERE auto_search = TRUE AND status = 'active'
        """

        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query_sql)
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            return results
        except Error as e:
            print(f"[db] 获取自动搜索词失败: {e}")
            return []


def test_connection() -> bool:
    """测试数据库连接。"""
    config = DatabaseConfig()
    try:
        conn = mysql.connector.connect(**config.get_connection_params())
        print(f"[db] 成功连接到 MySQL: {config.host}:{config.port}")
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()
        print(f"[db] MySQL 版本: {version[0]}")
        cursor.close()
        conn.close()
        return True
    except Error as e:
        print(f"[db] 连接失败: {e}")
        return False


if __name__ == "__main__":
    # 测试连接
    print("=== 测试数据库连接 ===")
    if test_connection():
        print("\n=== 初始化数据库 ===")
        db = XhsDatabase()
        if db.init_database():
            print("\n=== 数据库统计 ===")
            stats = db.get_stats()
            print(json.dumps(stats, ensure_ascii=False, indent=2))