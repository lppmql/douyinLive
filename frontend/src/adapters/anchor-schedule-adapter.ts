/**
 * 主播排班页面 — 数据适配器
 *
 * 负责把原始数据转换成表格列定义等前端展示配置。
 * createColumns 用 h() 渲染函数构建复杂列内容。
 */
import { h } from 'vue';
import dayjs from 'dayjs';
import { NAvatar, NButton, NTag } from 'naive-ui';
import {
  statusMap,
  formatClock,
  formatDuration,
  getAnchorAvatarUrl
} from '@/utils/anchorScheduleHelpers';

// ========== 类型定义 ==========

/** createColumns 需要的依赖注入参数 */
export interface ColumnDependencies {
  /** 仪表盘数据（响应式 ref 的值） */
  dashboard: Api.Douyin.AnchorScheduleDashboard | null;
  /** 点击"查看场次"的回调 */
  onOpenSession: (sessionId: number | null) => void;
}

// ========== 适配函数 ==========

/**
 * 创建排班数据表格的列定义
 *
 * 用 h() 渲染函数而非模板，因为列内容包含头像、状态标签等动态组件。
 * 依赖通过参数注入，保持函数纯净（不直接访问响应式变量）。
 */
export function createColumns(deps: ColumnDependencies): NaiveUI.TableColumn<Api.Douyin.AnchorScheduleRow>[] {
  const { dashboard, onOpenSession } = deps;

  return [
    {
      title: '主播',
      key: 'display_name',
      width: 210,
      fixed: 'left',
      render(row) {
        const anchor = dashboard?.anchors.find(item => item.source_anchor_name === row.source_anchor_name);
        const avatarUrl = getAnchorAvatarUrl(anchor);
        return h('div', { class: 'flex items-center gap-10px' }, [
          h(
            NAvatar,
            { round: true, size: 36, src: avatarUrl },
            avatarUrl ? undefined : () => row.source_anchor_name[0]
          ),
          h('div', { class: 'min-w-0' }, [
            h('div', { class: 'truncate font-600' }, row.display_name),
            h('div', { class: 'truncate text-12px text-gray-400' }, anchor?.actual_anchor_name || '等待匹配真实账号')
          ])
        ]);
      }
    },
    {
      title: '日期',
      key: 'schedule_date',
      width: 112,
      render: row => dayjs(row.schedule_date).format('YYYY-MM-DD')
    },
    {
      title: '场次',
      key: 'session_index',
      width: 76,
      render: row => (row.is_extra ? `加场 ${row.extra_index}` : `第 ${row.session_index} 场`)
    },
    {
      title: '直播间 / 网络',
      key: 'room_name',
      width: 165,
      render(row) {
        return h('div', [
          h('div', { class: 'font-500' }, row.room_name),
          h('div', { class: 'text-12px text-gray-400' }, row.network_name || '-')
        ]);
      }
    },
    {
      title: '计划时间',
      key: 'planned_start_time',
      width: 135,
      render: row =>
        row.is_extra ? '计划外加场' : `${formatClock(row.planned_start_time)} - ${formatClock(row.planned_end_time)}`
    },
    {
      title: '标准时长',
      key: 'expected_duration_minutes',
      width: 90,
      render: row => (row.is_extra ? '-' : `${row.expected_duration_minutes} 分钟`)
    },
    {
      title: '实际开播',
      key: 'actual_start',
      width: 105,
      render: row => formatClock(row.actual_session?.live_start_time || null)
    },
    {
      title: '实际时长',
      key: 'actual_duration',
      width: 100,
      render: row => (row.actual_session ? formatDuration(row.actual_session.live_duration_seconds) : '-')
    },
    {
      title: '执行状态',
      key: 'status',
      width: 100,
      render(row) {
        const info = statusMap[row.status];
        const label = row.is_extra && row.status === 'invalid' ? '无效加场' : info.label;
        return h(NTag, { type: info.type, size: 'small', round: true, bordered: false }, () => label);
      }
    },
    {
      title: '提醒',
      key: 'warnings',
      minWidth: 260,
      ellipsis: { tooltip: true },
      render(row) {
        if (row.is_extra && row.status !== 'invalid') {
          return h('span', { class: 'text-info' }, '超过当天规定场次，标记为加场');
        }
        if (!row.warnings.length) return row.status === 'upcoming' ? '等待计划时间' : '无异常';
        return h(
          'span',
          { class: ['missing', 'invalid'].includes(row.status) ? 'text-error' : 'text-warning' },
          row.warnings.join('；')
        );
      }
    },
    {
      title: '操作',
      key: 'action',
      width: 90,
      fixed: 'right',
      render(row) {
        return h(
          NButton,
          {
            text: true,
            type: 'primary',
            size: 'small',
            disabled: !row.actual_session,
            onClick: () => onOpenSession(row.actual_session?.id || null)
          },
          () => '查看场次'
        );
      }
    }
  ];
}
