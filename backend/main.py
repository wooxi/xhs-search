"""小红书搜索入库主脚本。

功能：
1. 搜索小红书帖子
2. 自动存入 MySQL 数据库
3. 支持批量获取详情
4. 图片上传到 Lsky Pro 图床（可选）

用法：
    python main.py search "关键词"
    python main.py search-detail "关键词" --limit 5 --upload-images
    python main.py stats
    python main.py init-db
"""

import argparse
import json
import sys
import time
from typing import Dict, Any

from db import XhsDatabase, DatabaseConfig, test_connection
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 导入 CDP 搜索模块
try:
    from xhs_search_cdp import (
        search_notes,
        get_note_detail,
        search_and_detail,
        check_login,
        XHSCDPClient,
    )
except ImportError:
    print("[main] 错误: 无法导入 xhs_search_cdp 模块")
    print("[main] 请确保 xhs_search_cdp.py 在同一目录下")
    sys.exit(1)

# 导入图片上传模块
try:
    from upload_images import ImageUploader
except ImportError:
    print("[main] 警告: 无法导入 upload_images 模块，图片上传功能不可用")
    ImageUploader = None


class XhsSearchToDB:
    """小红书搜索入库类。"""

    def __init__(self, upload_images: bool = False):
        self.db = XhsDatabase()
        self.upload_images = upload_images
        self.image_uploader = None
        
        # 如果启用图片上传，初始化上传器
        if upload_images and ImageUploader:
            try:
                self.image_uploader = ImageUploader()
                print("[main] 图片上传功能已启用")
            except Exception as e:
                print(f"[main] 图片上传器初始化失败: {e}")
                self.upload_images = False

    def init(self) -> bool:
        """初始化数据库连接和表结构。"""
        # 测试连接
        if not test_connection():
            print("[main] 数据库连接失败，请检查 .env 配置")
            return False

        # 初始化数据库
        if not self.db.init_database():
            print("[main] 数据库初始化失败")
            return False

        return True

    def search_and_store(self, keyword: str, limit: int = 10, sort_by: str = "general") -> Dict[str, Any]:
        """搜索并存储到数据库。"""
        print(f"[main] 搜索关键词: {keyword}, 数量: {limit}, 排序: {sort_by}")

        # 执行搜索
        result = search_notes(keyword, limit, sort_by, save=False)

        if not result.get("success", False):
            print(f"[main] 搜索失败: {result.get('error', '未知错误')}")
            return result

        notes = result.get("notes", [])
        print(f"[main] 搜索到 {len(notes)} 条帖子")

        # 存入数据库
        success_count = self.db.insert_notes_batch(notes, keyword, sort_by)
        print(f"[main] 成功入库 {success_count} 条帖子")

        result["stored_count"] = success_count
        return result

    def _process_images_for_note(self, note: Dict[str, Any]) -> Dict[str, Any]:
        """处理单个帖子的图片，上传到图床。
        
        Args:
            note: 帖子数据
            
        Returns:
            处理后的帖子数据（images 字段替换为图床链接）
        """
        if not self.image_uploader:
            return note
        
        images = note.get("images", [])
        if not images:
            return note
        
        print(f"[main] 处理帖子 {note.get('id', '')} 的 {len(images)} 张图片")
        
        new_images = []
        upload_success = 0
        upload_fail = 0
        
        for i, img_url in enumerate(images):
            print(f"[main] 上传第 {i+1}/{len(images)} 张图片: {img_url[:50]}...")
            
            result = self.image_uploader.upload_image(img_url)
            
            if result.get("success"):
                new_url = result.get("url", "")
                new_images.append(new_url)
                upload_success += 1
                print(f"[main] 上传成功: {new_url}")
            else:
                # 上传失败，保留原链接
                new_images.append(img_url)
                upload_fail += 1
                print(f"[main] 上传失败，保留原链接")
            
            # 上传间隔
            if i < len(images) - 1:
                time.sleep(0.5)
        
        # 更新帖子数据
        note["images"] = new_images
        note["images_upload_success"] = upload_success
        note["images_upload_fail"] = upload_fail
        
        print(f"[main] 图片上传完成: 成功 {upload_success}, 失败 {upload_fail}")
        return note
    
    def search_detail_and_store(
        self,
        keyword: str,
        limit: int = 5,
        sort_by: str = "general",
        delay: float = 2.0,
    ) -> Dict[str, Any]:
        """搜索、获取详情并存储到数据库。"""
        print(f"[main] 搜索并获取详情: {keyword}, 数量: {limit}")

        # 执行搜索和获取详情
        result = search_and_detail(keyword, limit, delay, sort_by)

        if not result.get("success", False):
            print(f"[main] 搜索失败: {result.get('error', '未知错误')}")
            return result

        notes = result.get("notes", [])
        print(f"[main] 获取到 {len(notes)} 条详情")
        
        # 如果启用图片上传，处理每张图片
        if self.upload_images and self.image_uploader:
            print(f"[main] 开始上传图片到图床...")
            total_images = sum(len(n.get("images", [])) for n in notes)
            print(f"[main] 共 {total_images} 张图片需要处理")
            
            processed_notes = []
            for note in notes:
                processed_note = self._process_images_for_note(note)
                processed_notes.append(processed_note)
            
            notes = processed_notes
            print(f"[main] 图片处理完成")

        # 存入数据库
        success_count = self.db.insert_notes_batch(notes, keyword, sort_by)
        print(f"[main] 成功入库 {success_count} 条帖子")

        result["stored_count"] = success_count
        return result

    def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息。"""
        return self.db.get_stats()

    def query_notes(self, keyword: str = None, limit: int = 50) -> list:
        """查询数据库中的帖子。"""
        return self.db.query_notes(keyword, limit)

    def check_browser_login(self) -> Dict[str, Any]:
        """检查浏览器登录状态。"""
        client = XHSCDPClient()
        return check_login(client)


def main():
    parser = argparse.ArgumentParser(
        prog="xhs-db",
        description="小红书搜索入库脚本",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init-db 命令
    sub = subparsers.add_parser("init-db", help="初始化数据库")
    sub.set_defaults(func=lambda a, x: print(json.dumps({"success": x.init()}, ensure_ascii=False)))

    # search 命令
    sub = subparsers.add_parser("search", help="搜索并入库")
    sub.add_argument("keyword", help="搜索关键词")
    sub.add_argument("--limit", "-n", type=int, default=10, help="结果数量")
    sub.add_argument("--sort", "-s", default="general", choices=["general", "popular", "latest"], help="排序方式")
    sub.set_defaults(func=lambda a, x: print(json.dumps(x.search_and_store(a.keyword, a.limit, a.sort), ensure_ascii=False, indent=2)))

    # search-detail 命令
    sub = subparsers.add_parser("search-detail", help="搜索获取详情并入库")
    sub.add_argument("keyword", help="搜索关键词")
    sub.add_argument("--limit", "-n", type=int, default=5, help="结果数量")
    sub.add_argument("--sort", "-s", default="general", choices=["general", "popular", "latest"], help="排序方式")
    sub.add_argument("--delay", "-d", type=float, default=2.0, help="请求间隔（秒）")
    sub.add_argument("--upload-images", "-u", action="store_true", help="上传图片到 Lsky Pro 图床")
    sub.set_defaults(func=lambda a, x: print(json.dumps(x.search_detail_and_store(a.keyword, a.limit, a.sort, a.delay), ensure_ascii=False, indent=2)))

    # stats 命令
    sub = subparsers.add_parser("stats", help="获取数据库统计")
    sub.set_defaults(func=lambda a, x: print(json.dumps(x.get_stats(), ensure_ascii=False, indent=2)))

    # query 命令
    sub = subparsers.add_parser("query", help="查询数据库帖子")
    sub.add_argument("--keyword", "-k", default=None, help="筛选关键词")
    sub.add_argument("--limit", "-n", type=int, default=50, help="结果数量")
    sub.set_defaults(func=lambda a, x: print(json.dumps(x.query_notes(a.keyword, a.limit), ensure_ascii=False, indent=2)))

    # check-login 命令
    sub = subparsers.add_parser("check-login", help="检查浏览器登录状态")
    sub.set_defaults(func=lambda a, x: print(json.dumps(x.check_browser_login(), ensure_ascii=False, indent=2)))

    # ==================== 定时任务和日志命令 ====================

    # start-scheduler 命令：启动定时任务
    sub = subparsers.add_parser("start-scheduler", help="启动定时搜索任务")
    sub.add_argument("--no-upload", "-n", action="store_true", help="禁用图片上传")
    sub.set_defaults(func=lambda a, x: _run_scheduler(a))

    # logs 命令：查看搜索日志
    sub = subparsers.add_parser("logs", help="查看搜索执行日志")
    sub.add_argument("--keyword", "-k", default=None, help="筛选关键词")
    sub.add_argument("--limit", "-n", type=int, default=20, help="日志数量")
    sub.set_defaults(func=lambda a, x: print(json.dumps(x.db.get_search_logs(a.keyword, a.limit), ensure_ascii=False, indent=2)))

    # ==================== Keywords 管理命令 ====================

    # keywords 命令：列出所有搜索词
    sub = subparsers.add_parser("keywords", help="列出所有配置的搜索词")
    sub.set_defaults(func=lambda a, x: print(json.dumps(x.db.get_keywords(), ensure_ascii=False, indent=2)))

    # add-keyword 命令：添加搜索词
    sub = subparsers.add_parser("add-keyword", help="添加搜索词")
    sub.add_argument("keyword", help="搜索关键词")
    sub.add_argument("--auto", "-a", action="store_true", help="启用自动搜索")
    sub.add_argument("--interval", "-i", type=int, default=24, help="自动搜索间隔（小时）")
    sub.set_defaults(func=lambda a, x: print(json.dumps(x.db.add_keyword(a.keyword, a.auto, a.interval), ensure_ascii=False, indent=2)))

    # remove-keyword 命令：删除搜索词
    sub = subparsers.add_parser("remove-keyword", help="删除搜索词")
    sub.add_argument("keyword", help="搜索关键词")
    sub.set_defaults(func=lambda a, x: print(json.dumps(x.db.remove_keyword(a.keyword), ensure_ascii=False, indent=2)))

    # enable-keyword 命令：启用自动搜索
    sub = subparsers.add_parser("enable-keyword", help="启用自动搜索")
    sub.add_argument("keyword", help="搜索关键词")
    sub.add_argument("--interval", "-i", type=int, default=24, help="自动搜索间隔（小时）")
    sub.set_defaults(func=lambda a, x: print(json.dumps(x.db.enable_auto_search(a.keyword, a.interval), ensure_ascii=False, indent=2)))

    # disable-keyword 命令：禁用自动搜索
    sub = subparsers.add_parser("disable-keyword", help="禁用自动搜索")
    sub.add_argument("keyword", help="搜索关键词")
    sub.set_defaults(func=lambda a, x: print(json.dumps(x.db.disable_auto_search(a.keyword), ensure_ascii=False, indent=2)))

    args = parser.parse_args()

    # 创建实例并初始化
    # 根据 --upload-images 参数决定是否启用图片上传
    upload_images = getattr(args, 'upload_images', False)
    xhs = XhsSearchToDB(upload_images=upload_images)

    # 执行命令（除了 init-db，其他命令都需要初始化数据库）
    if args.command != "init-db":
        if not xhs.init():
            print(json.dumps({"success": False, "error": "数据库初始化失败"}, ensure_ascii=False))
            sys.exit(1)

    args.func(args, xhs)


def _run_scheduler(args):
    """运行调度器。"""
    from scheduler import run_scheduler
    upload_images = not args.no_upload
    run_scheduler(upload_images=upload_images)
    return True


if __name__ == "__main__":
    main()