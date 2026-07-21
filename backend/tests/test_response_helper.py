"""
测试统一响应包装 — 验证 ok_response 与 SoybeanAdmin 前端兼容。
"""

from app.core.response import ok_response


class TestOkResponse:
    """验证统一响应格式"""

    def test_default_structure(self):
        """默认响应格式：code=0000, msg=success"""
        result = ok_response()
        assert result == {"code": "0000", "data": None, "msg": "success"}

    def test_with_data(self):
        """带数据的响应"""
        result = ok_response(data={"name": "test"})
        assert result["code"] == "0000"
        assert result["data"] == {"name": "test"}

    def test_with_custom_msg(self):
        """自定义消息"""
        result = ok_response(data="token_string", msg="登录成功")
        assert result == {"code": "0000", "data": "token_string", "msg": "登录成功"}

    def test_with_list_data(self):
        """列表数据"""
        result = ok_response(data=[1, 2, 3])
        assert result["data"] == [1, 2, 3]

    def test_code_is_always_0000(self):
        """code 始终是 0000（SoybeanAdmin 约定）"""
        assert ok_response()["code"] == "0000"
        assert ok_response(data={})["code"] == "0000"
        assert ok_response(msg="anything")["code"] == "0000"

    def test_soybean_admin_compatibility(self):
        """SoybeanAdmin 前端期望的响应字段都存在"""
        result = ok_response(data={"user": "admin"}, msg="success")
        assert "code" in result
        assert "data" in result
        assert "msg" in result
        assert result["code"] == "0000"
