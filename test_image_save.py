"""测试脚本 - 小红书图片搜索与保存。

功能：
1. 搜索小红书帖子
2. 获取高清图片链接（通过 img[src*="sns-webpic"] 选择器提取）
3. 通过 Canvas API 从已加载图片获取 base64 数据

方式：找到已加载的 img 元素 → canvas 绘制 → toDataURL → base64 → Python 解码保存（禁止截图方式）。

测试关键词：大海
"""

import json
import os
import sys
import time
import base64
import argparse
from pathlib import Path

import requests

# 添加 xhs-search skill 的 scripts 目录
sys.path.insert(0, "/root/.openclaw/skills/xhs-search/scripts")

# 导入 CDP 搜索脚本的功能
from xhs_search_cdp import (
    XHSCDPClient,
    CDPError,
    make_search_url,
    convert_to_hd_url,
)

# 输出目录
OUTPUT_DIR = Path("/tmp/xhs_images_test")


def download_image_via_canvas(client: XHSCDPClient, url: str, save_path: str, timeout: float = 30.0) -> dict:
    """通过 Canvas API 从已加载图片获取 base64 数据。
    
    方式：在页面中找到匹配 URL 的 img 元素 → canvas 绘制 → toDataURL → base64。
    图片已经通过浏览器加载，绕过 CDN 防盗链。
    
    不使用截图方式。
    
    Args:
        client: CDP 客户端（保持连接）
        url: 图片 URL
        save_path: 本地保存路径
        timeout: 下载超时时间
        
    Returns:
        {"success": bool, "path": str, "error": str}
    """
    print(f"[download_canvas] 下载图片: {url[:80]}...")
    
    # 确保 URL 使用 HTTPS
    if url.startswith("http://"):
        url = "https://" + url[7:]
    
    try:
        # 转义 URL 中的特殊字符（用于 JavaScript 字符串）
        escaped_url = url.replace("'", "\\'").replace('"', '\\"')
        
        # 构建 JavaScript 表达式：从已加载的 img 元素获取图片数据
        print(f"[download_canvas] 执行 JavaScript canvas 获取...")
        
        # 使用字符串拼接避免 URL 中的 % 字符与 Python 格式化冲突
        js_expression = """
            (async () => {
                const targetUrl = '""" + url + """';
                
                try {
                    // 找到匹配 URL 的 img 元素（可能 URL 有后缀变化）
                    const allImgs = document.querySelectorAll('img');
                    let targetImg = null;
                    
                    // 精确匹配
                    for (const img of allImgs) {
                        const src = img.getAttribute('src') || '';
                        if (src === targetUrl || src.startsWith(targetUrl.split('!')[0])) {
                            targetImg = img;
                            break;
                        }
                    }
                    
                    // 如果没找到，尝试模糊匹配（去掉后缀部分）
                    if (!targetImg) {
                        const urlBase = targetUrl.split('!')[0];
                        for (const img of allImgs) {
                            const src = img.getAttribute('src') || '';
                            if (src.startsWith(urlBase)) {
                                targetImg = img;
                                break;
                            }
                        }
                    }
                    
                    if (!targetImg) {
                        return {
                            success: false,
                            error: '未找到匹配的 img 元素'
                        };
                    }
                    
                    // 等待图片完全加载
                    if (!targetImg.complete) {
                        await new Promise((resolve, reject) => {
                            targetImg.onload = resolve;
                            targetImg.onerror = () => reject('img load error');
                            setTimeout(() => reject('img load timeout'), 5000);
                        });
                    }
                    
                    // 创建 canvas 绘制图片
                    const canvas = document.createElement('canvas');
                    canvas.width = targetImg.naturalWidth;
                    canvas.height = targetImg.naturalHeight;
                    
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(targetImg, 0, 0);
                    
                    // 获取 base64 数据（JPEG 格式，质量 95%）
                    const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
                    const base64Data = dataUrl.split(',')[1];
                    
                    return {
                        success: true,
                        base64: base64Data,
                        width: canvas.width,
                        height: canvas.height,
                        originalSrc: targetImg.getAttribute('src')
                    };
                } catch (err) {
                    return {
                        success: false,
                        error: String(err)
                    };
                }
            })()
        """
        
        result = client._evaluate(js_expression, timeout=timeout)
        
        # 检查返回结果
        if not result:
            return {
                "success": False,
                "error": "JavaScript 返回空结果",
                "url": url,
            }
        
        # 检查是否失败
        if result.get("success") == False:
            return {
                "success": False,
                "error": f"canvas 获取失败: {result.get('error', '未知错误')}",
                "url": url,
            }
        
        # 获取 base64 数据
        base64_data = result.get("base64")
        if not base64_data:
            return {
                "success": False,
                "error": "未获取到 base64 数据",
                "url": url,
                "debug": result,
            }
        
        # 解码 base64
        image_data = base64.b64decode(base64_data)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        # 写入文件
        with open(save_path, "wb") as f:
            f.write(image_data)
        
        file_size = os.path.getsize(save_path)
        width = result.get("width", 0)
        height = result.get("height", 0)
        
        print(f"[download_canvas] 保存成功: {save_path} ({file_size} bytes)")
        print(f"[download_canvas] 图片尺寸: {width}x{height}")
        
        return {
            "success": True,
            "path": save_path,
            "size": file_size,
            "url": url,
            "method": "canvas_toDataURL",  # 标记下载方式
            "width": width,
            "height": height,
            "original_src": result.get("originalSrc"),
        }
        
    except Exception as e:
        print(f"[download_canvas] 下载失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "url": url,
        }


