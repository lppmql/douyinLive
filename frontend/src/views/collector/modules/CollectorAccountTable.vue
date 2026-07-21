<!--
  采集账号表格 — 从 collector/index.vue 拆分
  包含列定义和所有账号相关操作（检查存活、重新登录、删除）
-->
<script setup lang="ts">
import { h } from 'vue';
import { NCard, NDataTable, NButton, NSpace, NTag } from 'naive-ui';
import { $t } from '@/locales';

defineOptions({ name: 'CollectorAccountTable' });

const props = defineProps<{
  /** 页面整体加载中 */
  loading: boolean;
  /** 采集账号列表 */
  accounts: Api.Douyin.CollectorAccount[];
  /** 正在检查存活的账号 ID（用于显示按钮 loading） */
  accountHealthLoadingId: number | null;
  /** 是否有采集任务运行中（禁用部分操作） */
  collectionRunning: boolean;
  /** 监控是否运行中（禁用部分操作） */
  monitorRunning: boolean;
}>();

const emit = defineEmits<{
  /** 刷新数据 */
  (e: 'refresh'): void;
  /** 扫码登录新账号 */
  (e: 'startLogin'): void;
  /** 检查账号 Cookie 存活 */
  (e: 'healthCheck', row: Api.Douyin.CollectorAccount): void;
  /** 重新登录过期账号 */
  (e: 'reLogin', accountId: number): void;
  /** 删除账号 */
  (e: 'deleteAccount', accountId: number): void;
}>();

/** 账号行 key */
function getAccountRowKey(row: Api.Douyin.CollectorAccount) {
  return row.id;
}

/** 账号表格列定义 */
const accountColumns = [
  { title: 'ID', key: 'id', width: 60 },
  {
    title: () => $t('page.collector.accountName'),
    key: 'account_name',
    width: 180,
    fixed: 'left' as const,
    ellipsis: { tooltip: true }
  },
  {
    title: () => $t('page.collector.douyinId'),
    key: 'douyin_id',
    minWidth: 150,
    ellipsis: { tooltip: true },
    render(row: Api.Douyin.CollectorAccount) {
      if (row.douyin_id) return row.douyin_id;
      return h(
        NButton,
        {
          text: true,
          type: 'warning',
          size: 'tiny',
          loading: props.accountHealthLoadingId === row.id,
          onClick: () => emit('healthCheck', row)
        },
        { default: () => '未获取 / 点此刷新' }
      );
    }
  },
  {
    title: () => $t('page.collector.loginStatus'),
    key: 'login_status',
    width: 100,
    render(row: Api.Douyin.CollectorAccount) {
      const map: Record<string, { type: 'success' | 'warning' | 'error' | 'info'; label: string }> = {
        logged_in: { type: 'success', label: $t('page.collector.loggedIn') },
        expired: { type: 'error', label: $t('page.collector.statusExpired') },
        never: { type: 'warning', label: $t('page.collector.neverLogin') }
      };
      const info = map[row.login_status] || { type: 'warning' as const, label: row.login_status };
      return h(NTag, { type: info.type, size: 'small' }, { default: () => info.label });
    }
  },
  {
    title: () => $t('page.collector.lastLogin'),
    key: 'last_login_at',
    width: 170,
    render(row: Api.Douyin.CollectorAccount) {
      return row.last_login_at || '-';
    }
  },
  {
    title: () => $t('common.action'),
    key: 'actions',
    width: 220,
    fixed: 'right' as const,
    render(row: Api.Douyin.CollectorAccount) {
      const btns: ReturnType<typeof h>[] = [];
      // 检查存活按钮
      btns.push(
        h(
          NButton,
          {
            text: true,
            type: 'primary',
            size: 'small',
            loading: props.accountHealthLoadingId === row.id,
            disabled: props.collectionRunning || props.monitorRunning,
            onClick: () => emit('healthCheck', row)
          },
          { default: () => '检查存活' }
        )
      );
      // 过期账号显示重新登录按钮
      if (row.login_status === 'expired') {
        btns.push(
          h(
            NButton,
            {
              text: true,
              type: 'warning',
              size: 'small',
              onClick: () => emit('reLogin', row.id)
            },
            { default: () => $t('page.collector.reLogin') }
          )
        );
      }
      // 删除按钮
      btns.push(
        h(
          NButton,
          {
            text: true,
            type: 'error',
            size: 'small',
            onClick: () => emit('deleteAccount', row.id)
          },
          { default: () => $t('page.collector.deleteAccount') }
        )
      );
      return h(NSpace, { size: 12, wrap: false }, { default: () => btns });
    }
  }
];
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" :title="$t('page.collector.accountList')">
    <template #header-extra>
      <NSpace>
        <NButton size="small" :loading="loading" @click="emit('refresh')">
          <template #icon><SvgIcon icon="mdi:refresh" /></template>
          {{ $t('common.refresh') }}
        </NButton>
        <NButton type="primary" size="small" @click="emit('startLogin')">
          <template #icon><SvgIcon icon="mdi:qrcode-scan" /></template>
          {{ $t('page.collector.scanLogin') }}
        </NButton>
      </NSpace>
    </template>
    <div class="business-table-shell">
      <NDataTable
        :loading="loading"
        :columns="accountColumns"
        :data="accounts"
        :row-key="getAccountRowKey"
        :scroll-x="980"
        :bordered="false"
        size="small"
        :empty-text="$t('page.collector.noAccount')"
      />
    </div>
  </NCard>
</template>
