"""小红书搜索脚本 - 封装 xhs-cli 提供搜索和详情获取接口。

功能：
1. search: 根据关键词搜索小红书帖子
2. detail: 获取帖子详细信息（标题、内容、图片、点赞、收藏等）
3. search_detail: 搜索并批量获取详情

前置条件：需要先登录 (xhs login)

输出: JSON 格式
"""

import argparse
import json
import subprocess
import sys
import time
import re
from typing import Optional
from pathlib import Path

# 输出文件目录
OUTPUT_DIR = Path("/tmp/xhs_search")


def run_xhs_command(args: list, timeout: int = 30, use_json: bool = True) -> dict:
    """执行 xhs-cli 命令并返回解析后的 JSON 结果。
    
    Args:
        args: xhs 命令参数列表
        timeout: 命令超时时间（秒）
        use_json: 是否添加 --json 参数
    """
    # xhs-cli 使用 --json 参数输出 JSON 格式
    if use_json and "--json" not in args and "--yaml" not in args:
        args.append("--json")
    
    cmd = ["xhs"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        
        # 检查错误
        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or "命令执行失败"
            # 解析 YAML 格式的错误信息
            if "not_authenticated" in error_msg or "No 'a1' cookie" in error_msg:
                return {
                    "success": False, 
                    "error": "未登录",
                    "hint": "请先执行 xhs login 登录小红书账号"
                }
            return {"success": False, "error": error_msg}
        
        # 尝试解析 JSON 输出
        output = result.stdout.strip()
        if output:
            try:
                data = json.loads(output)
                # 检查 xhs-cli 返回的 ok 字段
                if isinstance(data, dict):
                    if data.get("ok") == False:
                        return {"success": False, "error": data.get("error", {}).get("message", "未知错误")}
                    elif data.get("ok") == True:
                        # 返回实际数据
                        return {"success": True, "data": data.get("data", data)}
                return {"success": True, "data": data}
            except json.JSONDecodeError:
                # 尝试解析 YAML 格式输出
                if "ok:" in output:
                    return parse_yaml_output(output)
                # 返回原始文本
                return {"success": True, "raw_output": output}
        return {"success": True, "raw_output": ""}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "命令超时"}
    except FileNotFoundError:
        return {"success": False, "error": "xhs 命令未安装，请先安装: pipx install xiaohongshu-cli"}


def parse_yaml_output(output: str) -> dict:
    """解析 xhs-cli 的 YAML 格式输出。"""
    # 简单解析 YAML 格式
    lines = output.strip().split("\n")
    result = {}
    for line in lines:
        if "ok:" in line:
            result["ok"] = line.split("ok:")[1].strip() == "true"
        elif "error:" in line and "message:" in line:
            # 提取错误消息
            match = re.search(r"message:\s*(.+)", output)
            if match:
                result["error"] = match.group(1).strip()
    if result.get("ok") == True:
        return {"success": True, "raw_output": output}
    else:
        return {"success": False, "error": result.get("error", output)}


def search_notes(keyword: str, limit: int = 10, sort_by: str = "general") -> dict:
    """搜索小红书笔记。
    
    Args:
        keyword: 搜索关键词
        limit: 返回结果数量（通过分页实现）
        sort_by: 排序方式 (general/popular/latest)
        
    Returns:
        包含搜索结果的字典
    """
    print(f"搜索关键词: {keyword}, 排序: {sort_by}")
    
    # xhs search 命令格式: xhs search KEYWORD --sort general --json
    # 注意: xhs-cli 没有 -n 参数，通过 --page 分页
    args = ["search", keyword, "--sort", sort_by]
    
    result = run_xhs_command(args)
    
    if not result.get("success", False):
        return result
    
    # 解析搜索结果
    notes = []
    data = result.get("data", result.get("raw_output", {}))
    
    # 处理不同格式的返回数据
    if isinstance(data, list):
        notes = data
    elif isinstance(data, dict):
        # xhs-cli 返回格式可能是 {items: [...]} 或 {notes: [...]} 或直接列表
        if "items" in data:
            notes = data["items"]
        elif "notes" in data:
            notes = data["notes"]
        elif "data" in data:
            notes = data["data"]
        elif "list" in data:
            notes = data["list"]
        else:
            # 尝试直接解析为列表
            for key in data:
                if isinstance(data[key], list) and len(data[key]) > 0:
                    if isinstance(data[key][0], dict) and ("id" in data[key][0] or "noteId" in data[key][0]):
                        notes = data[key]
                        break
    
    # 限制数量
    notes = notes[:limit] if notes else []
    
    # 构建返回结果
    output = {
        "success": True,
        "keyword": keyword,
        "sort_by": sort_by,
        "count": len(notes),
        "notes": format_search_results(notes),
    }
    
    # 保存结果
    save_result(output, f"search_{keyword}.json")
    
    return output


def format_search_results(notes: list) -> list:
    """格式化搜索结果，统一字段名。"""
    formatted = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        item = {
            "id": note.get("id", note.get("noteId", "")),
            "url": note.get("url", ""),
            "title": note.get("title", note.get("displayTitle", "")),
            "xsec_token": note.get("xsecToken", note.get("xsec_token", "")),
            "type": note.get("type", ""),
            "likes": note.get("likedCount", note.get("likes", "0")),
            "collects": note.get("collectedCount", note.get("collects", "0")),
            "comments": note.get("commentCount", note.get("comments", "0")),
            "author": {
                "id": note.get("userId", note.get("user", {}).get("userId", "")),
                "name": note.get("nickname", note.get("user", {}).get("nickname", "")),
            },
            "cover": note.get("cover", note.get("coverUrl", "")),
        }
        # 构建完整 URL（如果没有）
        if not item["url"] and item["id"] and item["xsec_token"]:
            item["url"] = f"https://www.xiaohongshu.com/explore/{item['id']}?xsec_token={item['xsec_token']}"
        formatted.append(item)
    return formatted


