"""小红书搜索脚本 - CDP 版本（使用已部署的 Chrome DevTools Protocol 浏览器）。

功能：
1. search: 根据关键词搜索小红书帖子
2. detail: 获取帖子详细信息（标题、内容、图片、点赞、收藏等）
3. search_detail: 搜索并批量获取详情
4. check-login: 检查浏览器登录状态

前置条件：
- Chrome/Chromium 浏览器已启动并开启远程调试端口（默认 9222）
- 浏览器中已登录小红书账号

输出: JSON 格式
"""

import argparse
import json
import sys
import time
import base64
import re
from typing import Any, Optional
from pathlib import Path
from urllib.parse import urlencode

import requests
import websockets.sync.client as ws_client

# 输出文件目录
OUTPUT_DIR = Path("/tmp/xhs_search")

# CDP 配置
CDP_HOST = "127.0.0.1"
CDP_PORT = 9222

# URL 常量
SEARCH_BASE_URL = "https://www.xiaohongshu.com/search_result"
XHS_HOME_URL = "https://www.xiaohongshu.com"


class CDPError(Exception):
    """CDP 通信错误。"""


class XHSCDPClient:
    """小红书 CDP 客户端，连接到已部署的 Chrome 浏览器。"""

    def __init__(self, host: str = CDP_HOST, port: int = CDP_PORT):
        self.host = host
        self.port = port
        self.ws: Optional[ws_client.WebSocketClientConnection] = None
        self._msg_id = 0
        self.target_id: Optional[str] = None

    def _get_targets(self) -> list[dict]:
        """获取浏览器所有 targets（tabs）。"""
        url = f"http://{self.host}:{self.port}/json"
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise CDPError(f"无法连接到 Chrome ({self.host}:{self.port}): {e}")

    def _find_or_create_tab(self, target_url_prefix: str = "") -> str:
        """找到或创建一个 tab，返回 WebSocket URL。"""
        targets = self._get_targets()
        pages = [
            t for t in targets
            if t.get("type") == "page" and t.get("webSocketDebuggerUrl")
        ]

        # 如果指定了 URL 前缀，优先找匹配的 tab
        if target_url_prefix:
            for t in pages:
                if t.get("url", "").startswith(target_url_prefix):
                    self.target_id = t.get("id")
                    return t["webSocketDebuggerUrl"]

        # 否则找小红书相关的 tab
        for t in pages:
            url = t.get("url", "")
            if "xiaohongshu.com" in url:
                self.target_id = t.get("id")
                return t["webSocketDebuggerUrl"]

        # 创建新 tab
        try:
            resp = requests.put(
                f"http://{self.host}:{self.port}/json/new?about:blank",
                timeout=5,
            )
            if resp.ok:
                data = resp.json()
                self.target_id = data.get("id")
                return data.get("webSocketDebuggerUrl", "")
        except Exception:
            pass

        # Fallback: 使用第一个可用的 page
        if pages:
            self.target_id = pages[0].get("id")
            return pages[0]["webSocketDebuggerUrl"]

        raise CDPError("没有可用的浏览器 tab")

    def connect(self, target_url_prefix: str = ""):
        """连接到浏览器 tab。"""
        ws_url = self._find_or_create_tab(target_url_prefix)
        if not ws_url:
            raise CDPError("无法获取 WebSocket URL")

        print(f"[xhs_cdp] 连接到: {ws_url}")
        self.ws = ws_client.connect(ws_url)
        print("[xhs_cdp] 已连接")

    def disconnect(self):
        """断开连接。"""
        if self.ws:
            self.ws.close()
            self.ws = None

    def _send(self, method: str, params: dict = None, timeout: float = 30.0) -> dict:
        """发送 CDP 命令并等待响应。"""
        if not self.ws:
            raise CDPError("未连接，请先调用 connect()")

        self._msg_id += 1
        msg_id = self._msg_id
        msg = {"id": msg_id, "method": method}
        if params:
            msg["params"] = params

        self.ws.send(json.dumps(msg))
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CDPError(f"等待 CDP 响应超时: {method}")

            try:
                raw = self.ws.recv(timeout=max(0.1, remaining))
            except TimeoutError:
                raise CDPError(f"等待 CDP 响应超时: {method}")

            data = json.loads(raw)
            if data.get("id") == msg_id:
                if "error" in data:
                    raise CDPError(f"CDP 错误: {data['error']}")
                return data.get("result", {})

        raise CDPError(f"等待 CDP 响应超时: {method}")

    def _evaluate(self, expression: str, timeout: float = 30.0) -> Any:
        """执行 JavaScript 并返回结果值。"""
        result = self._send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            timeout=timeout,
        )
        remote_obj = result.get("result", {})
        if remote_obj.get("subtype") == "error":
            raise CDPError(f"JS 执行错误: {remote_obj.get('description', remote_obj)}")
        return remote_obj.get("value")

    def _navigate(self, url: str, wait_time: float = 3.0):
        """导航到 URL。"""
        print(f"[xhs_cdp] 导航到: {url}")
        self._send("Page.enable")
        self._send("Page.navigate", {"url": url})
        time.sleep(wait_time)

    def _wait_for_load(self, timeout: float = 30.0):
        """等待页面加载完成。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                state = self._evaluate("document.readyState")
                if state == "complete":
                    return
            except CDPError:
                pass
            time.sleep(0.5)

    def _wait_for_initial_state(self, timeout: float = 20.0):
        """等待 __INITIAL_STATE__ 就绪。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                ready = self._evaluate("window.__INITIAL_STATE__ !== undefined")
                if ready:
                    return
            except CDPError:
                pass
            time.sleep(0.5)
        print("[xhs_cdp] 等待 __INITIAL_STATE__ 超时")

    def _wait_for_search_state(self, timeout: float = 25.0):
        """等待搜索结果就绪。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                ready = self._evaluate("""
                    window.__INITIAL_STATE__ &&
                    window.__INITIAL_STATE__.search &&
                    window.__INITIAL_STATE__.search.feeds
                """)
                if ready:
                    return
            except CDPError:
                pass
            time.sleep(0.6)
        print("[xhs_cdp] 等待搜索结果超时")

    def _wait_for_detail_state(self, timeout: float = 25.0):
        """等待详情页就绪。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                ready = self._evaluate("""
                    window.__INITIAL_STATE__ &&
                    window.__INITIAL_STATE__.note &&
                    window.__INITIAL_STATE__.note.noteDetailMap
                """)
                if ready:
                    return
            except CDPError:
                pass
            time.sleep(0.6)
        print("[xhs_cdp] 等待详情数据超时")


