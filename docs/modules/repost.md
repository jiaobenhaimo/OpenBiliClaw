# 搬运检测模块（repost）

## 概述

`repost` 模块负责**双向搬运检测与链接**：识别一条视频是否为另一平台原视频的搬运（re-upload），并在命中时把展示用的链接 / 封面 / 文案换成原视频。两个方向完全独立——独立缓存、独立检测逻辑、独立检索后端、独立 API 端点：

- **方向 A（`bilibili_from_youtube`）**：B 站视频搬运自 YouTube 原视频。推荐流里的 B 站候选若被判定为搬运，则在卡片上指向 YouTube 原版。这是默认且自动触发的方向。
- **方向 B（`youtube_from_bilibili`）**：YouTube 视频搬运自 B 站原视频。识别后指向 B 站原版。当前通过 `/api/yt-replacer/reverse-lookup` 端点与手动 `mark-as-repost` 触发。

本模块取代旧的单文件 `src/openbiliclaw/yt_replacer.py`（916 行、0 测试，PR #53 因体量与缺测试被拒），重构为职责清晰、可单测的包：

| 文件 | 职责 |
|------|------|
| `vocab.py` | 两个方向各一套关键词 / 品牌词表（信号**不对称**：「翻译」指向 A，「UP主」指向 B，混在一起会互相加噪） |
| `text.py` | 纯文本工具：标题相似度、CJK / 拉丁字符占比、英文术语抽取、BV 号 / YouTube id / 链接抽取、检索 query 构造 |
| `cache.py` | `RepostCache`：实例化、每方向一个 JSON 文件，区分 `MISS`（从未查过）与缓存的 `None`（查过、无匹配） |
| `detect.py` | `RepostSignal` 值对象 + 两个平行检测器 |
| `search.py` | 按 host 的可达性探测、YouTube（yt-dlp）/ B 站（HTTP）检索、两个 `find_*_original` 打分器 |
| `service.py` | `RepostService` 持有两个独立缓存，按方向串起 检测 → 可达性 → 检索 → 缓存 |
| `__init__.py` | 类式 API + 与旧 `yt_replacer` 同签名的函数式 API（向后兼容六个调用点） |

## 已实现功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 方向 A 自动检测 | ✅ | 推荐流命中搬运 B 站视频时换成 YouTube 原版。检测信号阶梯：描述含 YouTube 链接（决定性）→ 标题英文占比高且 CJK 占比低 → 外媒/频道名 + 少量英文 → 搬运/字幕关键词 + 英文存在 → 完整英文短语 → AI 配音/机翻关键词 → 评论指认 |
| 方向 B 自动检测 | ✅ | 新增真实检测器（取代旧「标题含任意中文字符」）。信号阶梯与 A 平行：描述/标题含 B 站链接或 BV 号（决定性）→「搬运自 B 站 / 已获授权」显式声明 → 中文主导标题 + B 站文化词 → 评论指认。**中文主导是必要非充分条件**——纯中文原创内容不再误判 |
| 独立双缓存 | ✅ | `repost_bili_to_yt.json`（bvid → YouTube 匹配）与 `repost_yt_to_bili.json`（yt id → B 站匹配）两个文件；`clear()` 同时清掉旧 `yt_replacer_cache.json` 残留 |
| 推荐流非阻塞 | ✅ | `/api/recommendations` 仅 inline 套用**已缓存**的替换（纯字典查询，零网络）；未解析的行交给托管后台任务 `repost_warm` 预热（评论并发拉取 async，阻塞式检索走 `asyncio.to_thread` 工作线程），结果落缓存供下次请求 inline 命中 |
| 手动标记搬运 | ✅ | `mark-as-repost` 按 `source_platform` 分流到两个方向，`skip_detection=True` 跳过启发式直接检索原视频；方向 B 未找到原视频时回退、清除误判并回报 `was_false_positive` |
| 检索召回兜底 | ✅ | B 站检索附带尽力获取的 `buvid3` cookie（进程内缓存 1h）以改善召回；标题 `<em>` 高亮标签在打分前剥除 |

## 公开 API

类式入口（推荐新代码使用）：

```python
from openbiliclaw.repost import RepostService

svc = RepostService(data_dir, cache_ttl_hours=24)

# 方向 A：B 站视频 → YouTube 原版
a = svc.link_bilibili_to_youtube(
    bvid, title, author=up_name, description=desc, search=True
)
# search=False 为纯缓存模式：命中返回缓存、未命中返回 None，绝不触发检测/检索

# 方向 B：YouTube 视频 → B 站原版
b = svc.link_youtube_to_bilibili(yt_id, title, description=desc)

# 推荐行覆盖（方向 A）+ 后台批量预热
override = svc.replace_recommendation_row(row, search=False)
stats = svc.warm_bilibili_to_youtube(rows, comments_by_bvid=comments)  # 阻塞，须走线程
svc.clear()
```

