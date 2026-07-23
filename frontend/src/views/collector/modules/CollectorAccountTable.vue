<script setup lang="ts">
import { h } from 'vue';
import { NAlert, NAvatar, NButton, NCard, NDataTable, NSpace, NTag } from 'naive-ui';
import { formatFullTime } from '../utils/collectorHelpers';

defineOptions({ name: 'CollectorAccountTable' });

const props = defineProps<{
  loading: boolean;
  accounts: Api.Douyin.CollectorAccount[];
  accountHealthLoadingId: number | null;
  collectionRunning: boolean;
}>();

const emit = defineEmits<{
  (e: 'refresh'): void;
  (e: 'startLogin'): void;
  (e: 'healthCheck', row: Api.Douyin.CollectorAccount): void;
  (e: 'reLogin', accountId: number): void;
  (e: 'deleteAccount', accountId: number): void;
}>();

function identityName(row: Api.Douyin.CollectorAccount): string {
  return row.douyin_nickname || row.account_name || `采集账号 #${row.id}`;
}

function cookieState(row: Api.Douyin.CollectorAccount) {
  const states: Record<string, { label: string; type: 'success' | 'warning' | 'error' | 'default' }> = {
    valid: { label: 'Cookie 有效', type: 'success' },
    unchecked: { label: '等待检查', type: 'warning' },
    expired: { label: 'Cookie 已失效', type: 'error' },
    missing: { label: '未保存 Cookie', type: 'default' }
  };
  return states[row.cookie_status] || states.unchecked;
}

const accountColumns = [
  {
    title: '扫码抖音账号',
    key: 'douyin_nickname',
    width: 220,
    fixed: 'left' as const,
    render(row: Api.Douyin.CollectorAccount) {
      const name = identityName(row);
      return h('div', { class: 'flex min-w-0 items-center gap-10px' }, [
        h(
          NAvatar,
          { round: true, size: 34, color: '#e8f0ff', textColor: '#2563eb' },
          { default: () => name.slice(0, 1) }
        ),
        h('div', { class: 'min-w-0' }, [
          h('div', { class: 'truncate text-13px font-600', title: name }, name),
          h('div', { class: 'mt-2px truncate text-11px text-gray-400' }, row.account_name || `系统账号 #${row.id}`)
        ])
      ]);
    }
  },
  {
    title: '抖音号',
    key: 'douyin_id',
    width: 130,
    render(row: Api.Douyin.CollectorAccount) {
      if (row.douyin_id) return h('span', { class: 'font-mono text-12px' }, row.douyin_id);
      return h(
        NButton,
        {
          text: true,
          type: 'warning',
          size: 'tiny',
          loading: props.accountHealthLoadingId === row.id,
          disabled: props.collectionRunning,
          onClick: () => emit('healthCheck', row)
        },
        { default: () => '未获取，点击刷新' }
      );
    }
  },
  {
    title: '登录凭据',
    key: 'cookie_status',
    width: 270,
    render(row: Api.Douyin.CollectorAccount) {
      const state = cookieState(row);
      return h('div', { class: 'py-3px' }, [
        h(NSpace, { size: 5, wrap: true }, {
          default: () => [
            h(NTag, { type: state.type, size: 'small', bordered: false }, { default: () => state.label }),
            h(
              NTag,
              { type: row.fingerprint_saved ? 'info' : 'default', size: 'small', bordered: false },
              { default: () => (row.fingerprint_saved ? '指纹已保存' : '无指纹') }
            )
          ]
        }),
        h('div', { class: 'mt-5px text-11px leading-18px text-gray-400' }, [
          h('div', `刷新：${formatFullTime(row.cookie_refreshed_at)}`),
          h('div', `检查：${formatFullTime(row.cookie_checked_at)}`)
        ])
      ]);
    }
  },
  {
    title: '扫码时间',
    key: 'last_login_at',
    width: 160,
    render: (row: Api.Douyin.CollectorAccount) => formatFullTime(row.last_login_at)
  },
  {
    title: '操作',
    key: 'actions',
    width: 220,
    fixed: 'right' as const,
    render(row: Api.Douyin.CollectorAccount) {
      return h(NSpace, { size: 12, wrap: false }, {
        default: () => [
          h(
            NButton,
            {
              text: true,
              type: 'primary',
              size: 'small',
              loading: props.accountHealthLoadingId === row.id,
              disabled: props.collectionRunning,
              onClick: () => emit('healthCheck', row)
            },
            { default: () => '检查 Cookie' }
          ),
          h(
            NButton,
            { text: true, type: 'warning', size: 'small', onClick: () => emit('reLogin', row.id) },
            { default: () => '重新扫码' }
          ),
          h(
            NButton,
            { text: true, type: 'error', size: 'small', onClick: () => emit('deleteAccount', row.id) },
            { default: () => '删除账号' }
          )
        ]
      });
    }
  }
];
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" title="采集账号">
    <template #header-extra>
      <NSpace align="center" wrap>
        <NTag type="info" round :bordered="false">{{ accounts.length }} 个账号</NTag>
        <NButton size="small" :loading="loading" @click="emit('refresh')">
          <template #icon><SvgIcon icon="mdi:refresh" /></template>
          刷新
        </NButton>
        <NButton type="primary" size="small" @click="emit('startLogin')">
          <template #icon><SvgIcon icon="mdi:qrcode-scan" /></template>
          扫码登录新账号
        </NButton>
      </NSpace>
    </template>

    <NAlert class="mb-12px" type="info" :bordered="false" show-icon>
      “检查 Cookie”会复用该账号保存的浏览器指纹做真实访问，并自动补齐扫码昵称和抖音号；直播监控运行时也可检查。
    </NAlert>
    <div class="business-table-shell">
      <NDataTable
        :loading="loading"
        :columns="accountColumns"
        :data="accounts"
        :row-key="row => row.id"
        :scroll-x="1000"
        :max-height="330"
        :bordered="false"
        :single-line="false"
        size="small"
        striped
        empty-text="暂无采集账号，请先扫码登录"
      />
    </div>
  </NCard>
</template>
