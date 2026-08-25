"""剪辑任务成功语义回归测试。"""

from app.services.tasks.batch_runners import clip_session_render_succeeded


def test_zero_rendered_clips_is_session_failure():
    """AI 选段成功但全部渲染失败时，不能把任务标记为完成。"""
    assert not clip_session_render_succeeded(
        {"selected_count": 5, "rendered_count": 0, "failed_count": 5}
    )


def test_partial_render_is_success_with_separate_warning_counts():
    """只要存在真实成片即可完成，局部失败由独立警告计数表达。"""
    assert clip_session_render_succeeded(
        {
            "selected_count": 5,
            "rendered_count": 3,
            "failed_count": 2,
            "subtitle_alignment_warning_count": 1,
        }
    )