向后兼容的函数式 API（旧 `yt_replacer` 同名同签名，内部复用按 `data_dir` 的单例服务）：

```python
from openbiliclaw.repost import (
    is_likely_repost,            # 方向 A 检测（纯函数）
    is_likely_bilibili_origin,   # 方向 B 检测（纯函数）
    replace_if_foreign,          # 方向 A 链接
    replace_if_from_bilibili,    # 方向 B 链接
    replace_recommendation_row,  # 推荐行覆盖（支持 search=False）
    warm_recommendation_reposts, # 后台预热（阻塞，须走线程）
    clear_cache,
)
```

检测器返回 `RepostSignal(detected: bool, confidence: float, reasons: list[str])`，`__bool__` 即 `detected`，`reasons` 便于日志排查命中原因。

## 后端 HTTP 端点

| 端点 | 方法 | 方向 | 说明 |
|------|------|------|------|
| `/api/yt-replacer/lookup` | GET | A | 查 B 站视频是否搬运自 YouTube 并取原版链接（插件 B 站内容脚本调用） |
| `/api/yt-replacer/reverse-lookup` | GET | B | 查 YouTube 视频是否搬运自 B 站并取原版链接（传 `yt_id` / `title` / `description`） |
| `/api/yt-replacer/mark-as-repost` | POST | A + B | 手动标记搬运，按 `source_platform` 分流 |
| `/api/yt-replacer/clear-cache` | POST | — | 清空两个方向的缓存 |

## 配置项

本模块复用 `[sources.youtube]` 下的既有配置，未新增配置键：

| 配置 | 默认值 | 说明 |
|------|------:|------|
| `sources.youtube.replace_bilibili_reposts` | `false` | 是否在推荐流启用方向 A 搬运替换 |
| `sources.youtube.yt_replacer_cache_ttl` | `24` | 缓存 TTL（小时），两个方向共用此值构造各自 `RepostCache` |
| `sources.youtube.use_comments_for_detection` | — | 是否拉取评论以启用「评论指认」信号（方向 A） |
| `sources.youtube.comment_detection_max_rows` | — | 单次预热拉评论的行数上限，控 B 站 API 配额 |

## 设计决策

- **两个方向不共享存储。** `RepostService` 持有两个 `RepostCache` 实例、各自落盘，取代旧实现「一个字典 + `bili:` 前缀键」。这样每个方向的缓存可独立推理、独立清除。
- **方向 B 的「中文主导」是必要非充分条件。** 旧检测器把「标题含任意中文字符」当作 B 站搬运信号，会把 YouTube 上大量原创中文内容全部误判。新检测器要求中文主导**且**伴随真实的 B 站来源信号（链接 / BV 号 / 显式声明 / 文化词）。
- **方向 A 高拉丁占比信号叠加低 CJK 占比门槛。** 「我用 Python 写推荐系统」这类标题约 37% 拉丁字符却显然是中文主导（只嵌了一个英文名词），旧实现会误判；现要求 CJK 占比 < 0.20 才以「英文占比高」命中，消除该误判类而不削弱对真英文标题的识别。
- **推荐流两段式，慢检索绝不阻塞响应。** serve path 只做纯缓存查询（`search=False`）；真正的 yt-dlp 检索（阻塞、子进程、3–5s）放到托管后台任务里经 `asyncio.to_thread` 在工作线程跑，结果落缓存供下次 inline 命中。首次看到新搬运显示 B 站版，预热后下次翻转为 YouTube 原版。
- **缓存区分 MISS 与 None。** `None` 是有意义的条目——「查过、无匹配」，缓存它以免每次重复昂贵检索；`MISS` 表示「从未查过」。预热据此跳过已解析（无论命中或无匹配）的行，重复调用只做新增工作。
- **缓存条目按 TTL 过期。** 每条 `set()` 打时间戳，`get()` 对超过 `ttl_seconds`（默认 24h）的条目返回 `MISS` 触发重查，避免把指向已删除原视频的旧命中、或「当时没搜到」的旧无匹配永久钉死；`ttl_seconds=0` 表示永不过期。落盘为 `{version, values, stamps}`，旧扁平缓存文件按过期处理、重查一次后即升级为新格式。
- **向后兼容函数式 API。** 保留旧 `yt_replacer` 的六个公开函数名与签名，六个调用点（`app.py` 推荐流 + 三个端点 + mark-as-repost 双向）只需改 import 路径，无需改调用。
