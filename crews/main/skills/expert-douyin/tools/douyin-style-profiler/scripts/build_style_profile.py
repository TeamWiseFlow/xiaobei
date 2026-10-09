#!/usr/bin/env python3
"""douyin-style-profiler：按作品类型（video / note）生成定性 DNA 资产。

三层产物（与 docs/expert-pack-dna-architecture.md 4.6 一致）：
    单篇作品 -> DNA report
    同一 DNA 目录下全部 report + 权重/focus + 用户输入转译 -> DNA 文档
    DNA 文档 -> DNA template

维度框架见本工具 references/ 下的 FRAMEWORK 文档（视频 / 图文各一份）。
脚本只做 scaffold 与统计证据底座：不评分、不判定风格合格，定性结论由 Agent 回读原文补齐。
"""
import argparse, json, math, re, shutil
from datetime import datetime, timezone
from pathlib import Path


SENTENCE_SPLIT = re.compile(r"[。！？!?]+")
PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
TOKEN_RE = re.compile(r"[一-鿿A-Za-z0-9_]+")
SECOND_PERSON_RE = re.compile(r"你们?|you", re.IGNORECASE)
FIRST_PERSON_RE = re.compile(r"我们?|I|we", re.IGNORECASE)
QUESTION_RE = re.compile(r"[？?]")
EXCLAMATION_RE = re.compile(r"[！!]")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
SOURCE_BLOCK_RE = re.compile(r"<!-- source-transcript\n(?P<path>.*?)\n-->", re.DOTALL)
REPORT_BLOCK_RE = re.compile(r"<!-- dna-reports\n(?P<paths>.*?)\n-->", re.DOTALL)
# 图文正文内联话题标签：#话题（样本文件约定正文为纯文本，行首 # 只出现在标题行）
TAG_RE = re.compile(r"(?m)(?:^|(?<=\s))#[^\s#]\S*")
EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "☀-⛿"
    "✀-➿"
    "⬀-⯿"
    "️"
    "]"
)

# ── CONFIG-BEGIN ──
PLATFORM = "douyin"

PLATFORM_LABEL = "抖音"

PLATFORM_DESC = "抖音短视频与图文作品"

KINDS = ("video", "note")

DEFAULT_KIND = "video"

KIND_LABELS = {"video": "视频作品", "note": "图文作品"}

KIND_SUFFIX_HINT = "抖音默认 dna-0 为视频，图文样本请另建 dna-id（如 dna-0-note）"

FRAMEWORK_DOCS = {"video": "video-dna-framework.md", "note": "note-dna-framework.md"}

# DNA 维度 v2（按作品类型分框架）。调整维度必须升版本，并同步 references/ 下的框架文档与工具 SKILL.md 的 Focus ID 表。
DIMENSION_GROUPS = {
    "video": {
        "选题与包装": [("topic-angle", "选题与观看理由"), ("title-cover", "标题与封面")],
        "内容创意": [("content-idea", "内容创意")],
        "形态与规格": [("video-form", "视频内容形态与制作指向"), ("production-spec", "制作规格与视听倾向")],
        "业务植入与转化": [("biz-implant", "业务植入套路"), ("interaction-cta", "互动引导与 CTA 套路")],
        "口播文案子模块（可选，仅口播类启用）": [("narration-script", "口播文案子DNA")],
        "账号运营子模块（对标账号样本才有）": [("account-bio", "账号简介写法"), ("content-mix-cadence", "内容形式比例与发布习惯")],
    },
    "note": {
        "选题与包装": [("topic-angle", "选题与观看理由"), ("title-cover", "标题与封面图组")],
        "内容创意": [("content-idea", "内容创意")],
        "正文与视觉": [("body-voice", "正文表达与语气"), ("imageset-visual", "图组视觉风格")],
        "业务植入与转化": [("biz-implant", "业务植入套路"), ("interaction-cta", "互动引导与 CTA 套路")],
        "账号运营子模块（对标账号样本才有）": [("account-bio", "账号简介写法"), ("content-mix-cadence", "内容形式比例与发布习惯")],
    },
}

STATISTICS_METRICS = {
    "video": [
        "avg_sentence_tokens",
        "question_density_per_100_sentences",
        "second_person_density_per_100_sentences",
        "exclamation_density_per_1000_characters",
        "speech_chars_per_minute",
    ],
    "note": [
        "title_chars",
        "line_count",
        "avg_sentence_tokens",
        "question_density_per_100_sentences",
        "second_person_density_per_100_sentences",
        "emoji_density_per_100_characters",
        "tag_count",
    ],
}

