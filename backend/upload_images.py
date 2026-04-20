"""图片上传模块 - 将小红书图片上传到 Lsky Pro 图床。

功能：
1. 下载小红书图片到临时目录（使用 CDP 浏览器绕过防盗链）
2. 上传到 Lsky Pro 图床
3. 返回图床链接

配置：
- LSKY_PRO_URL: 图床服务地址
- LSKY_PRO_TOKEN: API Token (通过 /api/v1/tokens 获取)
- CDP 浏览器: Chrome 远程调试端口 9222（用于下载小红书图片）

用法：
    from upload_images import ImageUploader
    
    uploader = ImageUploader()
    result = uploader.upload_image("https://sns-webpic-qc.xhscdn.com/...")
    print(result["url"])  # 图床链接
"""

import os
import time
import json
import base64
import tempfile
import websocket  # 使用 websocket-client 库（更稳定）
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置常量
LSKY_PRO_URL = os.getenv("LSKY_PRO_URL", "http://192.168.100.4:5021")
LSKY_PRO_TOKEN = os.getenv("LSKY_PRO_TOKEN", "")
TEMP_DIR = Path(os.getenv("TEMP_DIR", "/tmp/xhs_images"))

# CDP 配置（用于下载小红书图片）
CDP_HOST = os.getenv("CDP_HOST", "127.0.0.1")
CDP_PORT = int(os.getenv("CDP_PORT", "9222"))

# 小红书 CDN 域名列表
XHS_CDN_DOMAINS = [
    "sns-webpic-qc.xhscdn.com",
    "sns-webpic-cn.xhscdn.com",
    "sns-webpic.xhscdn.com",
    "xhscdn.com",
]

class CDPError(Exception):
    """CDP 通信错误。"""


def is_xhs_image_url(url: str) -> bool:
    """判断 URL 是否为小红书 CDN 图片。"""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        for xhs_domain in XHS_CDN_DOMAINS:
            if xhs_domain in domain or domain.endswith(xhs_domain):
                return True
        return False
    except Exception:
        return False


def connect_to_cdp_url(host: str = CDP_HOST, port: int = CDP_PORT, create_new: bool = True) -> str:
    """获取 CDP WebSocket URL。
    
    Args:
        host: CDP 主机地址
        port: CDP 端口
        create_new: 是否创建新页面（推荐）
        
    Returns:
        WebSocket URL
    """
    base_url = f"http://{host}:{port}"
    
    if create_new:
        try:
            print(f"[CDP] 创建新空白页面...")
            resp = requests.put(f"{base_url}/json/new?about:blank", timeout=10)
            resp.raise_for_status()
            new_page = resp.json()
            ws_url = new_page.get("webSocketDebuggerUrl", "")
            if ws_url:
                print(f"[CDP] 新页面 WebSocket URL: {ws_url[:50]}...")
                return ws_url
        except Exception as e:
            print(f"[CDP] 创建新页面失败: {e}")
    
    # 获取现有页面
    try:
        resp = requests.get(f"{base_url}/json/list", timeout=5)
        resp.raise_for_status()
        pages = resp.json()
        
        # 找一个可用的 page
        for page in pages:
            if page.get("type") == "page" and page.get("webSocketDebuggerUrl"): 
                url = page.get("url", "")
                # 跳过图片 URL 页面
                if "sns-webpic" in url or "xhscdn.com" in url:
                    continue
                ws_url = page.get("webSocketDebuggerUrl", "")
                if ws_url:
                    print(f"[CDP] 使用现有页面: {url[:50]}...")
                    return ws_url
        
        # fallback: 使用第一个 page
        ws_url = pages[0].get("webSocketDebuggerUrl", "")
        if ws_url:
            return ws_url
        
    except Exception as e:
        raise CDPError(f"无法获取 CDP 页面: {e}")
    
    raise CDPError("没有可用的 CDP 页面")


