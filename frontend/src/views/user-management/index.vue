<!--
  用户管理 — 编排器（方案 A 重构）
  职责：组合子组件。所有状态和业务逻辑委托给 useUserManagement composable。
  408 行 → ~80 行
-->
<script setup lang="ts">
import { onMounted } from 'vue';
import { NButton, NCard, NAlert, NInput, NTag, NSpace } from 'naive-ui';
import TableHeaderOperation from '@/components/advanced/table-header-operation.vue';
import UserDrawer from './modules/UserDrawer.vue';
import { useUserManagement } from './composables/useUserManagement';
import type { UserRecord } from '@/service/api/user';

defineOptions({ name: 'UserManagement' });

const um = useUserManagement();

// 设置表格列（传入编辑和删除回调，列里的 NPopconfirm 和 NButton 需要它们）
onMounted(() => {
  um.setColumns(um.openEdit, um.handleDelete);
});
</script>

<template>
  <NSpace vertical :size="16" class="business-page">
    <NCard :bordered="false" class="card-wrapper h-full" title="用户列表">
      <!-- 加载错误 -->
      <NAlert v-if="um.tableError.value" class="mb-16px" type="error" :bordered="false" show-icon>
        {{ um.tableError.value }}
        <NButton size="small" secondary @click="um.getData">重新加载</NButton>
      </NAlert>

      <!-- 工具栏：搜索 + 列设置 -->
      <div class="business-toolbar mb-16px">
        <div class="business-toolbar__filters">
          <NInput
            v-model:value="um.searchUsername.value"
            placeholder="搜索用户名"
            clearable
            class="w-220px"
            @keyup.enter="um.handleSearch"
          />
          <NButton type="primary" @click="um.handleSearch">搜索</NButton>
          <NButton @click="um.handleResetSearch">重置</NButton>
        </div>
        <div class="business-toolbar__actions">
          <NButton type="primary" @click="um.openCreate">
            <template #icon><SvgIcon icon="mdi:account-plus-outline" /></template>
            新增用户
          </NButton>
          <TableHeaderOperation v-model:columns="um.columnChecks.value" :loading="um.loading.value" @refresh="um.getData">
            <template #default>
              <NTag type="info" round size="small">超级管理员不可删除</NTag>
            </template>
          </TableHeaderOperation>
        </div>
      </div>

      <!-- 数据表格 -->
      <div class="business-table-shell">
        <NDataTable
          :loading="um.loading.value"
          :columns="(um.tableColumns.value as any)"
          :data="um.users.value"
          :pagination="um.mobilePagination.value"
          :row-key="(row: UserRecord) => row.id"
          :scroll-x="Math.max(um.scrollX.value, 1080)"
          :max-height="520"
          remote
          size="small"
          striped
          :bordered="false"
          class="min-h-0"
        />
      </div>
    </NCard>

    <!-- 新增/编辑抽屉 -->
    <UserDrawer
      v-model:visible="um.drawerVisible.value"
      :operate-type="um.operateType.value"
      :form-data="um.formData"
      :form-rules="um.formRules"
      :role-options="um.roleOptions"
      :status-options="um.statusOptions"
      :saving="um.saving.value"
      @update-field="um.updateFormField"
      @save="um.handleSave"
    />
  </NSpace>
</template>