REPORT_DIMENSION_PROMPTS = {
    "topic-angle": "- 单篇观测：选题类型、选题入口（现象 / 问题 / 冲突 / 数据 / 热点 / 挑战 / 个人经历）、目标人群为什么要看完（理解 / 判断 / 行动 / 避坑 / 身份认同 / 情绪共鸣）。\n- 边界：只记本篇，不判断跨篇稳定性；不评价选题好坏。",
    "title-cover": "- 单篇观测：标题类型（痛点 / 数字 / 反差 / 悬念 / 身份点名 / 搜索长尾）、标题与描述原文、话题标签策略。\n- 视觉证据：封面或首帧必须由视觉模型读取图片，至少提取画面主体与场景、构图与画幅、色彩体系、光线与质感、风格与媒介、文字视觉与图文关系、品牌识别元素、避免项，并反推为可执行的 AIGC 提示词要素；无图片写「未提供」，不得凭正文或标题想象补齐。",
    "content-idea": "- 单篇观测：一句话创意内核、创意类型、展开逻辑（悬念 / 反转 / 递进 / 对比 / 清单 / 实测）、记忆点。\n- 可复用信号：这个创意套路换成别的主题还能怎么用。\n- 边界：只记创意层，不记创作细节（逐句台词、镜头表、脚本结构、转场与编码参数）。",
    "video-form": "- 单篇观测：视频内容形态（口播 / 实拍拼接 / 影视解说+反转植入 / 纯 AIGC 动画 / 创意转场动效 / 录屏演示 / 图文卡片视频 / 混合）与判定依据（画面证据、口播占比、素材来源）。\n- 制作指向：必须落到真实存在的资源名——Content Producer `expert-video` 的某个 workflow（Reversal Ad / Deck Talk / Collage B-roll；不属这三类就写「不指定类型 workflow」，由 CP 按通用制作流程据创意自定手法），或 main 的素材加工技能（`video-edit` / `talking-head-cut` / `ui-demo`）；不得发明不存在的名字。",
    "production-spec": "- 单篇观测：横屏或竖屏、时长带、画面风格（色调、质感、字幕样式倾向、信息密度）、配音音色与声音形态（原声口播 / TTS / 旁白 / 纯画面字幕）、BGM 与音效倾向、封面规格。\n- 边界：只记规格与倾向，不规定镜头参数、逐镜设计、转场与编码细节——那些归 Content Producer。",
    "narration-script": "- 子模块（仅口播类作品启用）：起（从什么起步）、承（靠什么推进）、转（转折触发）、合（收束方式；CTA 的目标、位置与句式记在 `interaction-cta`），以及人称与语气、句长与语速、签名式表达。\n- 边界：非口播类或证据不足时写「未启用 / 未观测」；不得把单篇句式直接上升为规则。",
    "body-voice": "- 单篇观测：开头钩子（原文摘录）、正文组织方式（清单体 / 教程步骤 / 故事线 / 对比 / 观点输出）、分行与段落节奏、口语化程度与人称、emoji 与标点用法、签名式表达。\n- 证据边界：脚本统计只给句长 / 行数 / emoji / 标签等线索；口头禅与签名表达必须回读原文确认。",
    "imageset-visual": "- 单篇观测：图片数量与顺序、构图类型（产品展示 / 场景 / 文字卡片 / 对比图 / 过程图）、图文信息分工、色调与质感、版式一致性、文字视觉。\n- 视觉证据：必须由视觉模型读取本地图片并反推 AIGC 复现要素；无图片写「未提供」，不得凭正文想象补齐。",
    "biz-implant": "- 单篇观测：是否有业务植入（纯内容 / 软植入 / 硬广直给）、植入位置与时机、植入载体（剧情道具 / 口播一句话 / 字幕卡片 / 场景背景 / 案例与数据 / 清单第 N 项 / 教程步骤内嵌 / 产品截图 / 购物车或留资组件 / 主页与私信引导）、植入方式原型（反转植入 / 痛点→方案 / 场景带入 / 实测对比 / 身份认同 / 口碑故事 / 教程内嵌 / 硬广直给）、内容与业务的衔接句（原文摘录）、植入密度与占比、品牌词与产品名出现方式与频次。\n- 证据要求：位置 + 载体 + 原文摘录三样齐全；本篇无植入时写「无植入（纯内容）」，不得留空。\n- 边界：只记植入套路，不写逐句广告文案；形态层面的「影视解说 + 反转植入」由 `video-form` 记形态与制作指向。",
    "interaction-cta": "- 单篇观测：行动目标（关注 / 评论 / 收藏 / 转发 / 私信 / 主页点击 / 进店 / 咨询 / 搜索品牌词 / 购物车 / 直播预约）与本篇主目标、CTA 出现位置与时机（口播收尾句 / 字幕卡 / 片尾贴片 / 描述区 / 正文结尾 / 图组末图 / 评论区）、CTA 句式与原文摘录（命令式 / 提问式 / 利益式 / 身份式 / 悬念式）、一篇放几个行动、诱因设计（利益点 / 情绪 / 身份认同 / 稀缺）、与业务转化目标的对应。\n- 合规边界：不隐藏站外联系方式、不绕平台检测、不以利益换互动，记为必须避免项。",
    "account-bio": "- 子模块（仅对标账号样本可得）：账号昵称、简介写法、主页与置顶表达、对外承诺。\n- 边界：用户提供的单篇样本无法观测时写「未观测」，不得推导。",
    "content-mix-cadence": "- 子模块（仅对标账号批量样本可得）：图文 / 视频等内容形式比例、发布时间段与频率、内容形式混合节奏（如三篇图文对一篇视频）、栏目化节奏。\n- 边界：必须由账号发布列表的批量样本推导；单篇样本只记本篇发布时间。",
}

REPORT_OBSERVATION_PROMPTS = {
    "video": "- 作品类型：视频（本框架只用于视频作品；图文样本走 note-dna-framework）。\n- 样本来源：待 Agent 补齐（对标账号批量作品 / 用户提供的单篇或多篇 / 用户想法转译）。\n- 账号与简介：待 Agent 补齐；非账号样本写未观测。\n- 发布时间与时间段：待 Agent 补齐；单篇只记本篇时间，不推导账号节奏。\n- 数据线索：待 Agent 补齐（播放 / 点赞 / 评论 / 分享 / 收藏）；只作证据，不直接判风格好坏。\n- 横竖屏与时长：待 Agent 补齐。\n- 素材来源与授权：待 Agent 补齐（实拍 / 影视或开源片源 / AIGC / 录屏 / 混合）。\n- 转录与关键帧来源：待 Agent 补齐（如 main 的 viral-chaser 产物路径）；缺失写未提供，不得编造。",
    "note": "- 作品类型：图文（本框架只用于图文作品；视频样本走 video-dna-framework）。\n- 样本来源：待 Agent 补齐（对标账号批量作品 / 用户提供的单篇或多篇 / 用户想法转译）。\n- 账号与简介：待 Agent 补齐；非账号样本写未观测。\n- 发布时间与时间段：待 Agent 补齐；单篇只记本篇时间，不推导账号节奏。\n- 数据线索：待 Agent 补齐（阅读 / 点赞 / 收藏 / 评论 / 分享）；只作证据，不直接判风格好坏。\n- 图片数量与来源：待 Agent 补齐（封面 + 配图张数、实拍 / 截图 / AIGC）。\n- 关键词与标签：待 Agent 补齐（标题、正文与标签区原样记录）。",
}

TEMPLATE_STAGES = {
    "video": ("选题", "标题与封面", "内容创意", "业务植入与 CTA", "视频形态与制作指向", "制作规格", "口播文案"),
    "note": ("选题", "标题与封面", "内容创意与结构", "正文表达", "图组", "业务植入与 CTA"),
}

