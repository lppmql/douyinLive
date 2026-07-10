"""Phase 10: 为直播场次和趋势补充直播大屏指标

Revision ID: i1d2e3f4a5b6
Revises: h1d2e3f4a5b6
Create Date: 2026-07-10 22:40:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "i1d2e3f4a5b6"
down_revision = "h1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("live_sessions", sa.Column("viewed_count", sa.Integer(), nullable=True, server_default="0", comment="看过人数"))
    op.add_column("live_sessions", sa.Column("avg_online_count", sa.Integer(), nullable=True, server_default="0", comment="平均在线人数"))
    op.add_column("live_sessions", sa.Column("fans_avg_watch_seconds", sa.DECIMAL(10, 1), nullable=True, server_default="0", comment="粉丝停留时长（秒）"))
    op.add_column("live_sessions", sa.Column("private_message_longterm_count", sa.Integer(), nullable=True, server_default="0", comment="私信长效转化人数"))
    op.add_column("live_sessions", sa.Column("mini_windmill_click_rate", sa.DECIMAL(10, 4), nullable=True, server_default="0", comment="小风车点击率"))
    op.add_column("live_sessions", sa.Column("card_click_count", sa.Integer(), nullable=True, server_default="0", comment="卡片点击次数"))
    op.add_column("live_sessions", sa.Column("card_click_rate", sa.DECIMAL(10, 4), nullable=True, server_default="0", comment="卡片点击率"))
    op.add_column("live_sessions", sa.Column("follow_rate", sa.DECIMAL(10, 4), nullable=True, server_default="0", comment="关注率"))
    op.add_column("live_sessions", sa.Column("share_count", sa.Integer(), nullable=True, server_default="0", comment="分享次数"))
    op.add_column("live_sessions", sa.Column("share_users", sa.Integer(), nullable=True, server_default="0", comment="分享人数"))
    op.add_column("live_sessions", sa.Column("like_count", sa.Integer(), nullable=True, server_default="0", comment="点赞次数"))
    op.add_column("live_sessions", sa.Column("like_users", sa.Integer(), nullable=True, server_default="0", comment="点赞人数"))
    op.add_column("live_sessions", sa.Column("comment_users", sa.Integer(), nullable=True, server_default="0", comment="评论人数"))
    op.add_column("live_sessions", sa.Column("interaction_count", sa.Integer(), nullable=True, server_default="0", comment="互动次数"))
    op.add_column("live_sessions", sa.Column("interaction_users", sa.Integer(), nullable=True, server_default="0", comment="互动人数"))
    op.add_column("live_sessions", sa.Column("watch_count", sa.Integer(), nullable=True, server_default="0", comment="观看次数"))
    op.add_column("live_sessions", sa.Column("watch_over_1m_count", sa.Integer(), nullable=True, server_default="0", comment="大于1分钟观看人次"))
    op.add_column("live_sessions", sa.Column("fans_club_join_count", sa.Integer(), nullable=True, server_default="0", comment="加粉丝团人数"))
    op.add_column("live_sessions", sa.Column("fans_club_join_rate", sa.DECIMAL(10, 4), nullable=True, server_default="0", comment="加粉丝团率"))
    op.add_column("live_sessions", sa.Column("gift_count", sa.Integer(), nullable=True, server_default="0", comment="打赏次数"))
    op.add_column("live_sessions", sa.Column("gift_amount", sa.DECIMAL(10, 2), nullable=True, server_default="0", comment="打赏金额"))
    op.add_column("live_sessions", sa.Column("dislike_count", sa.Integer(), nullable=True, server_default="0", comment="不感兴趣次数"))
    op.add_column("live_sessions", sa.Column("dislike_users", sa.Integer(), nullable=True, server_default="0", comment="不感兴趣人数"))
    op.add_column("live_sessions", sa.Column("wechat_add_count", sa.Integer(), nullable=True, server_default="0", comment="企业微信添加数"))
    op.add_column("live_sessions", sa.Column("wechat_add_cost", sa.DECIMAL(10, 2), nullable=True, server_default="0", comment="企业微信添加成本"))
    op.add_column("live_sessions", sa.Column("form_submit_count", sa.Integer(), nullable=True, server_default="0", comment="表单提交数"))
    op.add_column("live_sessions", sa.Column("form_submit_users", sa.Integer(), nullable=True, server_default="0", comment="表单提交人数"))
    op.add_column("live_sessions", sa.Column("form_submit_cost", sa.DECIMAL(10, 2), nullable=True, server_default="0", comment="表单提交成本"))
    op.add_column("live_sessions", sa.Column("fans_view_ratio", sa.DECIMAL(10, 4), nullable=True, server_default="0", comment="场观粉丝占比"))
    op.add_column("live_sessions", sa.Column("scene_lead_conversion_rate", sa.DECIMAL(10, 4), nullable=True, server_default="0", comment="线索转化率"))

    op.add_column("live_metrics", sa.Column("clue_count", sa.Integer(), nullable=True, server_default="0", comment="全场景线索人数"))
    op.add_column("live_metrics", sa.Column("windmill_click_count", sa.Integer(), nullable=True, server_default="0", comment="风车点击次数"))
    op.add_column("live_metrics", sa.Column("card_click_count", sa.Integer(), nullable=True, server_default="0", comment="卡片点击次数"))
    op.add_column("live_metrics", sa.Column("wechat_add_count", sa.Integer(), nullable=True, server_default="0", comment="企业微信添加数"))
    op.add_column("live_metrics", sa.Column("form_submit_count", sa.Integer(), nullable=True, server_default="0", comment="表单提交数"))
    op.add_column("live_metrics", sa.Column("form_submit_users", sa.Integer(), nullable=True, server_default="0", comment="表单提交人数"))
    op.add_column("live_metrics", sa.Column("cost_amount", sa.DECIMAL(10, 2), nullable=True, server_default="0", comment="消耗金额"))


def downgrade() -> None:
    op.drop_column("live_metrics", "cost_amount")
    op.drop_column("live_metrics", "form_submit_users")
    op.drop_column("live_metrics", "form_submit_count")
    op.drop_column("live_metrics", "wechat_add_count")
    op.drop_column("live_metrics", "card_click_count")
    op.drop_column("live_metrics", "windmill_click_count")
    op.drop_column("live_metrics", "clue_count")

    op.drop_column("live_sessions", "scene_lead_conversion_rate")
    op.drop_column("live_sessions", "fans_view_ratio")
    op.drop_column("live_sessions", "form_submit_cost")
    op.drop_column("live_sessions", "form_submit_users")
    op.drop_column("live_sessions", "form_submit_count")
    op.drop_column("live_sessions", "wechat_add_cost")
    op.drop_column("live_sessions", "wechat_add_count")
    op.drop_column("live_sessions", "dislike_users")
    op.drop_column("live_sessions", "dislike_count")
    op.drop_column("live_sessions", "gift_amount")
    op.drop_column("live_sessions", "gift_count")
    op.drop_column("live_sessions", "fans_club_join_rate")
    op.drop_column("live_sessions", "fans_club_join_count")
    op.drop_column("live_sessions", "watch_over_1m_count")
    op.drop_column("live_sessions", "watch_count")
    op.drop_column("live_sessions", "interaction_users")
    op.drop_column("live_sessions", "interaction_count")
    op.drop_column("live_sessions", "comment_users")
    op.drop_column("live_sessions", "like_users")
    op.drop_column("live_sessions", "like_count")
    op.drop_column("live_sessions", "share_users")
    op.drop_column("live_sessions", "share_count")
    op.drop_column("live_sessions", "follow_rate")
    op.drop_column("live_sessions", "card_click_rate")
    op.drop_column("live_sessions", "card_click_count")
    op.drop_column("live_sessions", "mini_windmill_click_rate")
    op.drop_column("live_sessions", "private_message_longterm_count")
    op.drop_column("live_sessions", "fans_avg_watch_seconds")
    op.drop_column("live_sessions", "avg_online_count")
    op.drop_column("live_sessions", "viewed_count")
