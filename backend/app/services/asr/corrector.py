"""ASR 后处理纠错器 —— 用行业知识词典做编辑距离模糊匹配 + 文本校正

原理：
ASR（语音转文字）对专有名词（品牌名、行业术语）容易识别错，
比如把「好想来」识别成「好想赖」，把「快招公司」识别成「快招工资」。

纠错流程：
1. 从行业知识中构建标准词典（品牌名 + 行业术语）
2. 对 ASR 输出的每段文本做分词
3. 对每个词，计算它与词典中所有词的编辑距离
4. 如果编辑距离 ≤ 阈值，替换为词典中的标准写法

安全策略：
- 只有编辑距离足够近时才纠错（避免误改正常词汇）
- 短词（2-3字）阈值=1，中词（4-5字）阈值=1，长词（6字+）阈值=2
- 已经在词典里的词不做处理（说明 ASR 已经识别对了）
"""

import logging

from app.services.asr.hotwords import get_correction_dict_cached

logger = logging.getLogger(__name__)

# 编辑距离阈值：超过这个距离就不纠错（防止误杀）
_EDIT_DISTANCE_MAX = 2


def _edit_distance(s1: str, s2: str) -> int:
    """计算两个字符串的莱文斯坦编辑距离（Levenshtein distance）。

    编辑距离 = 最少需要多少次「增/删/改」操作才能把 s1 变成 s2。
    例如：「快招工资」→「快招公司」= 1 次修改（资→公）

    使用动态规划实现，O(n*m) 时间复杂度。
    """
    if len(s1) < len(s2):
        return _edit_distance(s2, s1)

    # s1 是较长的字符串
    prev = list(range(len(s2) + 1))
    curr = [0] * (len(s2) + 1)

    for i, c1 in enumerate(s1):
        curr[0] = i + 1
        for j, c2 in enumerate(s2):
            if c1 == c2:
                curr[j + 1] = prev[j]
            else:
                curr[j + 1] = 1 + min(prev[j], prev[j + 1], curr[j])
        prev, curr = curr, prev

    return prev[-1]


def _get_threshold(word_len: int) -> int:
    """根据词长度返回编辑距离阈值。

    统一阈值=1（只纠错差一个字的），这是 ASR 最常见的错误模式。
    阈值=2 会产生大量误匹配（如「个零食」→「爱零食」）。
    """
    return 1


def _find_best_match(word: str, dictionary: dict[str, str]) -> str | None:
    """在词典中找到与给定词编辑距离最近的标准词。

    Args:
        word: 待检查的词
        dictionary: 标准词典 {标准写法: 标准写法}

    Returns:
        匹配到的标准词（如果距离在阈值内），否则返回 None
    """
    # 已经在词典里的词，不需要纠错
    if word in dictionary:
        return None

    threshold = _get_threshold(len(word))
    best_match = None
    best_distance = threshold + 1

    for standard_word in dictionary:
        # 长度差太多肯定不是同一个词，跳过（性能优化）
        if abs(len(word) - len(standard_word)) > threshold:
            continue

        distance = _edit_distance(word, standard_word)
        if distance < best_distance:
            best_distance = distance
            best_match = standard_word
            # 编辑距离为 0 说明完全相同，但前面已经检查过不在词典里，
            # 所以不会走到这里。编辑距离为 1 已经是最优，可以提前退出。
            if distance == 1 and len(word) <= 4:
                break

    if best_distance <= threshold and best_match is not None:
        return best_match
    return None