TEMPLATE_STAGE_FIELDS = {
    "选题": ("选题角度推荐", "选题需考虑的受众关联角度", "内容支柱与系列关系", "避免"),
    "标题与封面": ("标题类型", "参考标题", "封面或首帧风格", "封面 AIGC 提示词要素", "话题标签策略"),
    "内容创意": ("创意原型", "展开逻辑", "记忆点与反转设计", "触发条件", "避免"),
    "视频形态与制作指向": ("视频内容形态", "制作指向", "委托边界", "未指定形态时"),
    "制作规格": ("横屏或竖屏", "时长带", "画面风格", "配音音色与声音形态", "BGM 与音效", "字幕"),
    "口播文案": ("是否启用", "起", "承", "转", "合", "人称与语气", "句长与语速", "签名式表达", "必须做", "避免"),
    "业务植入与 CTA": ("植入位置与时机", "植入载体与方式原型", "内容与业务的衔接句", "植入密度与占比", "CTA 主目标", "CTA 位置与句式", "诱因与合规红线", "避免"),
    "内容创意与结构": ("创意原型", "正文组织方式", "信息密度", "记忆点", "避免"),
    "正文表达": ("开头钩子", "推进方式", "段落与分行节奏", "人称与语气", "emoji 与标点", "签名式表达", "必须做", "避免"),
    "图组": ("图片数量与顺序", "构图类型", "色调与质感", "版式一致性", "文字视觉", "AIGC 提示词要素"),
}

TEMPLATE_INTROS = {
    "video": "本模板是 main agent 出具**视频制作 Brief（brief.md）**与（口播类）**口播文案**的输入模板，必须由 DNA 文档推导，不得引入 DNA 文档未确认的规则。\n\n- 下列各段直接对应 Brief 的正文字段；Brief 的其余字段（素材清单与授权、验收标准、闸门批准人）由平台 Content Production Workflow 规定。\n- Brief **不含 DNA 信息**：Content Producer 看不到 main 的 DNA，只按 Brief 制作。\n- 模板不规定创作细节：逐句台词、镜头表、转场与编码参数归 Content Producer。\n- 账号运营子模块（简介写法、内容形式比例、发布习惯）写在 DNA 文档，不进本模板。",
    "note": "本模板是 main agent 直接生产**图文作品**的写作模板，必须由 DNA 文档推导，不得引入 DNA 文档未确认的规则。\n\n- 开头两段（选题、标题与封面）跨平台通用。\n- 固定的是语义部分，不是物理段落数量：任一部分可对应一个或多个自然段，也可略过。\n- 每条规则必须能从 DNA 文档的聚合结论推导，避免「专业」「亲切」这类空泛形容词。\n- 账号运营子模块写在 DNA 文档，不进本模板。",
}

TEMPLATE_CHECKLISTS = {
    "video": "- 是否只用一个 DNA，且作品类型与该 DNA 的 `kind` 一致。\n- 选题、标题 / 描述、封面是否来自 DNA 文档。\n- 内容创意是否落到可复用的创意原型，而不是照抄样本主题。\n- 视频形态是否明确指向 Content Producer `expert-video` 的某个 workflow，或 main 的某个素材加工技能。\n- Brief 是否只含制作所需信息（不含 DNA 内容），素材是否给了绝对路径与授权说明。\n- 口播类（真人出镜 / 数字人 / 真人录音）是否附口播终稿（`voiceover.md` 绝对路径）或真人录音路径——无论口播子模块是否启用；剪辑配解说的旁白归 CP 写，Brief 口播字段写「不适用」。\n- 制作规格（横竖屏、时长带、画面风格、配音音色）是否尊重样本覆盖度；样本不足时是否标注未观测。\n- 业务植入是否落到位置 + 载体 + 衔接句（而不是只写「自然植入」），CTA 是否只有一个主行动、句式可执行且未越合规红线。\n- 用户输入是否已转译为具体执行规则。",
    "note": "- 是否只用一个 DNA，且作品类型与该 DNA 的 `kind` 一致。\n- 选题、标题与封面图组是否来自 DNA 文档。\n- 正文表达的每条规则是否可从 DNA 文档推导，未使用空泛形容词。\n- 图组数量、构图与视觉风格是否与 DNA 一致；视觉结论是否有图片证据。\n- 业务植入是否落到位置 + 载体 + 衔接句（而不是只写「软性推荐」），CTA 是否每篇只放一个主行动、句式可执行且未越合规红线。\n- 用户输入是否已转译为具体执行规则。",
}

DNA_SUBMODULE_NOTE = "- **口播文案子模块**（`narration-script`）：仅口播类视频启用，用于指导 main agent 写同类型视频的口播文案；它不是独立 DNA，未启用时写「未启用」。\n- **账号运营子模块**（`account-bio`、`content-mix-cadence`）：只在样本来自用户提供的对标账号（可从账号发布列表批量提取）时填写；结论只写进本 DNA 文档，不进 template；样本不足写「未观测」。"
# ── CONFIG-END ──

STATISTICS_METRICS_ALL = [
    "title_chars",
    "line_count",
    "paragraphs",
    "avg_paragraph_tokens",
    "avg_sentence_tokens",
    "question_density_per_100_sentences",
    "second_person_density_per_100_sentences",
    "first_person_density_per_100_sentences",
    "exclamation_density_per_1000_characters",
    "speech_chars_per_minute",
    "emoji_density_per_100_characters",
    "tag_count",
]

METRIC_LABELS = {
    "title_chars": "标题字数",
    "line_count": "正文行数",
    "paragraphs": "段落数",
    "avg_paragraph_tokens": "平均每段长度（token）",
    "avg_sentence_tokens": "平均句长（token）",
    "question_density_per_100_sentences": "问句密度 / 百句",
    "second_person_density_per_100_sentences": "第二人称密度 / 百句",
    "first_person_density_per_100_sentences": "第一人称密度 / 百句",
    "exclamation_density_per_1000_characters": "感叹号密度 / 千字",
    "speech_chars_per_minute": "口播密度（字/分钟）",
    "emoji_density_per_100_characters": "emoji 密度 / 百字",
    "tag_count": "话题标签数",
}


def dimensions_for(kind: str) -> list[dict]:
    """把某个作品类型的分组配置摊平成带序号的维度列表。"""
    dimensions = []
    number = 1
    for group, items in DIMENSION_GROUPS[kind].items():
        for dimension_id, name in items:
            dimensions.append({"id": dimension_id, "number": number, "name": name, "group": group})
            number += 1
    return dimensions


