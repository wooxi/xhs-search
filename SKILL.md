---
name: xhs-search
description: |
  小红书搜索技能 - 根据关键词搜索小红书帖子，获取帖子详情信息。
  功能：搜索笔记、获取笔记详情（标题、内容、图片、点赞、收藏等）。
  适用场景：搜索小红书内容、获取帖子信息、分析热门笔记。
metadata:
  openclaw:
    requires:
      bins:
        - python3
      skills:
        - xiaohongshu-skills
    emoji: "\U0001F4D5"
    os:
      - darwin
      - linux
---

# 小红书搜索技能 (xhs-search)

你是"小红书搜索助手"。根据用户关键词搜索小红书笔记，获取详细内容信息。

## 前置条件

### CDP 版本（推荐，服务器环境）

**使用已部署的 Chrome DevTools Protocol 浏览器，无需单独登录。**

前置条件：
- Chrome/Chromium 浏览器已启动并开启远程调试端口（默认 9222）
- 浏览器中已登录小红书账号（通过 OpenClaw browser tool 或手动登录）

检查浏览器状态：
```bash
openclaw browser status
```

如果浏览器未运行，启动它：
```bash
openclaw browser start
```

### CLI 版本（本地环境）

**需要先安装并登录 xhs-cli。**

```bash
# 安装
pipx install xiaohongshu-cli

# 方式 1: 自动从浏览器提取 Cookie（需要本地有已登录的浏览器）
xhs login

# 方式 2: QR 码登录（服务器环境）
xhs login --qrcode

# 检查登录状态
xhs status
```

## 功能说明

1. **搜索笔记**：根据关键词搜索小红书帖子列表
2. **获取详情**：获取帖子完整信息（标题、内容、全部图片链接、点赞量、收藏量）
3. **批量获取**：支持搜索并批量获取详情

## 使用方式

### CDP 版本（推荐）

```bash
# 搜索笔记
python /root/.openclaw/skills/xhs-search/scripts/xhs_search_cdp.py search "关键词" --limit 10

# 获取笔记详情
python /root/.openclaw/skills/xhs-search/scripts/xhs_search_cdp.py detail "NOTE_URL" --xsec-token "TOKEN"

# 搜索并批量获取详情（一步完成）
python /root/.openclaw/skills/xhs-search/scripts/xhs_search_cdp.py search-detail "关键词" --limit 5 --delay 2

# 检查浏览器登录状态
python /root/.openclaw/skills/xhs-search/scripts/xhs_search_cdp.py check-login
```

### CLI 版本（需要先登录）

```bash
# 搜索笔记
python scripts/xhs_search.py search "关键词" --limit 10 --sort popular

# 获取笔记详情
python scripts/xhs_search.py detail "NOTE_URL" --xsec-token "TOKEN"

# 搜索并批量获取详情
python scripts/xhs_search.py search-detail "关键词" --limit 5 --sort popular --delay 2

# 检查登录状态
python scripts/xhs_search.py check-login
```

### 直接使用 xhs-cli

```bash
# 搜索笔记（推荐加 --json 输出）
xhs search "关键词" --sort popular --json

# 查看详情（必须用搜索结果中的 URL 或 ID）
xhs read NOTE_URL --json

# 查看评论
xhs comments NOTE_URL --json

# 热门笔记
xhs hot --json

# 首页推荐
xhs feed --json
```

## 输出格式

返回 JSON 格式数据，包含：

```json
{
  "success": true,
  "keyword": "搜索关键词",
  "sort_by": "general",
  "count": 10,
  "notes": [
    {
      "id": "note_id",
      "url": "完整URL",
      "xsec_token": "安全token",
      "title": "标题",
      "content": "正文内容",
      "type": "normal/video",
      "images": ["图片链接1", "图片链接2"],
      "likes": "点赞量",
      "collects": "收藏量",
      "comments": "评论量",
      "author": {
        "id": "用户ID",
        "name": "用户名",
        "avatar": "头像链接"
      },
      "cover": "封面图片链接"
    }
  ]
}
```

## 排序选项

- `general`: 综合排序（默认）
- `popular`: 热门排序
- `latest`: 最新排序

## 版本对比

| 特性 | CDP 版本 | CLI 版本 |
|------|----------|----------|
| 登录方式 | 使用浏览器已有登录状态 | 需单独登录 |
| 适用环境 | 服务器环境（已部署 CDP 浏览器） | 本地环境 |
| 依赖 | Chrome + websockets | xhs-cli |
| 稳定性 | 高（使用真实浏览器） | 中（可能被风控） |

## 重要注意事项

1. **xsec_token 限制**：小红书强制 xsec_token 机制，正确流程是先 `search` 获取结果，再用结果中的 URL 获取详情。
2. **频率控制**：高频请求会触发验证码，建议每次操作间隔 2-3 秒。
3. **CDP 连接**：确保 Chrome 浏览器的远程调试端口（9222）可访问。

## 结果保存

搜索结果自动保存到 `/tmp/xhs_search/` 目录：
- `search_KEYWORD.json`: 搜索结果
- `detail_NOTE_ID.json`: 笔记详情
- `search_detail_KEYWORD.json`: 批量获取的完整结果

## 失败处理

- **CDP 连接失败**：检查 `openclaw browser status`，确保浏览器已启动
- **未登录**：在浏览器中手动登录小红书，或检查 OpenClaw browser 的登录状态
- **频率限制**：降低请求频率，等待后重试
- **验证码**：需要在浏览器中手动完成验证

## 技术实现

CDP 版本使用以下技术：
- **Chrome DevTools Protocol**：通过 WebSocket 连接到 Chrome 浏览器
- **页面数据提取**：从 `window.__INITIAL_STATE__` 提取数据
- **复用登录状态**：使用浏览器中已有的 Cookie 和登录状态

参考实现：
- `/root/.openclaw/skills/xiaohongshu-skills/scripts/xhs/cdp.py`
- `/root/.openclaw/skills/RedBookSkills/scripts/cdp_publish.py`
- `/root/.openclaw/skills/RedBookSkills/scripts/feed_explorer.py`