def get_note_detail(note_url: str, xsec_token: str = "") -> dict:
    """获取笔记详情。
    
    Args:
        note_url: 笔记 URL 或 note_id
        xsec_token: 安全 token（可选，如果有缓存可省略）
        
    Returns:
        包含笔记详情的字典
    """
    print(f"获取笔记详情: {note_url}")
    
    # xhs read 命令格式: xhs read ID_OR_URL --json [--xsec-token TOKEN]
    args = ["read", note_url]
    if xsec_token:
        args.extend(["--xsec-token", xsec_token])
    
    result = run_xhs_command(args, timeout=60)
    
    if not result.get("success", False):
        return result
    
    data = result.get("data", result.get("raw_output", {}))
    
    # 解析详情数据
    detail = {}
    if isinstance(data, dict):
        detail = format_detail_result(data)
    elif isinstance(data, str):
        detail = {"raw": data, "success": True}
    else:
        detail = {"data": data, "success": True}
    
    # 添加 URL
    detail["url"] = note_url
    detail["success"] = True
    
    # 保存结果
    note_id = extract_note_id(note_url) or detail.get("id", "unknown")
    save_result(detail, f"detail_{note_id}.json")
    
    return detail


def format_detail_result(data: dict) -> dict:
    """格式化笔记详情结果。"""
    # 提取图片列表
    images = []
    if "imageList" in data:
        for img in data.get("imageList", []):
            images.append(img.get("urlDefault", img.get("url", "")))
    elif "images" in data:
        images = data.get("images", [])
    
    # 提取作者信息
    author = {}
    if "user" in data:
        author = {
            "id": data["user"].get("userId", ""),
            "name": data["user"].get("nickname", ""),
            "avatar": data["user"].get("avatar", ""),
        }
    
    # 提取互动信息
    interact = data.get("interactInfo", {})
    
    return {
        "id": data.get("noteId", data.get("id", "")),
        "title": data.get("title", data.get("displayTitle", "")),
        "content": data.get("desc", data.get("content", "")),
        "type": data.get("type", ""),
        "images": images,
        "likes": interact.get("likedCount", data.get("likes", "0")),
        "collects": interact.get("collectedCount", data.get("collects", "0")),
        "comments": interact.get("commentCount", data.get("comments", "0")),
        "shares": interact.get("sharedCount", data.get("shares", "0")),
        "author": author,
        "ip_location": data.get("ipLocation", ""),
        "time": data.get("time", 0),
    }


def extract_note_id(url: str) -> str:
    """从 URL 中提取 note_id。"""
    # 匹配 /explore/ 后面的 ID
    match = re.search(r"/explore/([a-f0-9]+)", url)
    if match:
        return match.group(1)
    # 匹配 noteId 参数
    match = re.search(r"noteId=([a-f0-9]+)", url)
    if match:
        return match.group(1)
    # 直接是 note_id 格式
    match = re.search(r"^[a-f0-9]{24}$", url)
    if match:
        return url
    return "unknown"


def search_and_detail(keyword: str, limit: int = 5, delay: float = 2.0, sort_by: str = "general") -> dict:
    """搜索并批量获取笔记详情。
    
    Args:
        keyword: 搜索关键词
        limit: 搜索数量
        delay: 每次请求间隔（秒）
        sort_by: 排序方式
        
    Returns:
        包含搜索结果和详情的字典
    """
    print(f"搜索并获取详情: {keyword}")
    
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
        if not url:
            # 尝试构建 URL
            note_id = note.get("id", "")
            if note_id and xsec_token:
                url = f"https://www.xiaohongshu.com/explore/{note_id}"
        
        if url:
            print(f"获取第 {i+1}/{len(notes)} 条详情...")
            detail = get_note_detail(url, xsec_token)
            
            # 合并搜索结果和详情
            combined = {**note, **detail}
            combined["images"] = detail.get("images", [note.get("cover", "")])
            detailed_notes.append(combined)
            
            # 间隔等待，避免频率限制
            if i < len(notes) - 1:
                time.sleep(delay)
        else:
            # 没有 URL，只保留搜索结果
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
    print(f"结果已保存: {filepath}")


def check_login() -> dict:
    """检查登录状态。"""
    # xhs status 命令检查登录状态
    result = run_xhs_command(["status"])
    
    if result.get("success", False):
        data = result.get("data", {})
        return {
            "logged_in": True, 
            "message": "已登录",
            "user_info": data
        }
    else:
        return {
            "logged_in": False,
            "message": "未登录，请先执行 xhs login",
            "hint": "xhs login 会自动从浏览器提取 Cookie，或使用 xhs login --qrcode 扫码登录",
            "error": result.get("error", "")
        }


def main():
    parser = argparse.ArgumentParser(
        prog="xhs-search",
        description="小红书搜索脚本",
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
    sub = subparsers.add_parser("check-login", help="检查登录状态")
    sub.set_defaults(func=lambda a: print(json.dumps(check_login(), ensure_ascii=False, indent=2)))
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()