def statistics_metrics(kind: str) -> list[str]:
    wanted = STATISTICS_METRICS[kind]
    return [metric for metric in STATISTICS_METRICS_ALL if metric in wanted]


def split_sentences(text: str) -> list[str]:
    return [item.strip() for item in SENTENCE_SPLIT.split(text) if item.strip()]


def split_paragraphs(text: str) -> list[str]:
    return [item.strip() for item in PARAGRAPH_SPLIT.split(text) if item.strip()]


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def rounded(value: float) -> float:
    return round(value, 4)


def safe_ratio(numerator: int, denominator: float, multiplier: float = 1) -> float:
    return rounded((numerator / denominator) * multiplier) if denominator else 0.0


def average(values: list[float]) -> float:
    return rounded(sum(values) / len(values)) if values else 0.0


def split_title_body(text: str) -> tuple[str, str]:
    """样本文件约定：首个一级标题行为作品标题，其余为正文（图文正文可含内联 #话题）。"""
    title = ""
    body_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not title and stripped.startswith("# ") and len(stripped) > 2:
            title = stripped[2:].strip()
            continue
        body_lines.append(line)
    return title, "\n".join(body_lines).strip()


def title_candidates(path: Path, text: str) -> list[str]:
    candidates = [path.stem]
    title, _ = split_title_body(text)
    if title:
        candidates.append(title)
    return candidates


def document_metrics(path: Path, text: str, duration: float = 0.0) -> dict:
    """统计证据底座：视频与图文共用一套超集，展示哪些指标由 STATISTICS_METRICS[kind] 决定。"""
    title, body = split_title_body(text)
    sentences = split_sentences(text)
    sentence_lengths = [len(tokenize(sentence)) for sentence in sentences]
    sentence_count = len(sentences)
    character_count = len(text)
    body_lines = [line for line in body.splitlines() if line.strip()]
    paragraphs = split_paragraphs(body)
    paragraph_lengths = [len(tokenize(paragraph)) for paragraph in paragraphs]
    emoji_count = len(EMOJI_RE.findall(body))
    speech_chars_per_minute = rounded(character_count / duration * 60) if duration > 0 else 0.0

    return {
        "source_transcript": str(path.resolve()),
        "title_candidates": title_candidates(path, text),
        "characters": character_count,
        "sentences": sentence_count,
        "duration": duration,
        "title_chars": len(title),
        "line_count": len(body_lines),
        "paragraphs": len(paragraphs),
        "avg_paragraph_tokens": average([float(value) for value in paragraph_lengths]),
        "avg_sentence_tokens": average([float(value) for value in sentence_lengths]),
        "question_density_per_100_sentences": safe_ratio(len(QUESTION_RE.findall(text)), sentence_count, 100),
        "second_person_density_per_100_sentences": safe_ratio(len(SECOND_PERSON_RE.findall(text)), sentence_count, 100),
        "first_person_density_per_100_sentences": safe_ratio(len(FIRST_PERSON_RE.findall(text)), sentence_count, 100),
        "exclamation_density_per_1000_characters": safe_ratio(len(EXCLAMATION_RE.findall(text)), character_count, 1000),
        "speech_chars_per_minute": speech_chars_per_minute,
        "emoji_count": emoji_count,
        "emoji_density_per_100_characters": safe_ratio(emoji_count, character_count, 100),
        "tag_count": len(TAG_RE.findall(body)),
    }


def collect_input_paths(inputs: list[str], suffixes: set[str]) -> list[Path]:
    paths: list[Path] = []
    for input_value in inputs:
        input_path = Path(input_value).expanduser()
        if not input_path.exists():
            raise SystemExit(f"Input does not exist: {input_path}")
        if input_path.is_dir():
            paths.extend(
                path
                for path in input_path.rglob("*")
                if path.is_file() and path.suffix.lower() in suffixes
            )
        elif input_path.is_file() and input_path.suffix.lower() in suffixes:
            paths.append(input_path)
        else:
            raise SystemExit(f"Input must be a {', '.join(sorted(suffixes))} file or directory: {input_path}")
    unique = {path.resolve(): path for path in paths}
    return sorted(unique.values(), key=lambda path: str(path))


