<script setup lang="ts">
import { h, onMounted, ref } from 'vue';
import {
  NButton, NCard, NSpace, NDataTable, NTag,
  NDrawer, NDrawerContent, NInput, NForm, NFormItem,
  NSelect, NPopconfirm, NAlert, NEmpty,
  useMessage,
} from 'naive-ui';
import { fetchPrompts, createPrompt, updatePrompt, deletePrompt } from '@/service/api/douyin';
import { unwrapServiceData, getServiceErrorMessage } from '@/utils/service';
import TableHeaderOperation from '@/components/advanced/table-header-operation.vue';

defineOptions({ name: 'PromptManagement' });

const ms = useMessage();

/** 提示词类型选项 */
const TYPE_OPTIONS = [
  { label: '话术评分 (speech_score)', value: 'speech_score' },
  { label: '趋势分析 (trend_analysis)', value: 'trend_analysis' },
  { label: '异常检测 (anomaly_detection)', value: 'anomaly_detection' },
  { label: '优化建议 (optimization)', value: 'optimization' },
  { label: '意向识别 (high_intent)', value: 'high_intent' },
  { label: '知识问答 (qa)', value: 'qa' },
];

/* ===== 数据状态 ===== */
const loading = ref(false);
const prompts = ref<Api.Douyin.PromptTemplate[]>([]);
const searchType = ref<string | null>(null);
const editDrawerOpen = ref(false);
const editMode = ref<'create' | 'edit'>('create');
const editForm = ref({ type: 'speech_score', name: '', content: '', description: '' });
const editId = ref<number | null>(null);
const versionHistory = ref<Api.Douyin.PromptTemplate[]>([]);
const saving = ref(false);
const tableError = ref('');

/* ===== 获取数据 ===== */
async function getData() {
  loading.value = true;
  tableError.value = '';
  try {
    const result = await fetchPrompts(searchType.value ?? undefined);
    prompts.value = unwrapServiceData(result, '加载提示词列表失败');
  } catch (err: unknown) {
    tableError.value = getServiceErrorMessage(err, '加载失败');
  } finally {
    loading.value = false;
  }
}

function handleSearch() { getData(); }
function handleReset() {
  searchType.value = null;
  getData();
}

/* ===== 打开新建抽屉 ===== */
function openCreate() {
  editMode.value = 'create';
  editId.value = null;
  editForm.value = { type: 'speech_score', name: '', content: '', description: '' };
  versionHistory.value = [];
  editDrawerOpen.value = true;
}

/* ===== 打开编辑抽屉 ===== */
async function openEdit(row: Api.Douyin.PromptTemplate) {
  editMode.value = 'edit';
  editId.value = row.id;
  editForm.value = {
    type: row.type,
    name: row.name || '',
    content: row.content,
    description: row.description || '',
  };
  try {
    const result = await fetchPrompts(row.type);
    const all = unwrapServiceData(result, '获取历史版本失败');
    versionHistory.value = [...all].sort((a, b) => b.version - a.version);
  } catch {
    versionHistory.value = [];
  }
  editDrawerOpen.value = true;
}

/* ===== 保存 ===== */
async function handleSave() {
  if (!editForm.value.content.trim()) {
    ms.warning('提示词内容不能为空');
    return;
  }
  saving.value = true;
  try {
    if (editMode.value === 'create') {
      const result = await createPrompt(editForm.value);
      const created = unwrapServiceData(result, '创建失败');
      ms.success(`已创建版本 v${created.version}`);
    } else {
      const result = await updatePrompt(editId.value!, editForm.value);
      const updated = unwrapServiceData(result, '保存失败');
      ms.success(`已创建新版本 v${updated.version}，旧版本保留在历史中`);
    }
    editDrawerOpen.value = false;
    getData();
  } catch (err: unknown) {
    ms.error(getServiceErrorMessage(err, '保存失败'));
  } finally {
    saving.value = false;
  }
}

/* ===== 删除 ===== */
async function handleDelete(id: number) {
  try {
    await deletePrompt(id);
    ms.success('删除成功');
    getData();
  } catch (err: unknown) {
    ms.error(getServiceErrorMessage(err, '删除失败'));
  }
}

/* ===== 表格列定义 ===== */
const columns = [
  { title: 'ID', key: 'id', width: 60 },
  {
    title: '类型', key: 'type', width: 150,
    render: (row: Api.Douyin.PromptTemplate) => {
      const opt = TYPE_OPTIONS.find(t => t.value === row.type);
      return opt?.label || row.type;
    },
  },
  {
    title: '名称', key: 'name', width: 160,
    render: (row: Api.Douyin.PromptTemplate) => row.name || '-',
  },
  {
    title: '版本', key: 'version', width: 70,
    render: (row: Api.Douyin.PromptTemplate) => h(NTag, { size: 'small', type: 'info' }, { default: () => `v${row.version}` }),
  },
  {
    title: '用途说明', key: 'description', minWidth: 160,
    render: (row: Api.Douyin.PromptTemplate) => row.description || '-',
  },
  {
    title: '内容预览', key: 'content', minWidth: 200, ellipsis: { tooltip: true },
    render: (row: Api.Douyin.PromptTemplate) =>
      row.content.length > 80 ? `${row.content.slice(0, 80)}...` : row.content,
  },
  {
    title: '创建时间', key: 'created_at', width: 170,
    render: (row: Api.Douyin.PromptTemplate) =>
      row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-',
  },
  {
    title: '操作', key: 'actions', width: 140, fixed: 'right' as const,
    render: (row: Api.Douyin.PromptTemplate) => [
      h(NButton, { size: 'small', type: 'primary', secondary: true, onClick: () => openEdit(row) }, { default: () => '编辑' }),
      h(NPopconfirm, {
        onPositiveClick: () => handleDelete(row.id),
        positiveButtonProps: { type: 'error' },
      }, {
        default: () => '删除后不可恢复，确认删除？',
        trigger: () => h(NButton, { size: 'small', type: 'error', secondary: true, style: 'margin-left: 8px' }, { default: () => '删除' }),
      }),
    ],
  },
];

