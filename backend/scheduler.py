"""小红书自动搜索定时任务模块。

功能：
1. 定时执行搜索任务（随机时间间隔，防封号）
2. 自动跳过重复帖子
3. 支持图片上传到图床
4. 记录详细执行日志

用法：
    python main.py start-scheduler
"""

import random
import time
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List

from db import XhsDatabase
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 导入搜索模块
try:
    from xhs_search_cdp import search_and_detail, XHSCDPClient
except ImportError:
    print("[scheduler] 错误: 无法导入 xhs_search_cdp 模块")
    sys.exit(1)

# 导入图片上传模块
try:
    from upload_images import ImageUploader
except ImportError:
    print("[scheduler] 警告: 无法导入 upload_images 模块，图片上传功能不可用")
    ImageUploader = None


class SchedulerConfig:
    """调度器配置。"""
    
    # 基础周期：10分钟
    BASE_CYCLE_SECONDS = 600
    
    # 随机等待范围（周期开始前）
    RANDOM_WAIT_MIN = 0
    RANDOM_WAIT_MAX = 600  # 0-10分钟
    
    # 搜索间隔随机等待（防封号）
    SEARCH_DELAY_MIN = 3
    SEARCH_DELAY_MAX = 8
    
    # 详情获取间隔
    DETAIL_DELAY_MIN = 2
    DETAIL_DELAY_MAX = 5
    
    # 每次搜索帖子数
    SEARCH_LIMIT = 10
    
    # 图片上传间隔
    IMAGE_UPLOAD_DELAY = 0.5