def validate_cover_image(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_file():
        raise SystemExit(f"Cover image does not exist: {path}")
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise SystemExit("--cover-image must be a local .jpg/.jpeg/.png/.webp/.gif file")
    return path


def persist_cover_image(cover_image: Path, report_output_dir: Path, sample_id: str) -> Path:
    cover_dir = report_output_dir.parent / "covers"
    cover_dir.mkdir(parents=True, exist_ok=True)
    destination = cover_dir / f"{sample_id}{cover_image.suffix.lower()}"
    shutil.copyfile(cover_image, destination)
    return destination


def yaml_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def generated_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def metric_label(metric_name: str) -> str:
    return METRIC_LABELS.get(metric_name, metric_name)


def weighted_median(pairs: list[tuple[float, float]]) -> float:
    ordered = sorted(pairs, key=lambda pair: pair[0])
    total_weight = sum(weight for _, weight in ordered)
    if total_weight == 0:
        return 0.0
    midpoint = total_weight / 2
    cumulative = 0.0
    for value, weight in ordered:
        previous = cumulative
        cumulative += weight
        if cumulative >= midpoint and previous < midpoint:
            return rounded(value)
    return rounded(ordered[-1][0])


def weighted_mad(pairs: list[tuple[float, float]], center: float) -> float:
    deviations = [(abs(value - center), weight) for value, weight in pairs]
    return weighted_median(deviations)


def build_statistics(reports: list[dict], kind: str) -> dict:
    total_weight = rounded(sum(report["weight"] for report in reports))
    numeric_metrics = {}
    for metric_name in statistics_metrics(kind):
        pairs = [
            (float(report["document"][metric_name]), float(report["weight"]))
            for report in reports
        ]
        center = weighted_median(pairs)
        numeric_metrics[metric_name] = {
            "weighted_median": center,
            "weighted_mad": weighted_mad(pairs, center),
            "min": rounded(min(value for value, _ in pairs)) if pairs else 0.0,
            "max": rounded(max(value for value, _ in pairs)) if pairs else 0.0,
        }

    weights = [report["weight"] for report in reports]
    return {
        "report_count": len(reports),
        "total_weight": total_weight,
        "weighting": "user-specified" if any(abs(weight - 1) > 1e-9 for weight in weights) else "uniform",
        "numeric_metrics": numeric_metrics,
    }


def statistics_markdown(statistics: dict, kind: str) -> str:
    lines = [
        "| 指标 | 加权中位数 | 加权 MAD | 最小值 | 最大值 |",
        "|---|---:|---:|---:|---:|",
    ]
    for metric_name, values in statistics["numeric_metrics"].items():
        lines.append(
            f"| {metric_label(metric_name)} | {values['weighted_median']} | {values['weighted_mad']} | {values['min']} | {values['max']} |"
        )
    lines.extend(
        [
            "",
            f"样本覆盖度：`{statistics['report_count']}` 条 {KIND_LABELS[kind]} report。",
            f"权重模式：`{statistics['weighting']}`；总权重：`{statistics['total_weight']}`。",
        ]
    )
    if kind == "video":
        lines.append("口播密度（字/分钟）仅在 report 提供 `duration` 时有意义；未提供时该行只是 0 值占位。")
    lines.extend(
        [
            "「账号运营子模块」维度（简介写法、内容形式比例、发布习惯）不能由单篇样本推导：样本非对标账号批量时写未观测。",
            "统计只用于辅助聚合，不生成评分；定性判断必须回到各篇 DNA report 与原文。",
        ]
    )
    return "\n".join(lines)


def parse_frontmatter(markdown: str) -> dict[str, str]:
    match = re.match(r"^---\n(?P<body>.*?)\n---\n", markdown, re.DOTALL)
    if not match:
        raise SystemExit("DNA markdown is missing frontmatter")
    values = {}
    for line in match.group("body").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def parse_quoted(value: str) -> str:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value.strip('"')


def parse_json_list(value: str) -> list:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def parse_duration(value: str) -> float:
    try:
        duration = float(value)
    except ValueError:
        return 0.0
    return duration if math.isfinite(duration) and duration > 0 else 0.0


def hidden_path(block_match, path_key: str = "paths") -> list[Path]:
    if not block_match:
        return []
    return [Path(line.strip()) for line in block_match.group(path_key).splitlines() if line.strip()]


def load_reports(paths: list[Path]) -> list[dict]:
    reports = []
    for path in paths:
        markdown = path.read_text(encoding="utf-8")
        metadata = parse_frontmatter(markdown)
        source_match = SOURCE_BLOCK_RE.search(markdown)
        source_paths = hidden_path(source_match, "path")
        source_path = source_paths[0] if source_paths else Path(parse_quoted(metadata.get("source-transcript", "")))
        if not source_path.is_file():
            raise SystemExit(f"DNA report source transcript does not exist: {source_path}")
        duration = parse_duration(metadata.get("duration", "0"))
        document = document_metrics(
            source_path,
            source_path.read_text(encoding="utf-8", errors="ignore"),
            duration,
        )
        reports.append(
            {
                "report_path": str(path.resolve()),
                "dna_id": parse_quoted(metadata.get("dna-id", "")),
                "report_id": parse_quoted(metadata.get("report-id", path.name.removesuffix(".report.md"))),
                "kind": parse_quoted(metadata.get("kind", DEFAULT_KIND)),
                "title": parse_quoted(metadata.get("title", document["title_candidates"][-1])),
                "weight": float(metadata.get("weight", "1")),
                "focus": parse_json_list(metadata.get("focus", "[]")),
                "document": document,
            }
        )
    return reports


def enforce_single_kind(reports: list[dict], kind: str | None) -> str:
    """一个 DNA 只承载一种作品类型：返回该 DNA 的 kind，混型直接报错。"""
    kinds = {report["kind"] for report in reports}
    if len(kinds) > 1:
        raise SystemExit(
            "Reports mix work kinds: "
            + ", ".join(sorted(kinds))
            + f"。一个 dna-id 只能承载一种作品类型：{KIND_SUFFIX_HINT}。"
        )
    resolved = kinds.pop() if kinds else (kind or DEFAULT_KIND)
    if kind and resolved != kind:
        raise SystemExit(
            f"--kind {kind} 与 report 内的 kind {resolved} 不一致；一个 dna-id 只能承载一种作品类型。"
        )
    if resolved not in KINDS:
        raise SystemExit(f"Unknown kind: {resolved}（{PLATFORM_LABEL}支持：{', '.join(KINDS)}）")
    return resolved


def report_dimension_markdown(dimension: dict) -> str:
    heading = f"### {dimension['number']}. {dimension['name']}"
    prompt = REPORT_DIMENSION_PROMPTS.get(dimension["id"], "- 单篇观测：待 Agent 补齐。")
    return (
        f"{heading}\n\n"
        f"{prompt}\n\n"
        "**单篇结论：**待 Agent 补齐。\n\n"
        "**原文证据：**待 Agent 补齐（逐字引用、账号/发布信息、画面或声音描述、数据线索；注明来源）。\n\n"
        "**可复用信号：**待 Agent 补齐；证据不足时写未观测，不推导跨篇稳定性。"
    )


def report_markdown(
    dna_id: str,
    report_id: str,
    kind: str,
    weight: float,
    focus: list[str],
    document: dict,
    cover_image: str,
    source_url: str,
) -> str:
    dimensions = dimensions_for(kind)
    dimension_blocks = [report_dimension_markdown(dimension) for dimension in dimensions]
    duration_line = f"duration: {document['duration']}"
    statistics_lines = [
        f"- 转录/正文字符：{document['characters']}",
        f"- 句子数：{document['sentences']}",
    ]
    if kind == "video":
        statistics_lines.append(f"- 视频时长：{document['duration'] or '未提供'}")
    else:
        statistics_lines.extend(
            [
                f"- 标题字数：{document['title_chars']}",
                f"- 正文行数：{document['line_count']}",
                f"- 话题标签数：{document['tag_count']}",
            ]
        )
    statistics_lines.extend(
        [
            f"- 标题候选：{' / '.join(document['title_candidates'])}",
            f"- 来源链接：{source_url or '未提供'}",
            f"- 封面 / 首帧图：{cover_image or '未提供'}",
        ]
    )
    return "\n\n".join(
        [
            "---\n"
            f"dna-id: {yaml_value(dna_id)}\n"
            f"report-id: {yaml_value(report_id)}\n"
            "type: dna-report\n"
            f"kind: {yaml_value(kind)}\n"
            f"title: {yaml_value(document['title_candidates'][-1])}\n"
            f"source-transcript: {yaml_value(document['source_transcript'])}\n"
            f"source-url: {yaml_value(source_url)}\n"
            f"cover-image: {yaml_value(cover_image)}\n"
            f"{duration_line}\n"
            f"weight: {weight}\n"
            f"focus: {yaml_value(focus)}\n"
            "sample_count: 1\n"
            f"generated_at: {yaml_value(generated_at())}\n"
            "---",
            f"# {document['title_candidates'][-1]} 单篇 DNA Report（{KIND_LABELS[kind]}）",
            "本文件只描述这一篇作品。它不是聚合后的 DNA 文档，也不直接作为生产模板。",
            "## 单篇统计",
            "\n".join(statistics_lines),
            "## 样本观测",
            REPORT_OBSERVATION_PROMPTS[kind],
            f"## {len(dimensions)} 维单篇分析",
            "\n\n".join(dimension_blocks),
            "## 单篇边界",
            "- 这里记录本篇作品的可复用信号，不判断跨篇稳定性。\n"
            "- 聚合时由 Agent 根据全部 DNA report、权重和 focus 判断共性、偏好和例外。\n"
            f"- 维度定义与边界见本工具 `references/{FRAMEWORK_DOCS[kind]}`。",
            f"<!-- source-transcript\n{document['source_transcript']}\n-->",
            *([f"<!-- source-cover\n{cover_image}\n-->"] if cover_image else []),
        ]
    ) + "\n"


def user_input_markdown(user_inputs: list[str], kind: str, existing_body: str | None = None) -> str:
    if not user_inputs:
        return existing_body or "暂无待转译输入。"
    dimension_count = len(dimensions_for(kind))
    entries = []
    for index, user_input in enumerate(user_inputs, start=1):
        entries.append(
            f"### 输入 {index}\n"
            f"- raw_input: {yaml_value(user_input)}\n"
            f"- affected_dimensions: 待 Agent 映射到 {dimension_count} 个维度 ID\n"
            "- dna_document_change: 待 Agent 转译为聚合结论 / 报告依据 / 创作规则\n"
            "- template_change: 待 Agent 转译为具体执行规则\n"
            "- status: pending"
        )
    if existing_body and existing_body != "暂无待转译输入。":
        return existing_body + "\n\n" + "\n\n".join(entries)
    return "\n\n".join(entries)


def dna_document_markdown(
    dna_id: str,
    kind: str,
    reports: list[dict],
    statistics: dict,
    user_inputs: list[str] | None = None,
    previous_dna: str | None = None,
) -> str:
    dimensions = dimensions_for(kind)
    old_sections = extract_markdown_sections(previous_dna, "### ")
    dimension_blocks = []
    for dimension in dimensions:
        heading = f"### {dimension['number']}. {dimension['name']}"
        body = old_sections.get(heading)
        if body:
            dimension_blocks.append(f"{heading}\n\n{body}")
        else:
            dimension_blocks.append(
                f"{heading}\n\n**聚合结论：**待 Agent 补齐。\n\n"
                "**报告依据：**待 Agent 列出使用的 DNA report、权重和 focus。\n\n"
                "**创作规则：**待 Agent 补齐。"
            )
    report_paths = "\n".join(report["report_path"] for report in reports)
    existing_user_inputs = (
        extract_named_section(previous_dna, "## 用户输入转译区") if previous_dna else None
    )
    return "\n\n".join(
        [
            "---\n"
            f"dna-id: {yaml_value(dna_id)}\n"
            "type: dna-document\n"
            f"kind: {yaml_value(kind)}\n"
            f"platform: {yaml_value(PLATFORM)}\n"
            f"report_count: {statistics['report_count']}\n"
            f"total_weight: {statistics['total_weight']}\n"
            f"weighting: {statistics['weighting']}\n"
            f"generated_at: {yaml_value(generated_at())}\n"
            "---",
            f"# {dna_id} DNA 文档（{PLATFORM_LABEL} · {KIND_LABELS[kind]}）",
            "本文件聚合该 DNA 目录下的全部 DNA report，形成当前采用的内容生产规则，并且必须能推导出 DNA template。"
            "样本可以来自多个账号，也可以来自用户指定的一个账号的批量作品。",
            "## 报告与权重",
            "\n".join(
                f"- `{report['report_path']}`：weight `{report['weight']}`，focus `{', '.join(report['focus']) or 'all'}`"
                for report in reports
            ),
            statistics_markdown(statistics, kind),
            f"## {len(dimensions)} 维聚合",
            "\n\n".join(dimension_blocks),
            "## 子模块说明",
            DNA_SUBMODULE_NOTE,
            "## 用户输入转译区",
            user_input_markdown(user_inputs or [], kind, existing_user_inputs),
            "## 推导规则",
            "- 聚合结论必须能追溯到 DNA report；区分高覆盖共性、高权重偏好、局部借鉴、孤例与例外。\n"
            "- 用户输入必须先映射到具体维度，再修改聚合结论和创作规则；不得把原话直接当成 DNA 规则。\n"
            "- template 必须由本文件推导，不能引入本文件未确认的规则。\n"
            "- 账号运营子模块（简介写法、内容形式比例、发布习惯）只写进本文件，不进 template。",
            f"<!-- dna-reports\n{report_paths}\n-->",
        ]
    ) + "\n"


def extract_markdown_sections(markdown: str | None, heading_prefix: str) -> dict[str, str]:
    if not markdown:
        return {}
    sections = {}
    current_heading = None
    current_level = 0
    current_lines = []
    for line in markdown.splitlines():
        match = re.match(r"^(?P<level>#{1,6})\s+", line)
        if match:
            level = len(match.group("level"))
            if current_heading is not None and level <= current_level:
                sections[current_heading] = "\n".join(current_lines).strip()
                current_heading = None
                current_level = 0
                current_lines = []
            if line.startswith(heading_prefix):
                current_heading = line
                current_level = level
                current_lines = []
            elif current_heading is not None:
                current_lines.append(line)
            continue
        if current_heading is not None:
            current_lines.append(line)
    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines).strip()
    return sections