def test_image_save(keyword: str = "大海", limit: int = 5) -> dict:
    """测试图片搜索与保存功能。
    
    单次 CDP 连接完成搜索和下载。
    
    Args:
        keyword: 搜索关键词
        limit: 搜索数量
        
    Returns:
        测试结果，包含第一张图片的本地路径
    """
    print(f"\n{'='*50}")
    print(f"[test] 开始测试 - 关键词: {keyword}")
    print(f"{'='*50}\n")
    
    client = XHSCDPClient()
    
    try:
        # 连接浏览器
        client.connect("xiaohongshu.com")
        
        # 导航到搜索页
        search_url = make_search_url(keyword)
        client._navigate(search_url)
        client._wait_for_load()
        client._wait_for_initial_state()
        client._wait_for_search_state()
        
        # 从 DOM 直接提取高清图片链接（使用 img[src*="sns-webpic"] 选择器）
        dom_images = client._evaluate("""
            (() => {
                let results = [];
                
                // 策略1: 直接匹配 sns-webpic 格式的高清图片
                const hdImgs = document.querySelectorAll('img[src*="sns-webpic"]');
                
                // 收集每个帖子卡片的第一张图片
                const noteCards = document.querySelectorAll('.note-item, [class*="note-card"], [class*="feeds-item"]');
                
                if (noteCards.length > 0) {
                    noteCards.forEach((card, idx) => {
                        const img = card.querySelector('img[src*="sns-webpic"], img[src*="xhscdn"]');
                        if (img) {
                            const url = img.getAttribute('src') || img.getAttribute('data-src') || '';
                            if (url && (url.includes('sns-webpic') || url.includes('xhscdn.com'))) {
                                results.push({
                                    index: idx,
                                    url: url,
                                    type: 'card_image'
                                });
                            }
                        }
                    });
                }
                
                // 策略2: 如果卡片方式没找到，直接收集所有高清图片
                if (results.length === 0) {
                    hdImgs.forEach((img, idx) => {
                        const url = img.getAttribute('src') || img.getAttribute('data-src') || '';
                        if (url && url.includes('sns-webpic')) {
                            const parent = img.closest('[class*="avatar"], [class*="icon"], [class*="user"]');
                            if (!parent) {
                                results.push({
                                    index: idx,
                                    url: url,
                                    type: 'direct_image'
                                });
                            }
                        }
                    });
                }
                
                // 策略3: 从 __INITIAL_STATE__ 提取
                if (results.length === 0) {
                    const state = window.__INITIAL_STATE__;
                    if (state && state.search && state.search.feeds) {
                        const feeds = state.search.feeds;
                        const data = feeds.value !== undefined ? feeds.value : feeds._value;
                        if (data && Array.isArray(data)) {
                            data.forEach((feed, idx) => {
                                const noteCard = feed.noteCard || {};
                                const cover = noteCard.cover || {};
                                const url = cover.urlDefault || cover.url || '';
                                if (url) {
                                    results.push({
                                        index: idx,
                                        url: url,
                                        type: 'state_data',
                                        noteId: feed.id,
                                        title: noteCard.displayTitle || ''
                                    });
                                }
                            });
                        }
                    }
                }
                
                return results;
            })()
        """)
        
        if not dom_images or not isinstance(dom_images, list):
            return {
                "success": False,
                "error": "未获取到图片",
                "hint": "可能未登录或搜索无结果",
            }
        
        print(f"[test] 获取到 {len(dom_images)} 张图片链接")
        
        # 转换 URL 为高清格式
        for item in dom_images:
            if item.get("url"):
                item["url"] = convert_to_hd_url(item["url"])
        
        images = dom_images[:limit]
        
        if not images:
            return {
                "success": False,
                "error": "未找到图片",
            }
        
        # 创建输出目录
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        # 下载第一张图片
        first_image = images[0]
        url = first_image.get("url")
        
        if not url:
            return {
                "success": False,
                "error": "第一张图片 URL 无效",
            }
        
        # 生成文件名
        timestamp = int(time.time())
        filename = f"xhs_{keyword}_{timestamp}_0.jpg"
        save_path = str(OUTPUT_DIR / filename)
        
        print(f"\n[test] 下载第一张图片...")
        print(f"[test] URL: {url[:100]}...")
        print(f"[test] 保存路径: {save_path}")
        
        # 通过 Canvas API 下载图片（从已加载的 img 元素）
        download_result = download_image_via_canvas(client, url, save_path)
        
        if download_result.get("success"):
            print(f"\n{'='*50}")
            print(f"[test] 测试成功!")
            print(f"[test] 第一张图片已保存到: {save_path}")
            print(f"[test] 下载方式: {download_result.get('method', 'unknown')}")
            print(f"[test] 图片尺寸: {download_result.get('width')}x{download_result.get('height')}")
            print(f"[test] 文件大小: {download_result.get('size')} bytes")
            print(f"{'='*50}\n")
            
            return {
                "success": True,
                "keyword": keyword,
                "first_image_path": save_path,
                "first_image_url": url,
                "first_image_size": download_result.get("size"),
                "download_method": download_result.get("method"),
                "image_dimensions": f"{download_result.get('width')}x{download_result.get('height')}",
                "original_src": download_result.get("original_src"),
                "total_images": len(images),
                "all_images": images,
            }
        else:
            print(f"[test] 下载失败: {download_result.get('error')}")
            return {
                "success": False,
                "error": download_result.get("error"),
                "url": url,
                "debug": download_result.get("debug"),
            }
            
    except CDPError as e:
        return {
            "success": False,
            "error": str(e),
            "hint": "请确保 Chrome 浏览器已启动并开启远程调试端口 9222",
        }
    finally:
        client.disconnect()


def main():
    parser = argparse.ArgumentParser(
        prog="test-image-save",
        description="测试小红书图片搜索与保存",
    )
    parser.add_argument("keyword", nargs="?", default="大海", help="搜索关键词")
    parser.add_argument("--limit", "-n", type=int, default=5, help="搜索数量")
    
    args = parser.parse_args()
    
    # 运行测试
    result = test_image_save(args.keyword, args.limit)
    
    # 输出结果
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()