def make_search_url(keyword: str) -> str:
    """构建搜索 URL。"""
    params = urlencode({"keyword": keyword.strip(), "source": "web_explore_feed"})
    return f"{SEARCH_BASE_URL}?{params}"


def make_feed_detail_url(feed_id: str, xsec_token: str) -> str:
    """构建帖子详情 URL（手机端可打开格式）。"""
    return f"https://www.xiaohongshu.com/discovery/item/{feed_id}?source=webshare&xhsshare=pc_web&xsec_token={xsec_token}&xsec_source=pc_share"


def extract_note_id(url: str) -> str:
    """从 URL 中提取 note_id。"""
    match = re.search(r"/explore/([a-f0-9]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"noteId=([a-f0-9]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"^[a-f0-9]{24}$", url)
    if match:
        return url
    return "unknown"


def format_search_results(feeds: list[dict]) -> list[dict]:
    """格式化搜索结果。"""
    formatted = []
    for feed in feeds:
        if not isinstance(feed, dict):
            continue

        note_card = feed.get("noteCard", {})
        user = note_card.get("user", {})
        interact_info = note_card.get("interactInfo", {})
        cover = note_card.get("cover", {})

        # 提取所有图片链接
        images = []
        # 优先从 imageList 提取
        for img in note_card.get("imageList", []) or []:
            img_url = img.get("urlDefault") or img.get("url") or img.get("urlDefaultWatermark")
            if img_url:
                images.append(img_url)
        # 如果没有 imageList，使用 cover
        if not images:
            cover_url = cover.get("urlDefault") or cover.get("url")
            if cover_url:
                images.append(cover_url)

        item = {
            "id": feed.get("id", ""),
            "url": f"https://www.xiaohongshu.com/explore/{feed.get('id', '')}",
            "xsec_token": feed.get("xsecToken", ""),
            "title": note_card.get("displayTitle", ""),
            "type": note_card.get("type", ""),
            "likes": interact_info.get("likedCount", "0"),
            "collects": interact_info.get("collectedCount", "0"),
            "comments": interact_info.get("commentCount", "0"),
            "author": {
                "id": user.get("userId", ""),
                "name": user.get("nickname", ""),
            },
            "cover": cover.get("urlDefault", cover.get("url", "")),
            "images": images,  # 所有图片链接数组
        }

        # 构建完整 URL（手机端可打开格式）
        if item["id"] and item["xsec_token"]:
            item["url"] = f"https://www.xiaohongshu.com/discovery/item/{item['id']}?source=webshare&xhsshare=pc_web&xsec_token={item['xsec_token']}&xsec_source=pc_share"

        formatted.append(item)

    return formatted


def format_detail_result(data: dict) -> dict:
    """格式化帖子详情。"""
    note = data.get("note", {})
    user = note.get("user", {})
    interact_info = note.get("interactInfo", {})

    # 提取所有图片链接（优先高清链接）
    images = []
    for img in note.get("imageList", []) or []:
        # 优先使用默认链接，其次水印链接，最后原始链接
        img_url = img.get("urlDefault") or img.get("urlDefaultWatermark") or img.get("url")
        if img_url:
            images.append(img_url)

    # 提取视频封面（如果有）
    video_cover = ""
    if note.get("type") == "video":
        video = note.get("video", {})
        video_cover = video.get("cover", {}).get("urlDefault", "")

    return {
        "id": note.get("noteId", ""),
        "title": note.get("title", ""),
        "content": note.get("desc", ""),
        "type": note.get("type", ""),
        "images": images,  # 所有图片链接数组
        "video_cover": video_cover,  # 视频封面（如果是视频笔记）
        "likes": interact_info.get("likedCount", "0"),
        "collects": interact_info.get("collectedCount", "0"),
        "comments": interact_info.get("commentCount", "0"),
        "shares": interact_info.get("sharedCount", "0"),
        "author": {
            "id": user.get("userId", ""),
            "name": user.get("nickname", ""),
            "avatar": user.get("avatar", ""),
        },
        "ip_location": note.get("ipLocation", ""),
        "time": note.get("time", 0),
    }


def check_login(client: XHSCDPClient) -> dict:
    """检查登录状态。"""
    try:
        client.connect("xiaohongshu.com")
        client._navigate(XHS_HOME_URL)
        client._wait_for_load()

        # 检查是否有登录弹窗关键词
        login_keywords = [
            "登录后推荐更懂你的笔记",
            "请登录",
            "扫码登录",
        ]

        page_text = client._evaluate("document.body ? document.body.innerText : ''")
        if isinstance(page_text, str):
            for kw in login_keywords:
                if kw in page_text:
                    return {
                        "logged_in": False,
                        "message": f"未登录，检测到关键词: {kw}",
                        "hint": "请在浏览器中登录小红书账号",
                    }

        # 检查是否有用户信息
        has_user = client._evaluate("""
            document.querySelector('.user-info, .nickname, [class*="user"]') !== null ||
            (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.user)
        """)

        if has_user:
            return {
                "logged_in": True,
                "message": "已登录",
            }

        return {
            "logged_in": False,
            "message": "未检测到登录状态",
            "hint": "请在浏览器中登录小红书账号",
        }

    except CDPError as e:
        return {
            "logged_in": False,
            "message": "连接失败",
            "error": str(e),
            "hint": "请确保 Chrome 浏览器已启动并开启远程调试端口 9222",
        }
    finally:
        client.disconnect()


def search_notes(keyword: str, limit: int = 10, sort_by: str = "general") -> dict:
    """搜索小红书笔记。

    Args:
        keyword: 搜索关键词
        limit: 返回结果数量
        sort_by: 排序方式 (general/popular/latest)
    """
    print(f"[xhs_cdp] 搜索关键词: {keyword}, 排序: {sort_by}")

    client = XHSCDPClient()
    try:
        # 连接到浏览器
        client.connect("xiaohongshu.com")

        # 导航到搜索页
        search_url = make_search_url(keyword)
        client._navigate(search_url)
        client._wait_for_load()
        client._wait_for_initial_state()
        client._wait_for_search_state()

        # 提取搜索结果
        raw = client._evaluate("""
            (() => {
                if (
                    window.__INITIAL_STATE__ &&
                    window.__INITIAL_STATE__.search &&
                    window.__INITIAL_STATE__.search.feeds
                ) {
                    const feeds = window.__INITIAL_STATE__.search.feeds;
                    const data = feeds.value !== undefined ? feeds.value : feeds._value;
                    if (data) {
                        return JSON.stringify(data);
                    }
                }
                return "";
            })()
        """)

        if not raw or not isinstance(raw, str):
            return {
                "success": False,
                "error": "未获取到搜索结果",
                "hint": "可能未登录或关键词无效",
            }

        try:
            feeds = json.loads(raw)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"解析搜索结果失败: {e}",
            }

        if not isinstance(feeds, list):
            return {
                "success": False,
                "error": "搜索结果格式异常",
            }

        # 格式化并限制数量
        formatted = format_search_results(feeds)[:limit]

        output = {
            "success": True,
            "keyword": keyword,
            "sort_by": sort_by,
            "count": len(formatted),
            "notes": formatted,
        }

        # 保存结果
        save_result(output, f"search_{keyword}.json")

        return output

    except CDPError as e:
        return {
            "success": False,
            "error": str(e),
            "hint": "请确保 Chrome 浏览器已启动并开启远程调试端口 9222",
        }
    finally:
        client.disconnect()


