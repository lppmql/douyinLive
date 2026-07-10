<script setup lang="ts">
import { h, onMounted, reactive, ref } from 'vue';
import { NButton, NTag, NDataTable, NModal, NForm, NFormItem, NInput, NSelect, NSpace, useMessage, useDialog } from 'naive-ui';
import { $t } from '@/locales';
import { fetchUserList, fetchCreateUser, fetchUpdateUser, fetchDeleteUser, type UserRecord, type UserPageResult } from '@/service/api/user';

defineOptions({ name: 'UserManagement' });

const message = useMessage();
const dialog = useDialog();

/* ---------- 表格状态 ---------- */
const loading = ref(false);
const users = ref<UserRecord[]>([]);
const pagination = reactive({
  page: 1,
  pageSize: 20,
  itemCount: 0,
  pageSizes: [10, 20, 50, 100],
  showSizePicker: true,
  prefix({ itemCount }: { itemCount: number | undefined }) {
    return `共 ${itemCount ?? 0} 条`;
  },
  onChange(page: number) {
    pagination.page = page;
    loadUsers();
  },
  onUpdatePageSize(pageSize: number) {
    pagination.pageSize = pageSize;
    pagination.page = 1;
    loadUsers();
  }
});

/* ---------- 搜索 ---------- */
const searchUsername = ref('');

function loadUsers() {
  loading.value = true;
  fetchUserList({
    current: pagination.page,
    size: pagination.pageSize,
    username: searchUsername.value || undefined
  }).then(({ data, error }) => {
    if (!error && data) {
      users.value = data.records;
      pagination.itemCount = data.total;
      pagination.page = data.current;
    }
  }).catch(() => {
    message.error('加载用户列表失败');
  }).finally(() => {
    loading.value = false;
  });
}

/* ---------- 表格列 ---------- */
function renderRoles(roles: string[]) {
  if (!roles || roles.length === 0) return '-';
  return roles.map(role => {
    const type = role === 'R_SUPER' ? 'primary' : 'default';
    return h(NTag, { type, size: 'small', round: true }, { default: () => role === 'R_SUPER' ? '超级管理员' : '普通用户' });
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

const columns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '用户名', key: 'username', width: 100 },
  { title: '昵称', key: 'nickname', width: 100, render(row: UserRecord) { return row.nickname || '-'; } },
  { title: '邮箱', key: 'email', width: 160, ellipsis: { tooltip: true }, render(row: UserRecord) { return row.email || '-'; } },
  { title: '角色', key: 'roles', width: 140, render(row: UserRecord) { return renderRoles(row.roles); } },
  { title: '状态', key: 'status', width: 80, render(row: UserRecord) { return renderStatus(row.status); } },
  { title: '最后登录', key: 'last_login_at', width: 150, render(row: UserRecord) { return fmtDateTime(row.last_login_at); } },
  { title: '创建时间', key: 'created_at', width: 150, render(row: UserRecord) { return fmtDateTime(row.created_at); } },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    render(row: UserRecord) {
      return h(NSpace, { size: 'small' }, {
        default: () => [
          h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => openEdit(row) }, { default: () => '编辑' }),
          h(NButton, {
            text: true,
            type: 'error',
            size: 'tiny',
            disabled: row.id === 1,
            onClick: () => handleDelete(row)
          }, { default: () => '删除' })
        ]
      });
    }
  }
];

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
        loadUsers();
      }
    } else {
      const { error } = await fetchCreateUser(formData);
      if (!error) {
        message.success('创建成功');
        modalShow.value = false;
        loadUsers();
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
          loadUsers();
        }
      } catch {
        message.error('删除失败');
      }
    }
  });
}

onMounted(() => {
  loadUsers();
});
</script>

<template>
  <div class="h-full flex-col overflow-auto p-16px">
    <!-- 顶部操作栏 -->
    <div class="mb-16px flex items-center justify-between">
      <NSpace align="center">
        <NInput
          v-model:value="searchUsername"
          placeholder="搜索用户名"
          clearable
          style="width: 200px"
          @keyup.enter="loadUsers"
        />
        <NButton type="primary" @click="loadUsers">搜索</NButton>
      </NSpace>
      <NButton type="primary" @click="openCreate">新增用户</NButton>
    </div>

    <!-- 表格 -->
    <NDataTable
      :loading="loading"
      :columns="columns"
      :data="users"
      :pagination="pagination"
      :row-key="(row: UserRecord) => row.id"
      size="small"
      striped
      bordered
      :scroll-x="1000"
      class="flex-1"
    />

    <!-- 新增/编辑对话框 -->
    <NModal
      v-model:show="modalShow"
      :title="modalTitle"
      :mask-closable="false"
      preset="card"
      style="width: 500px"
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
  </div>
</template>
