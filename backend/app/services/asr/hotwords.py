"""行业知识热词提取器 —— 从行业知识 Markdown 文档中提取品牌名、术语、地名

用途：
1. 注入 FunASR hotwords 参数，提高语音识别准确率
2. 构建 ASR 后处理纠错词典

热词来源：
- docs/行业知识/零食店红黑榜.md（品牌详情、快招黑榜）
- docs/行业知识/零食店品牌区域分布.md（各省品牌分布）
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# 行业知识文档路径（相对于项目根目录）
_KNOWLEDGE_DIR = Path(__file__).resolve().parents[4] / "docs" / "行业知识"

# 手动补充的行业术语（Markdown 里可能没有直接出现的通用术语）
_MANUAL_TERMS = [
    # 行业黑话
    "快招公司", "割韭菜", "区域保护", "回本周期", "加盟费", "保证金",
    "转让费", "选址评估", "门店面积", "门头宽度", "投资预算",
    # 业务术语
    "留资", "私信", "钩子", "话术", "复盘", "避坑",
    "一线品牌", "二线品牌", "头部品牌", "零食折扣店",
    # 资料名称
    "行业调研报告", "品牌避坑名单", "选址评估表", "回本周期计算表",
    # 经营相关
    "零食集合店", "量贩零食", "品牌零食店", "零食批发超市",
    "开店预算", "整店输出", "加盟品牌", "自主经营",
]

# FunASR hotwords 上限（官方建议不超过 200 个词，否则可能影响识别速度）
MAX_HOTWORDS = 200


def _read_knowledge_files() -> str:
    """读取所有行业知识 Markdown 文件的原始文本。"""
    texts = []
    if _KNOWLEDGE_DIR.is_dir():
        for md_file in sorted(_KNOWLEDGE_DIR.glob("*.md")):
            try:
                texts.append(md_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("读取行业知识文件 %s 失败: %s", md_file.name, exc)
    return "\n".join(texts)


def _extract_brand_names(text: str) -> set[str]:
    """从 Markdown 中提取品牌名。

    识别模式：
    1. ### 数字. 品牌名 标题（如 ### 1. 好想来）
    2. 品牌区域分布中的品牌名（如 - **一线**：来优品（安徽合肥）、赵一鸣...）
    3. 黑榜表格中的品牌名（第二列）
    """
    brands: set[str] = set()

    # 1. 从 h3 标题提取头部品牌名：### 1. 好想来 / ### 2. 赵一鸣
    for match in re.finditer(r"###\s+\d+\.\s*(.+)$", text, re.MULTILINE):
        name = match.group(1).strip()
        if 2 <= len(name) <= 16:
            brands.add(name)

    # 2. 从区域分布列表项中提取品牌名
    # 格式：- **一线**：来优品（安徽合肥）、赵一鸣（江西宜春）（另设广州总部）、好想来（江苏泰州兴化市）
    # 取冒号后面的内容，按顿号分割，提取括号前的品牌名
    for line in text.split("\n"):
        stripped = line.strip()
        if not (stripped.startswith("- ") or stripped.startswith("* ")):
            continue
        # 找到冒号后的内容
        if "：" not in stripped and ":" not in stripped:
            continue
        parts = re.split(r"[：:]", stripped, maxsplit=1)
        if len(parts) < 2:
            continue
        after_colon = parts[1]
        # 按顿号分割（也处理逗号分隔的情况）
        segments = re.split(r"[、，,]", after_colon)
        for seg in segments:
            seg = seg.strip()
            # 提取括号前的品牌名（也可能没有括号）
            name_match = re.match(r"([^\s（(]{2,16})", seg)
            if not name_match:
                continue
            name = name_match.group(1).strip()
            # 过滤非品牌名的词
            skip_words = {
                "一线", "二线", "三线", "品牌", "备注", "参考", "提示", "共同",
                "整体", "正常", "卖场", "门头", "以下", "开放区域", "强势区域",
                "未开放", "门店规模", "总部", "代言人", "项目", "内容", "地区",
                "品牌/备注", "疑似快招", "开店预算", "面积要求", "回本周期",
                "投资预算", "区域保护", "零食折扣店",
            }
            if name not in skip_words and 2 <= len(name) <= 16:
                brands.add(name)

    # 3. 从黑榜表格中提取品牌名（表格第二列或列表中的品牌名）
    # 黑榜表格格式：
    # | 广东 | 艾回味、零食大明星、巨惠码头 |
    blacklist_section = re.search(
        r"快招公司.*?割韭菜.*?\n\n((?:\|.+\|.*\n)+)",
        text, re.DOTALL
    )
    if blacklist_section:
        for row in blacklist_section.group(1).strip().split("\n"):
            cells = [c.strip() for c in row.split("|") if c.strip()]
            # 表格有 3 列：空 | 地区 | 黑榜品牌 |
            if len(cells) >= 2:
                brand_cell = cells[-1]  # 最后一列是品牌名
                for seg in re.split(r"[、，,]", brand_cell):
                    name = seg.strip()
                    if 2 <= len(name) <= 16:
                        brands.add(name)

    return brands


def _extract_locations(text: str) -> set[str]:
    """从 Markdown 中提取省份和城市名。

    识别模式：
    - 省份标题（### 安徽省、### 河南省 等）
    - 品牌总部城市（括号中的城市名）
    """
    locations: set[str] = set()

    # 省份/直辖市/自治区名（从 ### 标题中提取）
    for match in re.finditer(r"###\s*(.+?)(?:省|市|自治区|地区)", text):
        loc = match.group(1).strip()
        if loc and len(loc) <= 6:
            locations.add(loc)

    # 城市名（从括号中的总部城市提取，如"来优品（安徽合肥）"）
    for match in re.finditer(r"（([^）)]{2,8})）", text):
        inner = match.group(1).strip()
        # 过滤数字、特殊字符，只保留可能的地名
        if inner and not re.search(r"[0-9万㎡以年月日代～~]", inner) and len(inner) <= 8:
            # 省+市组合（如"安徽合肥"），整体加入
            locations.add(inner)
            # 也把城市单独加入（如"合肥"）
            city_match = re.match(r".*(?:州|阳|城|都|肥|昌|汉|沙|安|宁|口|春|圳|门|莞|山|坊|博|庄|兴|华|封)$", inner)
            if city_match and len(inner) >= 2:
                pass  # 省+市组合，保持完整

    return locations


def _extract_industry_terms(text: str) -> set[str]:
    """从 Markdown 中提取行业术语。

    关注关键词：快招、割韭菜、回本周期、投资预算、区域保护 等
    """
    # 这些术语在 _MANUAL_TERMS 中已经覆盖，
    # 这里从文档中额外提取文档里特有的术语
    additional: set[str] = set()

    # 提取"疑似快招"相关的关键词模式
    term_patterns = [
        r"(快招\S*)",
        r"(割\S*菜)",
        r"(回本\S*)",
        r"(投资预算\S*)",
        r"(区域保护\S*)",
        r"(加盟\S*)",
        r"(选址\S*)",
        r"(转让费\S*)",
    ]
    for pattern in term_patterns:
        for match in re.finditer(pattern, text):
            term = match.group(1)
            if 2 <= len(term) <= 10:
                additional.add(term)

    return additional


def extract_hotwords() -> list[str]:
    """从行业知识文档中提取所有热词。

    返回按优先级排序的热词列表（品牌名 > 术语 > 地名）。
    FunASR hotwords 参数建议不超过 200 个词。

    Returns:
        热词列表，空格分隔的字符串形式供 FunASR 使用
    """
    text = _read_knowledge_files()
    if not text:
        logger.warning("未找到行业知识文档，使用默认热词列表")
        return _MANUAL_TERMS[:MAX_HOTWORDS]

    brands = _extract_brand_names(text)
    locations = _extract_locations(text)
    doc_terms = _extract_industry_terms(text)

    # 合并所有热词，按优先级排列
    all_terms = list(_MANUAL_TERMS)  # 手动术语优先级最高

    # 品牌名排第二（最重要，ASR 最容易识别错）
    for brand in sorted(brands):
        if brand not in all_terms:
            all_terms.append(brand)

    # 地名排第三
    for loc in sorted(locations):
        if loc not in all_terms:
            all_terms.append(loc)

    # 文档中提取的术语
    for term in sorted(doc_terms):
        if term not in all_terms:
            all_terms.append(term)

    logger.info("从行业知识中提取了 %d 个热词（品牌 %d + 地名 %d + 术语 %d）",
                len(all_terms), len(brands), len(locations), len(doc_terms) + len(_MANUAL_TERMS))

    # FunASR hotwords 建议不超过 200 个
    if len(all_terms) > MAX_HOTWORDS:
        logger.info("热词数量超过 %d，截取前 %d 个（优先级：术语 > 品牌 > 地名）", MAX_HOTWORDS, MAX_HOTWORDS)
        all_terms = all_terms[:MAX_HOTWORDS]

    return all_terms


def get_hotwords_string() -> str:
    """获取 FunASR 可用的热词字符串（空格分隔）。"""
    return " ".join(extract_hotwords())


def build_correction_dictionary() -> dict[str, str]:
    """构建 ASR 后处理纠错词典。

    只包含核心品牌名和关键术语（手动维护，确保精确）。
    纠错词典不能有噪声，否则会误改正常文本。

    Returns:
        {品牌名: 品牌名} 的词典
    """
    # ── 核心品牌名和术语（手动维护，确保精确无误）──
    correction_dict: dict[str, str] = {}

    # 头部品牌
    head_brands = [
        "好想来", "赵一鸣", "零食很忙", "零食有鸣",
        "来优品", "老婆大人", "陆小馋", "吖滴吖滴",
    ]
    # 二线靠谱品牌（常见）
    second_tier = [
        "糖巢", "零食舱", "折扣牛", "爱零食", "零食优选",
        "恰货铺子", "戴永红", "良品铺子", "零食顽家", "懒猫食光",
        "来伊份", "好特卖零食", "悠百佳", "怡佳仁零食",
        "蓉一品零食", "零食公社", "恐龙和泰迪零食",
        "零食很能嗨", "零小象", "景盟零食批发超市",
        "喜喜零食", "逗零嘴零食", "兜点零食", "零食侠客",
        "天啦零食", "心动零食", "多乐屯", "汪哥折扣仓",
        "王否否", "大嘴零食", "愚公移山零食", "巡物社",
        "悦记好零食", "零食尤尼", "花花零食",
        "超越优品零食店", "好好鲜森", "好丽华休闲零食", "御果缘零食",
        "钟和风", "略略熊零食", "养馋记", "桔子花开",
        "爱折扣", "拾粹折扣店", "七娄零食",
        "零食疆山", "南国零食", "罗比零食", "零食奶爸",
        "云聚仓省钱超市", "零食管家",
        "零食家族", "零小萌批发超市",
        "七货街零食", "零食漫漫", "囤点零食",
    ]
    # 快招/黑榜品牌
    blacklist = [
        "零百味", "玩妙熊", "贪吃掌柜", "提姆队长", "艾回味",
        "零食大明星", "巨惠码头", "零食爽", "零嘴福", "零食哆哆",
        "好零友", "小食坊", "富力熊", "巡味星球", "馋小忙",
        "零食叮当", "馋铺记", "三只北极熊", "第宜佳折扣超市",
        "零食媳妇", "每桔折扣店", "玖倍佳", "邻盛客", "吃点零拾",
        "好幸福零食", "一扫光零食", "卡塔利亚", "熊猫沫沫",
        "消闲果儿", "零福记", "皇妃嘴", "零食好萌", "甄惠客",
        "馋嘴女孩", "爱上零食屋", "鲸叹号", "小敏小诺",
        "零食集结号", "零小惠", "购物猩", "惠购猩", "俄满多",
        "俄客士", "零食旅行记", "言小木", "锁味零食", "幸福松鼠",
        "江南佳美", "宝赞特", "小零大食", "小喵很忙零食",
        "零食小铺", "美食好忙", "零食门", "美悠佳", "零拾年代",
        "邻步量贩", "零食大爆炸", "小食熊", "舌尖大赢家",
        "爽舌尖零食", "零食转角", "亿小馋品牌零食", "御冠码头零食",
        "渝蓉良品零食", "湘遇舌尖零食", "馋猫的橱柜零食店",
        "邻食佳折扣", "馋嘴侠", "林拾日记",
    ]
    # 行业关键术语
    key_terms = [
        "快招公司", "割韭菜", "区域保护", "回本周期",
        "投资预算", "零食折扣店", "量贩零食",
    ]

    for brand in head_brands + second_tier + blacklist + key_terms:
        if len(brand) >= 3:  # 纠错只用 3 字以上的词
            correction_dict[brand] = brand

    logger.info("纠错词典构建完成：%d 个标准词条（手动精准维护）", len(correction_dict))
    return correction_dict


# 懒加载缓存（避免每次调用都重新解析 Markdown）
_hotwords_cache: str | None = None
_correction_dict_cache: dict[str, str] | None = None


def get_hotwords_cached() -> str:
    """带缓存的热词获取（首次调用时解析 Markdown，后续直接返回缓存）。"""
    global _hotwords_cache
    if _hotwords_cache is None:
        _hotwords_cache = get_hotwords_string()
    return _hotwords_cache


def get_correction_dict_cached() -> dict[str, str]:
    """带缓存的纠错词典获取。"""
    global _correction_dict_cache
    if _correction_dict_cache is None:
        _correction_dict_cache = build_correction_dictionary()
    return _correction_dict_cache
