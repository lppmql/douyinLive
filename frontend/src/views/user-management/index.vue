<script setup lang="ts">
import { h, reactive, ref } from 'vue';
import {
  NButton,
  NTag,
  NDataTable,
  NModal,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpace,
  useMessage,
  useDialog
} from 'naive-ui';
import { fetchUserList, fetchCreateUser, fetchUpdateUser, fetchDeleteUser, type UserRecord } from '@/service/api/user';
import { defaultTransform, useNaivePaginatedTable } from '@/hooks/common/table';
import TableHeaderOperation from '@/components/advanced/table-header-operation.vue';

defineOptions({ name: 'UserManagement' });

const message = useMessage();
const dialog = useDialog();

/* ---------- 搜索 ---------- */
const searchUsername = ref('');
const searchParams = reactive({ current: 1, size: 20, username: undefined as string | undefined });

/* ---------- 表格列 ---------- */
function renderRoles(roles: string[]) {
  if (!roles || roles.length === 0) return '-';
  return roles.map(role => {
    const type = role === 'R_SUPER' ? 'primary' : 'default';
    return h(
      NTag,
      { type, size: 'small', round: true },
      { default: () => (role === 'R_SUPER' ? '超级管理员' : '普通用户') }
    );
  });
}

function renderStatus(status: string) {
  const type = status === 'active' ? 'success' : 'error';
  const label = status === 'active' ? '启用' : '禁用';
  return h(NTag, { type, size: 'small', round: true }, { default: () => label });
}

function fmtDateTime(val: string | null): string {
  if (!val) return '-';
  const d = new Date(val);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function createColumns(): NaiveUI.TableColumn<UserRecord>[] {
  return [
    { title: 'ID', key: 'id', width: 60 },
    { title: '用户名', key: 'username', width: 100 },
    {
      title: '昵称',
      key: 'nickname',
      width: 100,
      render(row: UserRecord) {
        return row.nickname || '-';
      }
    },
    {
      title: '邮箱',
      key: 'email',
      width: 160,
      ellipsis: { tooltip: true },
      render(row: UserRecord) {
        return row.email || '-';
      }
    },
    {
      title: '角色',
      key: 'roles',
      width: 140,
      render(row: UserRecord) {
        return renderRoles(row.roles);
      }
    },
    {
      title: '状态',
      key: 'status',
      width: 80,
      render(row: UserRecord) {
        return renderStatus(row.status);
      }
    },
    {
      title: '最后登录',
      key: 'last_login_at',
      width: 150,
      render(row: UserRecord) {
        return fmtDateTime(row.last_login_at);
      }
    },
    {
      title: '创建时间',
      key: 'created_at',
      width: 150,
      render(row: UserRecord) {
        return fmtDateTime(row.created_at);
      }
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render(row: UserRecord) {
        return h(
          NSpace,
          { size: 'small' },
          {
            default: () => [
              h(
                NButton,
                { text: true, type: 'primary', size: 'tiny', onClick: () => openEdit(row) },
                { default: () => '编辑' }
              ),
              h(
                NButton,
                {
                  text: true,
                  type: 'error',
                  size: 'tiny',
                  disabled: row.id === 1,
                  onClick: () => handleDelete(row)
                },
                { default: () => '删除' }
              )
            ]
          }
        );
      }
    }
  ];
}

const {
  loading,
  data: users,
  columns,
  columnChecks,
  mobilePagination,
  scrollX,
  getData,
  getDataByPage
} = useNaivePaginatedTable({
  api: () => fetchUserList(searchParams),
  transform: response => defaultTransform(response),
  onPaginationParamsChange: ({ page, pageSize }) => {
    searchParams.current = page || 1;
    searchParams.size = pageSize || 20;
  },
  defaultPageSize: 20,
  paginationProps: { pageSizes: [10, 20, 50, 100] },
  columns: createColumns
});

async function handleSearch() {
  searchParams.username = searchUsername.value.trim() || undefined;
  await getDataByPage(1);
}

async function handleResetSearch() {
  searchUsername.value = '';
  searchParams.username = undefined;
  await getDataByPage(1);
}

/* ---------- 新增/编辑对话框 ---------- */
const modalShow = ref(false);
const modalTitle = ref('新增用户');
const editingId = ref<number | null>(null);
const formData = reactive({
  username: '',
  password: '',
  nickname: '',
  email: '',
  phone: '',
  roles: ['R_USER'] as string[],
  status: 'active'
});
const saving = ref(false);

const roleOptions = [
  { label: '超级管理员', value: 'R_SUPER' },
  { label: '普通用户', value: 'R_USER' }
];

const statusOptions = [
  { label: '启用', value: 'active' },
  { label: '禁用', value: 'disabled' }
];

function openCreate() {
  modalTitle.value = '新增用户';
  editingId.value = null;
  formData.username = '';
  formData.password = '';
  formData.nickname = '';
  formData.email = '';
  formData.phone = '';
  formData.roles = ['R_USER'];
  formData.status = 'active';
  modalShow.value = true;
}

function openEdit(row: UserRecord) {
  modalTitle.value = '编辑用户';
  editingId.value = row.id;
  formData.username = row.username;
  formData.password = '';
  formData.nickname = row.nickname || '';
  formData.email = row.email || '';
  formData.phone = row.phone || '';
  formData.roles = row.roles;
  formData.status = row.status;
  modalShow.value = true;
}

async function handleSave() {
  if (!formData.username) {
    message.error('请输入用户名');
    return;
  }
  if (!editingId.value && !formData.password) {
    message.error('请输入密码');
    return;
  }

  saving.value = true;
  try {
    if (editingId.value) {
      const { error } = await fetchUpdateUser(editingId.value, formData);
      if (!error) {
        message.success('更新成功');
        modalShow.value = false;
        getData();
      }
    } else {
      const { error } = await fetchCreateUser(formData);
      if (!error) {
        message.success('创建成功');
        modalShow.value = false;
        getData();
      }
    }
  } catch {
    message.error('操作失败');
  } finally {
    saving.value = false;
  }
}

function handleDelete(row: UserRecord) {
  dialog.warning({
    title: '确认删除',
    content: `确定要删除用户 "${row.username}" 吗？`,
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const { error } = await fetchDeleteUser(row.id);
        if (!error) {
          message.success('删除成功');
          getData();
        }
      } catch {
        message.error('删除失败');
      }
    }
  });
}
</script>