def extract_named_section(markdown: str, heading: str) -> str:
    lines = markdown.splitlines()
    found = False
    body = []
    for line in lines:
        if found:
            if line.startswith("## "):
                break
            body.append(line)
        elif line.strip() == heading:
            found = True
    return "\n".join(body).strip()


def parse_template_fields(body: str) -> dict[str, str]:
    fields = {}
    for line in body.splitlines():
        match = re.match(r"^（(?P<label>[^：]+)：(?P<value>.+)）$", line.strip())
        if match:
            fields[match.group("label")] = match.group("value")
    return fields


def template_stage_from_heading(heading: str, kind: str) -> str | None:
    for stage in TEMPLATE_STAGES[kind]:
        if heading.startswith(f"[{stage}部分]"):
            return stage
    return None


def template_segment(stage: str, values: dict[str, str] | None = None) -> str:
    values = values or {}
    lines = [f"[{stage}部分]"]
    for field in TEMPLATE_STAGE_FIELDS[stage]:
        value = values.get(field, "待 Agent 补齐。")
        lines.append(f"（{field}：{value}）")
    return "\n".join(lines)


def stage_values_from_template(old_sections: dict[str, str], kind: str) -> dict[str, dict[str, str]]:
    values = {stage: {} for stage in TEMPLATE_STAGES[kind]}
    for heading in sorted(old_sections, key=lambda item: template_order(item, kind)):
        stage = template_stage_from_heading(heading, kind)
        if not stage:
            continue
        for field, value in parse_template_fields(old_sections[heading]).items():
            values[stage][field] = value
    return values