def get_note_detail(note_url: str, xsec_token: str = "") -> dict:
    """获取笔记详情。

    Args:
        note_url: 笔记 URL 或 note_id
        xsec_token: 安全 token（可选）
    """
    print(f"[xhs_cdp] 获取笔记详情: {note_url}")

    client = XHSCDPClient()
    try:
        # 解析 note_id
        note_id = extract_note_id(note_url)

        # 构建详情 URL
        if xsec_token:
            detail_url = make_feed_detail_url(note_id, xsec_token)
        else:
            detail_url = f"https://www.xiaohongshu.com/discovery/item/{note_id}?source=webshare&xhsshare=pc_web"

        # 连接并导航
        client.connect("xiaohongshu.com")
        client._navigate(detail_url)
        client._wait_for_load()
        client._wait_for_initial_state()
        client._wait_for_detail_state()

        # 提取详情数据
        raw = client._evaluate(f"""
            (() => {{
                const feedId = "{note_id}";
                const state = window.__INITIAL_STATE__;
                if (!state || !state.note || !state.note.noteDetailMap) {{
                    return "";
                }}

                const detailMap = state.note.noteDetailMap;
                if (detailMap[feedId]) {{
                    return JSON.stringify(detailMap[feedId]);
                }}

                const keys = Object.keys(detailMap || {{}});
                if (keys.length === 1 && detailMap[keys[0]]) {{
                    return JSON.stringify(detailMap[keys[0]]);
                }}
                return "";
            }})()
        """)

        if not raw or not isinstance(raw, str):
            return {
                "success": False,
                "error": "未获取到笔记详情",
                "hint": "可能未登录或笔记不存在",
            }

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"解析详情数据失败: {e}",
            }

        # 格式化详情
        detail = format_detail_result(data)
        detail["url"] = detail_url
        detail["success"] = True

        # 保存结果
        save_result(detail, f"detail_{note_id}.json")

        return detail

    except CDPError as e:
        return {
            "success": False,
            "error": str(e),
            "hint": "请确保 Chrome 浏览器已启动并开启远程调试端口 9222",
        }
    finally:
        client.disconnect()