onMounted(() => { getData(); });
</script>

<template>
  <NSpace vertical :size="16" class="business-page">
    <NCard :bordered="false" class="card-wrapper h-full" title="Prompt 模板管理">
      <!-- 加载错误 -->
      <NAlert v-if="tableError" class="mb-16px" type="error" :bordered="false" show-icon>
        {{ tableError }}
        <NButton size="small" secondary @click="getData">重新加载</NButton>
      </NAlert>

      <!-- 工具栏 -->
      <div class="business-toolbar mb-16px">
        <div class="business-toolbar__filters">
          <NSelect
            v-model:value="searchType"
            placeholder="按类型筛选"
            clearable
            :options="TYPE_OPTIONS"
            class="w-280px"
            @update:value="handleSearch"
          />
          <NButton @click="handleReset">重置</NButton>
        </div>
        <div class="business-toolbar__actions">
          <NButton type="primary" @click="openCreate">
            <template #icon><SvgIcon icon="mdi:plus" /></template>
            新建提示词
          </NButton>
          <TableHeaderOperation :loading="loading" @refresh="getData">
            <template #default>
              <NTag type="info" round size="small">编辑自动创建新版本，不覆盖旧版</NTag>
            </template>
          </TableHeaderOperation>
        </div>
      </div>

      <!-- 数据表格 -->
      <div class="business-table-shell">
        <NDataTable
          :loading="loading"
          :columns="columns"
          :data="prompts"
          :row-key="(row: Api.Douyin.PromptTemplate) => row.id"
          :scroll-x="1100"
          :max-height="520"
          size="small"
          striped
          :bordered="false"
          class="min-h-0"
        />
        <NEmpty v-if="!loading && prompts.length === 0" description="暂无提示词模板" class="py-40px" />
      </div>
    </NCard>

    <!-- 编辑抽屉 -->
    <NDrawer v-model:show="editDrawerOpen" :width="680" placement="right">
      <NDrawerContent
        :title="editMode === 'create' ? '新建提示词' : '编辑提示词（自动创建新版本）'"
        :native-scrollbar="false"
      >
        <NForm label-placement="top" label-width="auto">
          <NFormItem label="类型">
            <NSelect v-model:value="editForm.type" :options="TYPE_OPTIONS" placeholder="选择提示词类型" />
          </NFormItem>
          <NFormItem label="名称">
            <NInput v-model:value="editForm.name" placeholder="提示词名称（可选）" />
          </NFormItem>
          <NFormItem label="用途说明">
            <NInput v-model:value="editForm.description" placeholder="简短说明该提示词的用途" />
          </NFormItem>
          <NFormItem label="提示词内容">
            <NInput
              v-model:value="editForm.content"
              type="textarea"
              :rows="16"
              placeholder="输入提示词模板内容，使用 {变量名} 作为占位符"
              :autosize="{ minRows: 10, maxRows: 24 }"
            />
          </NFormItem>
        </NForm>

        <!-- 版本历史 -->
        <template v-if="editMode === 'edit' && versionHistory.length > 0" #footer>
          <details style="margin-top: 12px; font-size: 13px;">
            <summary><strong>版本历史（{{ versionHistory.length }} 个版本）</strong></summary>
            <div v-for="v in versionHistory" :key="v.id" style="margin-top: 8px; padding: 8px; background: #f5f5f5; border-radius: 6px;">
              <div>
                <NTag size="small" type="info">v{{ v.version }}</NTag>
                <span style="margin-left: 8px;">{{ v.name || '-' }}</span>
                <span style="margin-left: 12px; color: #999; font-size: 12px;">{{ v.created_at ? new Date(v.created_at).toLocaleString('zh-CN') : '' }}</span>
              </div>
              <div style="margin-top: 4px; font-size: 12px; white-space: pre-wrap; max-height: 80px; overflow-y: auto;">
                {{ v.content.slice(0, 200) }}{{ v.content.length > 200 ? '...' : '' }}
              </div>
            </div>
          </details>
        </template>

        <!-- 底部按钮 -->
        <template #footer>
          <NSpace justify="end">
            <NButton @click="editDrawerOpen = false">取消</NButton>
            <NButton type="primary" :loading="saving" @click="handleSave">
              {{ editMode === 'create' ? '创建' : '保存为新版本' }}
            </NButton>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>
  </NSpace>
</template>

<style scoped>
.business-page { height: 100%; }
.card-wrapper { height: 100%; }
.business-toolbar {
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;
}
.business-toolbar__filters { display: flex; align-items: center; gap: 8px; }
.business-toolbar__actions { display: flex; align-items: center; gap: 8px; }
.business-table-shell { flex: 1; min-height: 0; overflow: auto; }
</style>