def template_markdown(
    dna_id: str,
    kind: str,
    source_dna: str,
    previous_template: str | None = None,
) -> str:
    stages = TEMPLATE_STAGES[kind]
    old_sections = extract_template_sections(previous_template, kind)
    stage_values = stage_values_from_template(old_sections, kind)
    segments = [template_segment(stage, stage_values[stage]) for stage in stages]
    section_defaults = [
        ("## 生产模板", "\n\n".join(segments)),
        (
            "## 用户输入转译后的执行规则",
            "- （来自用户输入：待 Agent 补齐来源。）\n"
            f"- （影响维度：待 Agent 映射到 {len(dimensions_for(kind))} 维 ID。）\n"
            "- （执行规则：待 Agent 写成生产时可直接执行的要求。）",
        ),
        ("## 使用检查", TEMPLATE_CHECKLISTS[kind]),
    ]
    rendered_sections = []
    for heading, default_body in section_defaults:
        if heading == "## 生产模板":
            body = default_body
        else:
            previous_body = (
                extract_named_section(previous_template, heading) if previous_template else ""
            )
            body = previous_body or default_body
        rendered_sections.append(f"{heading}\n\n{body}")

    return "\n\n".join(
        [
            "---\n"
            f"dna-id: {yaml_value(dna_id)}\n"
            "type: dna-template\n"
            f"kind: {yaml_value(kind)}\n"
            f"source_dna: {yaml_value(source_dna)}\n"
            f"generated_at: {yaml_value(generated_at())}\n"
            "---",
            f"# {dna_id} DNA Template（{PLATFORM_LABEL} · {KIND_LABELS[kind]}）",
            TEMPLATE_INTROS[kind],
            *rendered_sections,
        ]
    ) + "\n"


def extract_template_sections(markdown: str | None, kind: str) -> dict[str, str]:
    if not markdown:
        return {}
    sections = {}
    current = None
    lines = []
    in_segment = False
    for line in markdown.splitlines():
        if re.match(r"^\[[^\]]+部分\]$", line.strip()):
            if current:
                sections[current] = "\n".join(lines).strip()
            current = line
            lines = []
            in_segment = True
        elif line.startswith("## ") and in_segment:
            if current:
                sections[current] = "\n".join(lines).strip()
            current = None
            lines = []
            in_segment = False
        elif current:
            lines.append(line)
    if current:
        sections[current] = "\n".join(lines).strip()
    return sections


def template_order(heading: str, kind: str) -> tuple[int, str]:
    stage = template_stage_from_heading(heading, kind)
    if stage:
        return (TEMPLATE_STAGES[kind].index(stage) + 1, heading)
    return (10_000, heading)


def validate_id(value: str, label: str) -> None:
    if not ID_RE.fullmatch(value):
        raise SystemExit(f"{label} must be 2-64 chars: lowercase letters, digits, and hyphens")