def connect_to_cdp(host: str = CDP_HOST, port: int = CDP_PORT, create_new: bool = True) -> Any:
    """连接到 CDP 浏览器。
    
    Args:
        host: CDP 主机地址
        port: CDP 端口
        create_new: 是否创建新页面（推荐，避免干扰现有页面）
    """
    ws_url = connect_to_cdp_url(host, port, create_new)
    return websocket.create_connection(ws_url, timeout=10)


def download_image_via_cdp(image_url: str, timeout: float = 30.0, max_retries: int = 2) -> bytes:
    """使用 CDP 浏览器下载图片（绕过防盗链）。
    
    简化方法：创建新页面，导航到图片 URL，截图获取图片。
    
    Args:
        image_url: 图片 URL
        timeout: 下载超时时间
        max_retries: 最大重试次数
        
    Returns:
        图片二进制数据
    """
    ws = None
    msg_id = 0
    
    for retry in range(max_retries):
        try:
            print(f"[upload_images] 通过 CDP 下载图片 (尝试 {retry+1}/{max_retries}): {image_url[:80]}...")
            
            # 连接到 CDP 浏览器（创建新页面）
            ws_url = connect_to_cdp_url(create_new=True)
            ws = websocket.create_connection(ws_url, timeout=10)
            print(f"[CDP] WebSocket 连接成功")
            
            def send_cdp(method: str, params: dict = None) -> dict:
                """发送 CDP 命令。"""
                nonlocal msg_id
                msg_id += 1
                msg = {"id": msg_id, "method": method}
                if params:
                    msg["params"] = params
                ws.send(json.dumps(msg))
                
                # 等待响应
                while True:
                    try:
                        raw = ws.recv()
                        data = json.loads(raw)
                        if data.get("id") == msg_id:
                            if "error" in data:
                                raise CDPError(f"CDP 错误: {data['error']}")
                            return data.get("result", {})
                    except websocket.WebSocketTimeoutException:
                        raise CDPError(f"等待 CDP 响应超时: {method}")
            
            # 等待页面初始化
            time.sleep(0.5)
            
            # 导航到图片 URL
            print(f"[CDP] 导航到图片 URL...")
            result = send_cdp("Page.navigate", {"url": image_url})
            
            # 等待页面加载
            time.sleep(2.0)
            
            # 获取视口大小
            result = send_cdp("Page.getLayoutMetrics")
            content_size = result.get("contentSize", {})
            width = int(content_size.get("width", 800))
            height = int(content_size.get("height", 600))
            print(f"[CDP] 页面大小: {width}x{height}")
            
            # 截图
            result = send_cdp("Page.captureScreenshot", {
                "format": "png",
                "clip": {
                    "x": 0, "y": 0,
                    "width": width, "height": height,
                    "scale": 1
                }
            })
            
            screenshot_data = result.get("data", "")
            if screenshot_data:
                image_bytes = base64.b64decode(screenshot_data)
                print(f"[CDP] 截图成功！大小: {len(image_bytes)} bytes ({len(image_bytes)/1024:.1f} KB)")
                return image_bytes
            
            raise CDPError("无法获取图片数据")
            
        except CDPError as e:
            print(f"[upload_images] CDP 下载失败 (尝试 {retry+1}/{max_retries}): {e}")
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass
                ws = None
            if retry < max_retries - 1:
                time.sleep(2.0)
                continue
            raise
        
        except Exception as e:
            print(f"[upload_images] CDP 异常: {e}")
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass
                ws = None
            if retry < max_retries - 1:
                time.sleep(2.0)
                continue
            raise CDPError(f"CDP 下载失败: {e}")
    
    raise CDPError("CDP 下载失败：超过最大重试次数")