def search_and_detail(keyword: str, limit: int = 5, delay: float = 2.0, sort_by: str = "general") -> dict:
    """搜索并批量获取笔记详情。

    Args:
        keyword: 搜索关键词
        limit: 搜索数量
        delay: 每次请求间隔（秒）
        sort_by: 排序方式
    """
    print(f"[xhs_cdp] 搜索并获取详情: {keyword}")

    # 先搜索
    search_result = search_notes(keyword, limit, sort_by)

    if not search_result.get("success", False):
        return search_result

    notes = search_result.get("notes", [])
    detailed_notes = []

    # 逐个获取详情
    for i, note in enumerate(notes):
        url = note.get("url", "")
        xsec_token = note.get("xsec_token", "")

        if url:
            print(f"[xhs_cdp] 获取第 {i+1}/{len(notes)} 条详情...")
            detail = get_note_detail(url, xsec_token)

            # 合并搜索结果和详情
            if detail.get("success", False):
                combined = {**note, **detail}
                combined["images"] = detail.get("images", [note.get("cover", "")])
                detailed_notes.append(combined)
            else:
                # 获取详情失败，只保留搜索结果
                combined = {**note, "detail_error": detail.get("error", "未知错误")}
                detailed_notes.append(combined)

            # 间隔等待
            if i < len(notes) - 1:
                time.sleep(delay)
        else:
            detailed_notes.append(note)

    output = {
        "success": True,
        "keyword": keyword,
        "sort_by": sort_by,
        "count": len(detailed_notes),
        "notes": detailed_notes,
    }

    # 保存完整结果
    save_result(output, f"search_detail_{keyword}.json")

    return output