def validate_kind(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in KINDS:
        raise SystemExit(f"Unknown --kind: {value}（{PLATFORM_LABEL}支持：{', '.join(KINDS)}）")
    return value


def validate_focus(focus: list[str], kind: str) -> None:
    valid = {dimension["id"] for dimension in dimensions_for(kind)}
    unknown = sorted(set(focus) - valid)
    if unknown:
        raise SystemExit(f"Unknown focus for kind '{kind}': {', '.join(unknown)}")


def validate_duration(value: str) -> float:
    try:
        duration = float(value)
    except ValueError:
        raise SystemExit("--duration must be a number of seconds")
    if duration < 0 or not math.isfinite(duration):
        raise SystemExit("--duration must be a non-negative finite number")
    return duration


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def inputs_from_args(args: argparse.Namespace) -> list[str]:
    if not args.input:
        raise SystemExit("Use --input FILE/DIR at least once")
    return args.input


def report_command(args: argparse.Namespace) -> None:
    validate_id(args.dna_id, "--dna-id")
    validate_id(args.sample_id, "--sample-id")
    kind = validate_kind(args.kind) or DEFAULT_KIND
    validate_focus(args.focus, kind)
    weight = float(args.weight)
    if weight <= 0 or not math.isfinite(weight):
        raise SystemExit("--weight must be a positive finite number")
    duration = validate_duration(args.duration) if args.duration else 0.0
    if kind != "video" and duration:
        print(f"[warn] --duration 只对视频作品有意义，{KIND_LABELS[kind]} report 忽略该值。")
        duration = 0.0
    paths = collect_input_paths(inputs_from_args(args), {".md", ".txt"})
    if len(paths) != 1:
        raise SystemExit("report command accepts exactly one transcript; use build to aggregate reports")
    document = document_metrics(paths[0], paths[0].read_text(encoding="utf-8", errors="ignore"), duration)
    output_dir = Path(args.output_dir or f"{PLATFORM}/dna/{args.dna_id}/reports")
    cover_image = ""
    if args.cover_image:
        source_cover = validate_cover_image(args.cover_image)
        cover_image = str(persist_cover_image(source_cover, output_dir, args.sample_id).resolve())
    output = output_dir / f"{args.sample_id}.report.md"
    write_text(
        output,
        report_markdown(
            args.dna_id, args.sample_id, kind, weight, args.focus, document, cover_image,
            args.source_url or "",
        ),
    )
    print(f"Wrote single-work DNA report ({KIND_LABELS[kind]}): {output}")
    print(f"[next] Agent 补齐「样本观测」与 {len(dimensions_for(kind))} 维单篇结论后，跑 build 聚合。")


def build_command(args: argparse.Namespace) -> None:
    validate_id(args.dna_id, "--dna-id")
    input_values = args.input or [f"{PLATFORM}/dna/{args.dna_id}/reports"]
    paths = collect_input_paths(input_values, {".md"})
    report_paths = [path for path in paths if path.name.endswith(".report.md")]
    if not report_paths:
        raise SystemExit("build accepts DNA report .md files generated by the report command")
    reports = load_reports(report_paths)
    foreign_reports = [report["report_id"] for report in reports if report["dna_id"] != args.dna_id]
    if foreign_reports:
        raise SystemExit(f"Reports belong to another dna-id: {', '.join(foreign_reports)}")
    kind = enforce_single_kind(reports, validate_kind(args.kind))
    for report in reports:
        validate_focus(report["focus"], kind)
    statistics = build_statistics(reports, kind)
    output_dir = Path(args.output_dir or f"{PLATFORM}/dna/{args.dna_id}")
    dna_path = output_dir / f"{args.dna_id}.dna.md"
    template_path = output_dir / f"{args.dna_id}.template.md"
    write_text(dna_path, dna_document_markdown(args.dna_id, kind, reports, statistics, args.user_input))
    write_text(template_path, template_markdown(args.dna_id, kind, dna_path.name, None))
    print(f"Wrote DNA document and template ({KIND_LABELS[kind]}): {output_dir}")


def update_command(args: argparse.Namespace) -> None:
    dna_path = Path(args.dna)
    template_path = Path(args.template)
    if not dna_path.is_file() or not template_path.is_file():
        raise SystemExit("Both --dna and --template must exist")
    previous_dna = dna_path.read_text(encoding="utf-8")
    previous_template = template_path.read_text(encoding="utf-8")
    metadata = parse_frontmatter(previous_dna)
    dna_id = parse_quoted(metadata.get("dna-id", dna_path.name.removesuffix(".dna.md")))
    validate_id(dna_id, "--dna-id")
    declared_kind = parse_quoted(metadata.get("kind", "")) or None
    kind = validate_kind(args.kind) or validate_kind(declared_kind)

    input_values = args.input or []
    new_paths = collect_input_paths(input_values, {".md"}) if input_values else []
    new_reports = [path for path in new_paths if path.name.endswith(".report.md")]
    if input_values and not new_reports:
        raise SystemExit("update accepts DNA report .md files generated by the report command")
    historical = hidden_path(REPORT_BLOCK_RE.search(previous_dna))
    all_paths = {path.resolve(): path for path in [*historical, *new_reports]}
    reports = load_reports(sorted(all_paths.values(), key=lambda path: str(path)))
    foreign_reports = [report["report_id"] for report in reports if report["dna_id"] != dna_id]
    if foreign_reports:
        raise SystemExit(f"Reports belong to another dna-id: {', '.join(foreign_reports)}")
    kind = enforce_single_kind(reports, kind)
    for report in reports:
        validate_focus(report["focus"], kind)
    validate_focus(args.focus, kind)
    statistics = build_statistics(reports, kind)
    user_inputs = list(args.user_input or [])
    write_text(dna_path, dna_document_markdown(dna_id, kind, reports, statistics, user_inputs, previous_dna))
    write_text(template_path, template_markdown(dna_id, kind, dna_path.name, previous_template))
    print(f"Updated DNA document and template ({KIND_LABELS[kind]}): {dna_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Build qualitative {PLATFORM_LABEL} DNA assets per work kind")
    subparsers = parser.add_subparsers(dest="command", required=True)

    kind_help = f"作品类型：{' / '.join(KINDS)}（默认 {DEFAULT_KIND}）"
    report = subparsers.add_parser("report", help="Create one single-work DNA report")
    report.add_argument("--input", action="append", required=True)
    report.add_argument("--kind", help=kind_help)
    report.add_argument("--cover-image", help="Local cover / first-frame image used by visual-model analysis")
    report.add_argument("--source-url", help="Original work URL kept as report evidence")
    report.add_argument("--duration", help="Video duration in seconds (video kind only), used for speech-density statistics")
    report.add_argument("--dna-id", required=True)
    report.add_argument("--sample-id", required=True)
    report.add_argument("--weight", default="1")
    report.add_argument("--focus", action="append", default=[])
    report.add_argument("--output-dir")
    report.set_defaults(handler=report_command)

    build = subparsers.add_parser("build", help="Aggregate DNA reports into DNA document and template")
    build.add_argument("--input", action="append")
    build.add_argument("--kind", help=kind_help)
    build.add_argument("--dna-id", required=True)
    build.add_argument("--user-input", action="append", default=[])
    build.add_argument("--output-dir")
    build.set_defaults(handler=build_command)

    update = subparsers.add_parser("update", help="Merge reports and translate user input")
    update.add_argument("--input", action="append")
    update.add_argument("--kind", help=kind_help)
    update.add_argument("--dna", required=True)
    update.add_argument("--template", required=True)
    update.add_argument("--focus", action="append", default=[])
    update.add_argument("--user-input", action="append", default=[])
    update.set_defaults(handler=update_command)
    return parser


def run(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    run()