class XhsScheduler:
    """小红书定时搜索调度器。"""
    
    def __init__(self, upload_images: bool = True):
        self.db = XhsDatabase()
        self.upload_images = upload_images
        self.image_uploader = None
        self.running = False
        
        # 初始化图片上传器
        if upload_images and ImageUploader:
            try:
                self.image_uploader = ImageUploader()
                print("[scheduler] 图片上传功能已启用")
            except Exception as e:
                print(f"[scheduler] 图片上传器初始化失败: {e}")
                self.upload_images = False
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """处理终止信号。"""
        print(f"\n[scheduler] 收到终止信号 {signum}，正在停止...")
        self.running = False
    
    def init(self) -> bool:
        """初始化数据库。"""
        if not self.db.init_database():
            print("[scheduler] 数据库初始化失败")
            return False
        return True
    
    def should_search(self, keyword_config: Dict[str, Any]) -> bool:
        """检查是否应该执行搜索。
        
        Args:
            keyword_config: 关键词配置（包含 search_interval, last_search_time）
            
        Returns:
            True: 需要执行搜索
            False: 还不到搜索时间
        """
        search_interval = keyword_config.get('search_interval', 24)  # 小时
        last_search_time = keyword_config.get('last_search_time')
        
        if not last_search_time:
            # 没有上次搜索记录，应该执行
            return True
        
        # 解析时间
        if isinstance(last_search_time, str):
            try:
                last_search_time = datetime.fromisoformat(last_search_time)
            except ValueError:
                return True
        
        # 计算间隔
        next_search_time = last_search_time + timedelta(hours=search_interval)
        now = datetime.now()
        
        return now >= next_search_time
    
    def _process_images_for_note(self, note: Dict[str, Any]) -> Dict[str, Any]:
        """处理单个帖子的图片，上传到图床。
        
        Returns:
            处理后的帖子数据，包含上传统计
        """
        if not self.image_uploader:
            return note
        
        images = note.get("images", [])
        if not images:
            note["images_upload_success"] = 0
            note["images_upload_fail"] = 0
            return note
        
        print(f"[scheduler] 处理帖子 {note.get('id', '')} 的 {len(images)} 张图片")
        
        new_images = []
        upload_success = 0
        upload_fail = 0
        
        for i, img_url in enumerate(images):
            print(f"[scheduler] 上传第 {i+1}/{len(images)} 张图片...")
            
            result = self.image_uploader.upload_image(img_url)
            
            if result.get("success"):
                new_url = result.get("url", "")
                new_images.append(new_url)
                upload_success += 1
            else:
                # 上传失败，保留原链接
                new_images.append(img_url)
                upload_fail += 1
            
            # 上传间隔
            if i < len(images) - 1:
                time.sleep(SchedulerConfig.IMAGE_UPLOAD_DELAY)
        
        note["images"] = new_images
        note["images_upload_success"] = upload_success
        note["images_upload_fail"] = upload_fail
        
        return note
    
    def execute_search(self, keyword: str) -> Dict[str, Any]:
        """执行单次搜索任务。
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            执行结果统计
        """
        start_time = time.time()
        
        result = {
            "keyword": keyword,
            "posts_found": 0,
            "posts_inserted": 0,
            "posts_skipped": 0,
            "images_found": 0,
            "images_uploaded": 0,
            "images_failed": 0,
            "duration_seconds": 0,
            "error": None,
        }
        
        try:
            print(f"[scheduler] 开始搜索: {keyword}")
            
            # 执行搜索（获取详情）
            search_result = search_and_detail(
                keyword,
                limit=SchedulerConfig.SEARCH_LIMIT,
                delay=random.uniform(SchedulerConfig.DETAIL_DELAY_MIN, SchedulerConfig.DETAIL_DELAY_MAX),
                sort_by="general"
            )
            
            if not search_result.get("success", False):
                result["error"] = search_result.get("error", "搜索失败")
                print(f"[scheduler] 搜索失败: {result['error']}")
                return result
            
            notes = search_result.get("notes", [])
            result["posts_found"] = len(notes)
            print(f"[scheduler] 搜索到 {len(notes)} 条帖子")
            
            # 处理每个帖子
            for note in notes:
                note_id = note.get("id", "")
                note_url = note.get("url", "")
                
                # 随机等待（防封号）
                wait_time = random.uniform(SchedulerConfig.DETAIL_DELAY_MIN, SchedulerConfig.DETAIL_DELAY_MAX)
                print(f"[scheduler] 等待 {wait_time:.1f} 秒...")
                time.sleep(wait_time)
                
                # 检查是否重复
                if self.db.is_note_exists(note_id=note_id, url=note_url):
                    print(f"[scheduler] 跳过重复帖子: {note_id}")
                    result["posts_skipped"] += 1
                    continue
                
                # 处理图片上传
                if self.upload_images:
                    note = self._process_images_for_note(note)
                    result["images_found"] += len(note.get("images", []))
                    result["images_uploaded"] += note.get("images_upload_success", 0)
                    result["images_failed"] += note.get("images_upload_fail", 0)
                
                # 存入数据库
                if self.db.insert_note(note, keyword, "general"):
                    result["posts_inserted"] += 1
                    print(f"[scheduler] 入库成功: {note_id}")
                else:
                    result["posts_skipped"] += 1
            
            # 更新上次搜索时间
            self.db.update_last_search_time(keyword)
            
        except Exception as e:
            result["error"] = str(e)
            print(f"[scheduler] 执行异常: {e}")
        
        result["duration_seconds"] = int(time.time() - start_time)
        return result
    
    def run_cycle(self):
        """执行一个完整的搜索周期。"""
        print(f"[scheduler] ===== 开始搜索周期 =====")
        print(f"[scheduler] 时间: {datetime.now().isoformat()}")
        
        # 获取需要自动搜索的关键词
        keywords = self.db.get_auto_search_keywords()
        
        if not keywords:
            print("[scheduler] 没有需要自动搜索的关键词")
            return
        
        print(f"[scheduler] 找到 {len(keywords)} 个自动搜索关键词")
        
        for keyword_config in keywords:
            keyword = keyword_config.get('keyword')
            
            # 检查是否应该执行搜索
            if not self.should_search(keyword_config):
                print(f"[scheduler] 跳过 {keyword}：未到搜索时间")
                continue
            
            # 随机等待（防封号）
            wait_time = random.uniform(SchedulerConfig.SEARCH_DELAY_MIN, SchedulerConfig.SEARCH_DELAY_MAX)
            print(f"[scheduler] 搜索前等待 {wait_time:.1f} 秒...")
            time.sleep(wait_time)
            
            # 执行搜索
            result = self.execute_search(keyword)
            
            # 记录日志
            self.db.log_search_result(
                keyword=result["keyword"],
                posts_found=result["posts_found"],
                posts_inserted=result["posts_inserted"],
                posts_skipped=result["posts_skipped"],
                images_found=result["images_found"],
                images_uploaded=result["images_uploaded"],
                images_failed=result["images_failed"],
                duration_seconds=result["duration_seconds"],
                error_message=result["error"],
            )
            
            print(f"[scheduler] 搜索完成: {keyword}")
            print(f"[scheduler] 发现: {result['posts_found']}, 入库: {result['posts_inserted']}, 跳过: {result['posts_skipped']}")
            print(f"[scheduler] 图片: 发现 {result['images_found']}, 上传 {result['images_uploaded']}, 失败 {result['images_failed']}")
            print(f"[scheduler] 耗时: {result['duration_seconds']} 秒")
        
        print(f"[scheduler] ===== 周期结束 =====")
    
    def run_scheduler(self):
        """运行调度器主循环。"""
        print("[scheduler] 调度器启动")
        print(f"[scheduler] 周期: {SchedulerConfig.BASE_CYCLE_SECONDS} 秒 (约10分钟)")
        print(f"[scheduler] 图片上传: {'启用' if self.upload_images else '禁用'}")
        
        self.running = True
        
        while self.running:
            # 随机等待 0-10 分钟
            wait_time = random.randint(SchedulerConfig.RANDOM_WAIT_MIN, SchedulerConfig.RANDOM_WAIT_MAX)
            print(f"[scheduler] 周期开始前随机等待 {wait_time} 秒 ({wait_time/60:.1f} 分钟)...")
            
            # 分段等待，以便响应终止信号
            while wait_time > 0 and self.running:
                sleep_chunk = min(wait_time, 10)  # 每10秒检查一次
                time.sleep(sleep_chunk)
                wait_time -= sleep_chunk
            
            if not self.running:
                break
            
            # 执行搜索周期
            self.run_cycle()
            
            # 等待下一个周期（补足剩余时间）
            remaining_time = SchedulerConfig.BASE_CYCLE_SECONDS - wait_time
            if remaining_time > 0 and self.running:
                print(f"[scheduler] 等待下一个周期: {remaining_time} 秒...")
                while remaining_time > 0 and self.running:
                    sleep_chunk = min(remaining_time, 10)
                    time.sleep(sleep_chunk)
                    remaining_time -= sleep_chunk
        
        print("[scheduler] 调度器已停止")


def run_scheduler(upload_images: bool = True):
    """启动调度器（入口函数）。"""
    scheduler = XhsScheduler(upload_images=upload_images)
    
    if not scheduler.init():
        print("[scheduler] 初始化失败，退出")
        return False
    
    scheduler.run_scheduler()
    return True


if __name__ == "__main__":
    run_scheduler()