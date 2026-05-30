"""Keyword and brand vocabularies for repost detection.

Two directions, parallel structure:

  Direction A — ``bilibili_from_youtube``
    A Bilibili video that is a 搬运 (re-upload) of an original YouTube
    video. Signals point at "this Chinese-platform video originated
    abroad": translation/subtitle keywords, AI-dub keywords, foreign
    brand/channel names, English-heavy titles.

  Direction B — ``youtube_from_bilibili``
    A YouTube video that is a re-upload of an original Bilibili video.
    Signals point at "this video originated on Bilibili": references
    to 哔哩哔哩 / B站 / UP主, BV ids, bilibili.com links, and the
    distinctive 三连 / 一键三连 creator-culture vocabulary that leaks
    into re-uploaded descriptions.

Keeping the two vocabularies side by side (rather than one shared
bag) is deliberate: the signals are NOT symmetric. "翻译" is evidence
of direction A; "UP主" is evidence of direction B. Mixing them would
make both detectors noisier.
"""

from __future__ import annotations

# ── Direction A: bilibili video reposted FROM youtube ──────────────

# Title/description keywords that indicate a translation / re-upload
# of foreign content.
A_REPOST_KEYWORDS: tuple[str, ...] = (
    "翻译",
    "中字",
    "字幕",
    "自译",
    "译制",
    "熟肉",
    "搬运",
    "英文字幕",
    "中英字幕",
    "双语字幕",
    "英文",
    "外语",
    "外文",
    "英文原版",
    "原版视频",
    "sub",
    "subtitle",
    "translation",
    "translate",
    "CC",
    "English",
    "中英",
    "英文解说",
)

# AI dubbing / machine-translation signals — the newer wave of reposts
# where the original foreign audio is replaced with AI Chinese voice.
# The title is often fully Chinese (low Latin ratio), so the classic
# Latin-ratio / English-term signals miss these.
A_AI_DUB_KEYWORDS: tuple[str, ...] = (
    "AI配音",
    "AI 配音",
    "AI翻译",
    "AI 翻译",
    "AI语音",
    "AI 语音",
    "AI朗读",
    "AI 朗读",
    "AI克隆",
    "AI 克隆",
    "AI声音",
    "AI 声音",
    "AI解说",
    "AI 解说",
    "AI连读",
    "AI 连读",
    "机翻",
    "机器翻译",
    "AI机翻",
    "AI 机翻",
    "AI voice",
    "AI dub",
    "AI dubbing",
    "AI translate",
    "AI voiceover",
    "TTS配音",
    "TTS 配音",
    "TTS翻译",
    "TTS 翻译",
    "自动配音",
    "自动翻译",
    "配音译制",
    "译制配音",
    "中英双语配音",
    "配音翻译",
    "外语中文配音",
    "英文中配",
    "英语中配",
    "智能配音",
    "智能翻译",
    "语音合成",
)

# Description phrases hinting the video is an AI-dubbed / sourced repost.
A_AI_DUB_DESC_SIGNALS: tuple[str, ...] = (
    "原视频",
    "原片",
    "原版",
    "来源",
    "原始视频",
    "original video",
    "source video",
    "original",
    "来自YouTube",
    "来自Youtube",
    "来自油管",
    "YouTube链接",
    "youtube链接",
    "本视频为AI",
    "AI配音视频",
    "AI翻译视频",
    "机器翻译视频",
    "机翻视频",
    "字幕翻译",
    "音频翻译",
    "转载自油管",
    "转载自YouTube",
    "来源油管",
    "视频来源",
    "素材来源",
    "原作者",
    "原视频链接",
    "原地址",
    "原链接",
    "出自YouTube",
    "采集自",
    "自译",
    "翻译自",
    "译自",
)

# Comment keywords that suggest the video is a repost of foreign content.
A_REPOST_COMMENT_KEYWORDS: tuple[str, ...] = (
    "AI配音",
    "AI 配音",
    "机翻",
    "机器翻译",
    "配音",
    "这是搬运",
    "搬运的",
    "搬运视频",
    "原视频",
    "原版",
    "这都能搬",
    "又搬",
    "偷视频",
    "YouTube上",
    "油管上",
    "不是原创",
    "不是原創",
    "AI翻译",
    "AI 翻译",
    "抄的",
    "盗视频",
    "盗用",
)

