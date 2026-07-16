"""Add anchor schedule templates imported from 排班.xls.

Revision ID: b2d2e3f4a5b6
Revises: a2d2e3f4a5b6
"""
from datetime import time

from alembic import op
import sqlalchemy as sa


revision = "b2d2e3f4a5b6"
down_revision = "a2d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "anchor_schedules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="排班ID"),
        sa.Column("source_anchor_name", sa.String(100), nullable=False, comment="排班表中的主播姓名"),
        sa.Column("display_name", sa.String(100), nullable=False, comment="页面展示名称"),
        sa.Column("match_keywords", sa.JSON(), nullable=False, comment="匹配真实采集主播名称的关键词"),
        sa.Column("room_name", sa.String(100), nullable=False, comment="直播间"),
        sa.Column("network_name", sa.String(100), nullable=True, comment="直播网络"),
        sa.Column("session_index", sa.Integer(), nullable=False, comment="主播当天第几场"),
        sa.Column("planned_start_time", sa.Time(), nullable=False, comment="计划开播时间"),
        sa.Column("planned_end_time", sa.Time(), nullable=False, comment="计划下播时间"),
        sa.Column(
            "expected_duration_minutes",
            sa.Integer(),
            nullable=False,
            server_default="80",
            comment="标准直播分钟数",
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true(), comment="是否启用"),
        sa.Column("source_name", sa.String(200), nullable=False, server_default="排班.xls", comment="排班来源"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_anchor_name", "session_index", name="uq_anchor_schedule_slot"),
    )

    common = {"expected_duration_minutes": 80, "active": True, "source_name": "排班.xls"}
    rows = [
        ("韩龙飞", "韩龙飞（飞哥）", ["韩龙飞", "飞哥"], "1号直播间", "商业宽带1", 1, "17:55", "19:15"),
        ("韩龙飞", "韩龙飞（飞哥）", ["韩龙飞", "飞哥"], "1号直播间", "商业宽带1", 2, "19:50", "21:10"),
        ("韩龙飞", "韩龙飞（飞哥）", ["韩龙飞", "飞哥"], "1号直播间", "商业宽带1", 3, "22:20", "23:40"),
        ("刘文豪", "刘文豪（文豪）", ["刘文豪", "文豪"], "2号直播间", "家庭宽带1", 1, "09:50", "11:10"),
        ("刘文豪", "刘文豪（文豪）", ["刘文豪", "文豪"], "2号直播间", "家庭宽带1", 2, "11:55", "13:15"),
        ("刘文豪", "刘文豪（文豪）", ["刘文豪", "文豪"], "2号直播间", "家庭宽带1", 3, "15:05", "16:25"),
        ("刘文豪", "刘文豪（文豪）", ["刘文豪", "文豪"], "2号直播间", "家庭宽带1", 4, "17:45", "19:05"),
        ("王路权", "王路权（大全）", ["王路权", "大全"], "3号直播间", "家庭宽带2", 1, "11:20", "12:40"),
        ("王路权", "王路权（大全）", ["王路权", "大全"], "3号直播间", "家庭宽带2", 2, "13:15", "14:35"),
        ("王路权", "王路权（大全）", ["王路权", "大全"], "3号直播间", "家庭宽带2", 3, "16:25", "17:45"),
        ("王路权", "王路权（大全）", ["王路权", "大全"], "3号直播间", "家庭宽带2", 4, "18:10", "19:30"),
        ("民哥", "民哥", ["民哥"], "4号直播间", "商业宽带2", 1, "06:30", "07:50"),
        ("民哥", "民哥", ["民哥"], "4号直播间", "商业宽带2", 2, "08:20", "09:40"),
        ("民哥", "民哥", ["民哥"], "4号直播间", "商业宽带2", 3, "20:05", "21:25"),
        ("丹丹", "丹丹（丹姐）", ["丹丹", "丹姐"], "4号直播间", "商业宽带1", 1, "12:55", "14:15"),
        ("丹丹", "丹丹（丹姐）", ["丹丹", "丹姐"], "4号直播间", "商业宽带1", 2, "15:40", "17:00"),
        ("丹丹", "丹丹（丹姐）", ["丹丹", "丹姐"], "4号直播间", "商业宽带1", 3, "17:30", "18:50"),
    ]
    op.bulk_insert(
        table,
        [
            {
                **common,
                "source_anchor_name": anchor,
                "display_name": display,
                "match_keywords": keywords,
                "room_name": room,
                "network_name": network,
                "session_index": index,
                "planned_start_time": time.fromisoformat(start),
                "planned_end_time": time.fromisoformat(end),
            }
            for anchor, display, keywords, room, network, index, start, end in rows
        ],
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW de_v_fact_anchor_schedule AS
        SELECT id, source_anchor_name, display_name, room_name, network_name,
               session_index, planned_start_time, planned_end_time,
               expected_duration_minutes, active, source_name, updated_at
        FROM anchor_schedules
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS de_v_fact_anchor_schedule")
    op.drop_table("anchor_schedules")