<template>
  <NCard :bordered="false" class="card-wrapper h-full" title="用户管理">
    <div class="mb-16px flex flex-wrap items-center justify-between gap-12px">
      <NSpace align="center" wrap>
        <NInput
          v-model:value="searchUsername"
          placeholder="搜索用户名"
          clearable
          class="w-200px lt-sm:w-160px"
          @keyup.enter="handleSearch"
        />
        <NButton type="primary" @click="handleSearch">搜索</NButton>
        <NButton @click="handleResetSearch">重置</NButton>
      </NSpace>
      <TableHeaderOperation v-model:columns="columnChecks" :loading="loading" @refresh="getData">
        <template #default>
          <NButton type="primary" size="small" @click="openCreate">
            <template #icon><SvgIcon icon="mdi:account-plus-outline" /></template>
            新增用户
          </NButton>
        </template>
      </TableHeaderOperation>
    </div>

    <NDataTable
      :loading="loading"
      :columns="columns"
      :data="users"
      :pagination="mobilePagination"
      :row-key="(row: UserRecord) => row.id"
      :scroll-x="scrollX"
      remote
      size="small"
      striped
      :bordered="false"
      class="min-h-0"
    />

    <!-- 新增/编辑对话框 -->
    <NModal
      v-model:show="modalShow"
      :title="modalTitle"
      :mask-closable="false"
      preset="card"
      class="w-520px max-w-[calc(100vw-32px)]"
    >
      <NForm label-placement="left" label-width="80px">
        <NFormItem label="用户名" required>
          <NInput v-model:value="formData.username" placeholder="请输入用户名" />
        </NFormItem>
        <NFormItem :label="editingId ? '新密码' : '密码'" :required="!editingId">
          <NInput
            v-model:value="formData.password"
            type="password"
            show-password-on="click"
            :placeholder="editingId ? '留空则不修改' : '请输入密码'"
          />
        </NFormItem>
        <NFormItem label="昵称">
          <NInput v-model:value="formData.nickname" placeholder="请输入昵称" />
        </NFormItem>
        <NFormItem label="邮箱">
          <NInput v-model:value="formData.email" placeholder="请输入邮箱" />
        </NFormItem>
        <NFormItem label="手机号">
          <NInput v-model:value="formData.phone" placeholder="请输入手机号" />
        </NFormItem>
        <NFormItem label="角色">
          <NSelect v-model:value="formData.roles" :options="roleOptions" multiple />
        </NFormItem>
        <NFormItem label="状态">
          <NSelect v-model:value="formData.status" :options="statusOptions" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="modalShow = false">取消</NButton>
          <NButton type="primary" :loading="saving" @click="handleSave">保存</NButton>
        </NSpace>
      </template>
    </NModal>
  </NCard>
</template>