# Known non-Chinese channels/brands that often get reposted to Bilibili.
A_FOREIGN_BRANDS: tuple[str, ...] = (
    "Gamespot",
    "IGN",
    "Gamesradar",
    "Polygon",
    "Kotaku",
    "GameSpot",
    "Nintendo",
    "PlayStation",
    "Xbox",
    "TED",
    "TEDx",
    "BBC",
    "CNN",
    "NPR",
    "PBS",
    "Netflix",
    "HBO",
    "Disney+",
    "Apple TV",
    "Vox",
    "Verge",
    "Wired",
    "TechCrunch",
    "Ars Technica",
    "NYT",
    "New York Times",
    "Guardian",
    "Reuters",
    "AP",
    "National Geographic",
    "Discovery",
    "Science",
    "Nature",
    "Vsauce",
    "Veritasium",
    "SmarterEveryDay",
    "Kurzgesagt",
    "3Blue1Brown",
    "Numberphile",
    "Computerphile",
    "Tom Scott",
    "LTT",
    "Linus Tech Tips",
    "Gamers Nexus",
    "MKBHD",
    "Marques Brownlee",
    "Dave2D",
    "Dave Lee",
    "iJustine",
    "UrAvgConsumer",
    "Austin Evans",
    "Fstoppers",
    "DPReview",
    "PetaPixel",
    "The Wall Street Journal",
    "Bloomberg",
    "Forbes",
    "CNET",
    "Engadget",
    "Gizmodo",
    "GizChina",
    "Digital Trends",
    "Tom's Guide",
    "TechSpot",
    "AnandTech",
    "SemiAnalysis",
    "Chip War",
    "Asianometry",
    "High Yield",
    "Two Minute Papers",
    "Yannic Kilcher",
)


# ── Direction B: youtube video reposted FROM bilibili ──────────────

# Title/description keywords that the video originated on Bilibili.
# These are bilibili-culture markers that leak into re-uploaded
# descriptions and titles. NOTE: several of these (UP主, 三连) also
# appear in genuinely-Chinese-but-not-bilibili content, so the
# detector requires them to STACK or co-occur with a stronger signal
# rather than firing on a single weak hit.
B_BILI_ORIGIN_KEYWORDS: tuple[str, ...] = (
    "哔哩哔哩",
    "bilibili",
    "Bilibili",
    "B站",
    "b站",
    "比站",
    "UP主",
    "up主",
    "阿婆主",
    "一键三连",
    "三连",
    "投币",
    "点赞投币收藏",
    "关注UP",
    "关注up",
    "粉丝群",
)

# Description phrases that explicitly attribute the source to Bilibili.
# These are STRONG signals (an uploader stating where they took it).
B_BILI_ORIGIN_DESC_SIGNALS: tuple[str, ...] = (
    "搬运自B站",
    "搬运自哔哩哔哩",
    "转自B站",
    "转自哔哩哔哩",
    "转载自B站",
    "转载自哔哩哔哩",
    "来自B站",
    "来自哔哩哔哩",
    "原视频B站",
    "原视频在B站",
    "原视频来自哔哩哔哩",
    "已获授权转载",
    "已获UP主授权",
    "原作者授权",
    "source: bilibili",
    "from bilibili",
    "reposted from bilibili",
    "原址",
    "原链接",
)

# Comment keywords suggesting the YouTube video is a repost of B站 content.
B_BILI_ORIGIN_COMMENT_KEYWORDS: tuple[str, ...] = (
    "这是B站的",
    "搬运B站",
    "B站原视频",
    "B站搬的",
    "哔哩哔哩搬的",
    "搬运哔哩哔哩",
    "原视频在B站",
    "原作者在B站",
    "这是搬运",
    "搬运的",
    "偷的B站",
    "盗B站",
    "from bilibili",
    "stolen from bilibili",
    "reupload",
)