def correct_text(text: str) -> str:
    """对一段 ASR 转写文本做行业知识纠错。

    处理逻辑（精确匹配法，避免误杀）：
    1. 对词典中每个词条，在文本中逐位置扫描同长度的子串
    2. 如果子串编辑距离在阈值内且子串本身不在词典中，就替换
    3. 长的词条优先处理，避免短词把长品牌名的前半段替换掉
    4. 每个位置只替换一次（替换后跳过）

    Args:
        text: ASR 输出的原始文本

    Returns:
        纠错后的文本
    """
    if not text or not text.strip():
        return text

    dictionary = get_correction_dict_cached()
    if not dictionary:
        return text

    import re

    result = text
    # 标记哪些位置已经被纠错替换过（避免重复替换）
    replaced: set[int] = set()

    # ── 第 0 步：标记所有「已经是正确词典词条」的位置，这些位置绝对不碰 ──
    protected: set[int] = set()
    for term in dictionary:
        term_len = len(term)
        idx = 0
        while True:
            idx = result.find(term, idx)
            if idx == -1:
                break
            for pos in range(idx, idx + term_len):
                protected.add(pos)
            idx += 1

    # 按词条长度从长到短排序，长的优先处理
    sorted_terms = sorted(dictionary.keys(), key=len, reverse=True)

    for term in sorted_terms:
        term_len = len(term)
        threshold = _get_threshold(term_len)

        i = 0
        while i <= len(result) - term_len:
            # 跳过已被替换或受保护的窗口（窗口内任意位置被保护就跳过）
            window_positions = set(range(i, i + term_len))
            if window_positions & replaced:
                i += 1
                continue
            if window_positions & protected:
                i += 1
                continue

            window = result[i:i + term_len]

            # 已经是正确写法，跳过
            if window == term:
                i += 1
                continue

            # 只检查全为汉字的窗口
            if not re.fullmatch(r'[一-鿿]+', window):
                i += 1
                continue

            # 窗口本身已在词典中（是另一个正确的品牌名），不纠错
            if window in dictionary:
                i += 1
                continue

            # 计算编辑距离
            dist = _edit_distance(window, term)
            if dist <= threshold:
                logger.debug("ASR 纠错: '%s' → '%s' (距离=%d)", window, term, dist)
                result = result[:i] + term + result[i + term_len:]
                # 标记这段已被替换 + 受保护（避免后续其他词条覆盖）
                for pos in range(i, i + term_len):
                    replaced.add(pos)
                    protected.add(pos)
                i += term_len
            else:
                i += 1

    return result


def correct_segment_text(text: str) -> dict[str, str | list[str]]:
    """对一段 ASR 转写文本做纠错，并返回详细结果。

    Args:
        text: ASR 输出的原始文本

    Returns:
        {
            "original": 原始文本,
            "corrected": 纠错后文本,
            "changes": ["快招工资→快招公司", ...]  # 修改记录
        }
    """
    if not text or not text.strip():
        return {"original": text or "", "corrected": text or "", "changes": []}

    dictionary = get_correction_dict_cached()
    if not dictionary:
        return {"original": text, "corrected": text, "changes": []}

    changes: list[str] = []
    result = text
    replaced: set[int] = set()

    import re

    # 标记所有已正确识别的词典词条位置（不纠错这些区域）
    protected: set[int] = set()
    for term in dictionary:
        term_len = len(term)
        idx = 0
        while True:
            idx = result.find(term, idx)
            if idx == -1:
                break
            for pos in range(idx, idx + term_len):
                protected.add(pos)
            idx += 1

    sorted_terms = sorted(dictionary.keys(), key=len, reverse=True)

    for term in sorted_terms:
        term_len = len(term)
        threshold = _get_threshold(term_len)

        i = 0
        while i <= len(result) - term_len:
            window_positions = set(range(i, i + term_len))
            if window_positions & replaced:
                i += 1
                continue

            if window_positions & protected:
                i += 1
                continue

            window = result[i:i + term_len]
            if window == term:
                i += 1
                continue

            if not re.fullmatch(r'[一-鿿]+', window):
                i += 1
                continue

            if window in dictionary:
                i += 1
                continue

            dist = _edit_distance(window, term)
            if dist <= threshold:
                changes.append(f"{window}→{term}")
                result = result[:i] + term + result[i + term_len:]
                for pos in range(i, i + term_len):
                    replaced.add(pos)
                    protected.add(pos)
                i += term_len
            else:
                i += 1

    return {
        "original": text,
        "corrected": result,
        "changes": changes,
    }
