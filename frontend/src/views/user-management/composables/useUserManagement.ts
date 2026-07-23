/**
 * 用户管理 — 状态与操作管理
 *
 * 职责：管理表格配置、搜索、CRUD 状态、表单验证规则。
 * index.vue 只负责组合子组件。
 */
import { h, reactive, ref } from 'vue';
import { NButton, NTag, NSpace, NPopconfirm, useMessage } from 'naive-ui';
import { fetchUserList, fetchCreateUser, fetchUpdateUser, fetchDeleteUser, type UserRecord } from '@/service/api/user';
import { defaultTransform, useNaivePaginatedTable } from '@/hooks/common/table';
import { getServiceErrorMessage } from '@/utils/service';

export function useUserManagement() {
  const message = useMessage();

  /* ===== 搜索 ===== */
  const searchUsername = ref('');
  const searchParams = reactive({ current: 1, size: 20, username: undefined as string | undefined });
  const tableError = ref('');

  /* ===== 表格列定义 ===== */

  /** 格式化日期时间为 YYYY-MM-DD HH:mm */
  function fmtDateTime(val: string | null): string {
    if (!val) return '-';
    const d = new Date(val);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  /** 创建表格列定义（包含 NPopconfirm 删除确认） */
  function createColumns(
    onEdit: (row: UserRecord) => void,
    onDelete: (row: UserRecord) => Promise<void>
  ): NaiveUI.TableColumn<UserRecord>[] {
    return [
      { title: 'ID', key: 'id', width: 60, fixed: 'left' as const },
      { title: '用户名', key: 'username', width: 120, fixed: 'left' as const },
      {
        title: '昵称', key: 'nickname', width: 100,
        render(row: UserRecord) { return row.nickname || '-'; }
      },
      {
        title: '邮箱', key: 'email', width: 160, ellipsis: { tooltip: true },
        render(row: UserRecord) { return row.email || '-'; }
      },
      {
        title: '角色', key: 'roles', width: 140,
        render(row: UserRecord) {
          if (!row.roles || row.roles.length === 0) return '-';
          return row.roles.map(role =>
            h(NTag, { type: role === 'R_SUPER' ? 'primary' : 'default', size: 'small', round: true }, {
              default: () => role === 'R_SUPER' ? '超级管理员' : '普通用户'
            })
          );
        }
      },
      {
        title: '状态', key: 'status', width: 80,
        render(row: UserRecord) {
          const type = row.status === 'active' ? 'success' : 'error';
          const label = row.status === 'active' ? '启用' : '禁用';
          return h(NTag, { type, size: 'small', round: true }, { default: () => label });
        }
      },
      {
        title: '最后登录', key: 'last_login_at', width: 150,
        render(row: UserRecord) { return fmtDateTime(row.last_login_at); }
      },
      {
        title: '创建时间', key: 'created_at', width: 150,
        render(row: UserRecord) { return fmtDateTime(row.created_at); }
      },
      {
        title: '操作', key: 'actions', width: 140, fixed: 'right' as const,
        render(row: UserRecord) {
          return h(NSpace, { size: 'small' }, {
            default: () => [
              h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => onEdit(row) }, { default: () => '编辑' }),
              // 使用 NPopconfirm 替代 dialog.warning()——内联确认，体验更好
              h(
                NPopconfirm,
                { onPositiveClick: () => onDelete(row) },
                {
                  trigger: () =>
                    h(NButton, { text: true, type: 'error', size: 'tiny', disabled: row.id === 1 }, { default: () => '删除' }),
                  default: () => `确定要删除用户 "${row.username}" 吗？`
                }
              )
            ]
          });
        }
      }
    ];
  }

  /* ===== 表格列（独立 ref，通过 setColumns 设置） ===== */

  /** 实际的表格列（包含操作按钮，需要 onEdit/onDelete 回调） */
  const tableColumns = ref<NaiveUI.TableColumn<UserRecord>[]>([]);

  /* ===== 表格钩子（columns 传一个空函数，列通过 tableColumns ref 管理） ===== */

  const {
    loading,
    data: users,
    columnChecks,
    mobilePagination,
    scrollX,
    getData,
    getDataByPage
  } = useNaivePaginatedTable({
    api: () => fetchUserList(searchParams),
    transform: response => {
      tableError.value = response.error ? getServiceErrorMessage(response.error, '用户列表读取失败') : '';
      return defaultTransform(response);
    },
    onPaginationParamsChange: ({ page, pageSize }) => {
      searchParams.current = page || 1;
      searchParams.size = pageSize || 20;
    },
    defaultPageSize: 20,
    paginationProps: { pageSizes: [10, 20, 50, 100] },
    columns: () => tableColumns.value as any
  });

  /** 设置表格列（在 index.vue 中调用，传入 CRUD 回调） */
  function setColumns(onEdit: (row: UserRecord) => void, onDelete: (row: UserRecord) => Promise<void>) {
    tableColumns.value = createColumns(onEdit, onDelete);
  }

  /* ===== 搜索 ===== */

  async function handleSearch() {
    searchParams.username = searchUsername.value.trim() || undefined;
    await getDataByPage(1);
  }

  async function handleResetSearch() {
    searchUsername.value = '';
    searchParams.username = undefined;
    await getDataByPage(1);
  }

  /* ===== 新增/编辑抽屉状态 ===== */

  type OperateType = 'add' | 'edit';

  const drawerVisible = ref(false);
  const operateType = ref<OperateType>('add');
  const editingId = ref<number | null>(null);

  /** 表单数据 */
  const formData = reactive({
    username: '',
    password: '',
    nickname: '',
    email: '',
    phone: '',
    roles: ['R_USER'] as string[],
    status: 'active' as string
  });

  /** 表单验证规则（用 NForm :rules 替代手动 if 检查） */
  const formRules = {
    username: [
      { required: true, message: '请输入用户名', trigger: 'blur' }
    ],
    password: [
      { required: true, message: '请输入密码', trigger: 'blur' }
    ]
  };

  const roleOptions = [
    { label: '超级管理员', value: 'R_SUPER' },
    { label: '普通用户', value: 'R_USER' }
  ];

  const statusOptions = [
    { label: '启用', value: 'active' },
    { label: '禁用', value: 'disabled' }
  ];

  const saving = ref(false);

  /** 接收编辑抽屉的字段更新，所有表单状态只由这一层维护。 */
  function updateFormField(field: keyof typeof formData, value: string | string[]) {
    if (field === 'roles') {
      formData.roles = Array.isArray(value) ? value : [value];
      return;
    }
    formData[field] = Array.isArray(value) ? (value[0] || '') : value;
  }

  function openCreate() {
    operateType.value = 'add';
    editingId.value = null;
    formData.username = '';
    formData.password = '';
    formData.nickname = '';
    formData.email = '';
    formData.phone = '';
    formData.roles = ['R_USER'];
    formData.status = 'active';
    drawerVisible.value = true;
  }

  function openEdit(row: UserRecord) {
    operateType.value = 'edit';
    editingId.value = row.id;
    formData.username = row.username;
    formData.password = '';
    formData.nickname = row.nickname || '';
    formData.email = row.email || '';
    formData.phone = row.phone || '';
    formData.roles = row.roles;
    formData.status = row.status;
    drawerVisible.value = true;
  }

  async function handleSave() {
    formData.username = formData.username.trim();
    if (!formData.username) {
      message.error('请输入用户名');
      return;
    }
    if (operateType.value === 'add' && !formData.password) {
      message.error('请输入密码');
      return;
    }

    saving.value = true;
    try {
      if (operateType.value === 'edit' && editingId.value) {
        const { error } = await fetchUpdateUser(editingId.value, formData);
        if (!error) {
          message.success('更新成功');
          drawerVisible.value = false;
          getData();
        } else {
          message.error(getServiceErrorMessage(error, '更新用户失败'));
        }
      } else {
        const { error } = await fetchCreateUser(formData);
        if (!error) {
          message.success('创建成功');
          drawerVisible.value = false;
          getData();
        } else {
          message.error(getServiceErrorMessage(error, '创建用户失败'));
        }
      }
    } catch {
      message.error('操作失败');
    } finally {
      saving.value = false;
    }
  }

  async function handleDelete(row: UserRecord) {
    try {
      const { error } = await fetchDeleteUser(row.id);
      if (!error) {
        message.success('删除成功');
        getData();
      } else {
        message.error(getServiceErrorMessage(error, '删除失败'));
      }
    } catch {
      message.error('删除失败');
    }
  }

  return {
    // 状态
    searchUsername,
    tableError,
    loading,
    users,
    tableColumns,
    columnChecks,
    mobilePagination,
    scrollX,
    drawerVisible,
    operateType,
    editingId,
    formData,
    formRules,
    roleOptions,
    statusOptions,
    saving,
    // 方法
    getData,
    handleSearch,
    handleResetSearch,
    openCreate,
    openEdit,
    handleSave,
    handleDelete,
    updateFormField,
    setColumns
  };
}