class ImageUploader:
    """图片上传器，将图片下载并上传到 Lsky Pro 图床。"""
    
    def __init__(self, lsky_url: str = None, lsky_token: str = None):
        self.lsky_url = lsky_url or LSKY_PRO_URL
        self.token = lsky_token or LSKY_PRO_TOKEN
        self.temp_dir = TEMP_DIR
        
        # 创建临时目录
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查是否已配置 Token
        if not self.token:
            print("[upload_images] 警告: 未配置 LSKY_PRO_TOKEN，将自动获取")
            self.token = self._get_token()
        
        if not self.token:
            raise ValueError("[upload_images] 无法获取 Lsky Pro Token")
    
    def _get_token(self) -> str:
        """通过 API 获取 Token。"""
        # 从环境变量获取账号密码
        email = os.getenv("LSKY_PRO_EMAIL", "admin@xhs.local")
        password = os.getenv("LSKY_PRO_PASSWORD", "XhsAdmin123")
        
        try:
            resp = requests.post(
                f"{self.lsky_url}/api/v1/tokens",
                json={"email": email, "password": password},
                headers={"Accept": "application/json"},
                timeout=10
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") and data.get("data", {}).get("token"):
                    token = data["data"]["token"]
                    print(f"[upload_images] 成功获取 Token: {token}")
                    return token
        except Exception as e:
            print(f"[upload_images] 获取 Token 失败: {e}")
        
        return ""
    
    def download_image(self, url: str, timeout: float = 30.0) -> Optional[Path]:
        """下载图片到临时目录。
        
        Args:
            url: 图片 URL
            timeout: 下载超时时间
            
        Returns:
            本地文件路径，失败返回 None
        """
        if not url:
            return None
        
        # 生成临时文件名
        try:
            parsed = urlparse(url)
            ext = ".jpg"  # 默认扩展名
            for possible_ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                if possible_ext in parsed.path.lower():
                    ext = possible_ext
                    break
            
            # 使用时间戳生成唯一文件名
            filename = f"xhs_{int(time.time() * 1000)}{ext}"
            filepath = self.temp_dir / filename
            
        except Exception:
            filepath = self.temp_dir / f"xhs_{int(time.time() * 1000)}.jpg"
        
        # 判断是否为小红书 CDN 图片
        if is_xhs_image_url(url):
            # 使用 CDP 浏览器下载（绕过防盗链）
            try:
                print(f"[upload_images] 小红书图片，使用 CDP 下载: {url[:80]}...")
                image_data = download_image_via_cdp(url, timeout)
                
                # 写入文件
                with open(filepath, "wb") as f:
                    f.write(image_data)
                
                print(f"[upload_images] CDP 下载完成: {filepath} ({len(image_data)} bytes)")
                return filepath
                
            except CDPError as e:
                print(f"[upload_images] CDP 下载失败: {e}")
                return None
            except Exception as e:
                print(f"[upload_images] CDP 下载异常: {e}")
                return None
        
        else:
            # 非 Xbox CDN 图片，使用 requests 直接下载
            try:
                print(f"[upload_images] 非 Xbox CDN 图片，直接下载: {url[:80]}...")
                
                # 添加 headers 模拟浏览器请求
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.xiaohongshu.com/",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                }
                
                resp = requests.get(url, headers=headers, timeout=timeout, stream=True)
                resp.raise_for_status()
                
                # 写入文件
                with open(filepath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                print(f"[upload_images] 下载完成: {filepath}")
                return filepath
                
            except Exception as e:
                print(f"[upload_images] 下载失败: {e}")
                return None
    
    def upload_to_lsky(self, filepath: Path) -> Dict[str, Any]:
        """上传图片到 Lsky Pro 图床。
        
        Args:
            filepath: 本地图片路径
            
        Returns:
            上传结果，包含 url, key, name 等
        """
        if not filepath or not filepath.exists():
            return {"success": False, "error": "文件不存在"}
        
        try:
            print(f"[upload_images] 上传图片: {filepath}")
            
            with open(filepath, "rb") as f:
                files = {"file": (filepath.name, f, "image/jpeg")}
                headers = {
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                }
                
                resp = requests.post(
                    f"{self.lsky_url}/api/v1/upload",
                    files=files,
                    headers=headers,
                    timeout=30
                )
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status"):
                    links = data.get("data", {}).get("links", {})
                    result = {
                        "success": True,
                        "url": links.get("url", ""),
                        "key": data.get("data", {}).get("key", ""),
                        "name": data.get("data", {}).get("name", ""),
                        "thumbnail": links.get("thumbnail_url", ""),
                        "md5": data.get("data", {}).get("md5", ""),
                    }
                    print(f"[upload_images] 上传成功: {result['url']}")
                    return result
                else:
                    error = data.get("message", "未知错误")
                    print(f"[upload_images] 上传失败: {error}")
                    return {"success": False, "error": error}
            else:
                print(f"[upload_images] 上传失败: HTTP {resp.status_code}")
                return {"success": False, "error": f"HTTP {resp.status_code}", "response": resp.text[:200]}
                
        except Exception as e:
            print(f"[upload_images] 上传异常: {e}")
            return {"success": False, "error": str(e)}
    
    def upload_image(self, url: str, cleanup: bool = True) -> Dict[str, Any]:
        """下载并上传图片（一站式）。
        
        Args:
            url: 小红书图片 URL
            cleanup: 是否清理临时文件
            
        Returns:
            上传结果，包含 url（图床链接）
        """
        # 下载
        filepath = self.download_image(url)
        if not filepath:
            return {"success": False, "error": "下载失败", "original_url": url}
        
        # 上传
        result = self.upload_to_lsky(filepath)
        result["original_url"] = url
        
        # 清理临时文件
        if cleanup and filepath.exists():
            try:
                filepath.unlink()
            except Exception:
                pass
        
        return result
    
    def upload_images_batch(self, urls: List[str], delay: float = 0.5) -> List[Dict[str, Any]]:
        """批量上传图片。
        
        Args:
            urls: 图片 URL 列表
            delay: 每次上传间隔（秒）
            
        Returns:
            上传结果列表
        """
        results = []
        for i, url in enumerate(urls):
            print(f"[upload_images] 处理第 {i+1}/{len(urls)} 张图片")
            result = self.upload_image(url)
            results.append(result)
            
            # 间隔等待
            if i < len(urls) - 1 and delay > 0:
                time.sleep(delay)
        
        return results
    
    def get_upload_stats(self) -> Dict[str, Any]:
        """获取上传统计信息。"""
        success_count = 0
        fail_count = 0
        
        return {
            "lsky_url": self.lsky_url,
            "token_valid": bool(self.token),
            "temp_dir": str(self.temp_dir),
        }


def test_uploader():
    """测试上传功能。"""
    print("=== 测试图片上传模块 ===")
    
    # 测试图片 URL (小红书格式)
    test_url = "https://sns-webpic-qc.xhscdn.com/hd_test.jpg"
    
    uploader = ImageUploader()
    
    # 测试下载
    print("\n1. 测试下载功能")
    filepath = uploader.download_image(test_url)
    if filepath:
        print(f"下载成功: {filepath}")
        filepath.unlink()  # 清理
    else:
        print("下载测试失败（需要真实 URL）")
    
    # 测试上传（使用本地测试图片）
    print("\n2. 测试上传功能")
    test_img = Path("/tmp/test_upload.png")
    if test_img.exists():
        result = uploader.upload_to_lsky(test_img)
        print(f"上传结果: {result}")
    else:
        # 创建测试图片
        try:
            from PIL import Image
            img = Image.new('RGB', (100, 100), color='blue')
            img.save(test_img)
            result = uploader.upload_to_lsky(test_img)
            print(f"上传结果: {result}")
            test_img.unlink()
        except ImportError:
            print("PIL 未安装，跳过上传测试")
    
    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    test_uploader()