def save_result(data: dict, filename: str) -> None:
    """保存结果到文件。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = OUTPUT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[xhs_cdp] 结果已保存: {filepath}")


def main():
    parser = argparse.ArgumentParser(
        prog="xhs-search-cdp",
        description="小红书搜索脚本（CDP 版本）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # search 命令
    sub = subparsers.add_parser("search", help="搜索小红书笔记")
    sub.add_argument("keyword", help="搜索关键词")
    sub.add_argument("--limit", "-n", type=int, default=10, help="结果数量")
    sub.add_argument("--sort", "-s", default="general", choices=["general", "popular", "latest"], help="排序方式")
    sub.set_defaults(func=lambda a: print(json.dumps(search_notes(a.keyword, a.limit, a.sort), ensure_ascii=False, indent=2)))

    # detail 命令
    sub = subparsers.add_parser("detail", help="获取笔记详情")
    sub.add_argument("note_url", help="笔记 URL 或 ID")
    sub.add_argument("--xsec-token", "-x", default="", help="xsec_token（可选）")
    sub.set_defaults(func=lambda a: print(json.dumps(get_note_detail(a.note_url, a.xsec_token), ensure_ascii=False, indent=2)))

    # search-detail 命令
    sub = subparsers.add_parser("search-detail", help="搜索并获取详情")
    sub.add_argument("keyword", help="搜索关键词")
    sub.add_argument("--limit", "-n", type=int, default=5, help="结果数量")
    sub.add_argument("--sort", "-s", default="general", choices=["general", "popular", "latest"], help="排序方式")
    sub.add_argument("--delay", "-d", type=float, default=2.0, help="请求间隔（秒）")
    sub.set_defaults(func=lambda a: print(json.dumps(search_and_detail(a.keyword, a.limit, a.delay, a.sort), ensure_ascii=False, indent=2)))

    # check-login 命令
    sub = subparsers.add_parser("check-login", help="检查浏览器登录状态")
    sub.set_defaults(func=lambda a: print(json.dumps(check_login(XHSCDPClient()), ensure_ascii=False, indent=2)))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()