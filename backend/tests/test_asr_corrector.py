"""ASR 纠错器单元测试"""
from app.services.asr.corrector import _edit_distance, correct_text, correct_segment_text


class TestEditDistance:
    """编辑距离计算"""

    def test_same_string_zero(self):
        assert _edit_distance("好想来", "好想来") == 0

    def test_one_char_diff(self):
        assert _edit_distance("好想赖", "好想来") == 1

    def test_two_char_diff(self):
        assert _edit_distance("快招工资", "快招公司") == 2

    def test_different_length(self):
        assert _edit_distance("零食", "零食很忙") == 2


class TestCorrectText:
    """纠错功能"""

    def test_correct_brand_misspelling(self):
        """品牌名单字错误应被纠正"""
        result = correct_text("好想赖和赵一明都是头部品牌")
        assert "好想来" in result
        assert "赵一鸣" in result

    def test_no_correction_for_common_text(self):
        """普通文本不应被纠错"""
        text = "今天给大家介绍几款产品"
        assert correct_text(text) == text

    def test_no_correction_for_already_correct(self):
        """已正确的品牌名不应被修改"""
        text = "割韭菜的快招公司太多了"
        assert correct_text(text) == text

    def test_empty_text(self):
        """空文本处理"""
        assert correct_text("") == ""
        assert correct_text("  ") == "  "

    def test_correct_single_char_error_in_brand(self):
        """品牌名单字错误应纠正"""
        result = correct_text("贪吃长柜是个快招品牌")
        assert "贪吃掌柜" in result

    def test_multiple_corrections_in_one_text(self):
        """一段文本中多个错误都应纠正"""
        result = correct_text("河南零百味和贪吃长柜")
        assert result == "河南零百味和贪吃掌柜"

    def test_non_chinese_preserved(self):
        """非中文字符保持原样"""
        text = "价格: 55~60万, 面积: 130㎡"
        assert correct_text(text) == text


class TestCorrectSegmentText:
    """详细纠错信息"""

    def test_returns_changes_list(self):
        result = correct_segment_text("好想赖和赵一明")
        assert result["original"] == "好想赖和赵一明"
        assert len(result["changes"]) > 0
        assert "好想赖→好想来" in result["changes"] or any("好想来" in c for c in result["changes"])
