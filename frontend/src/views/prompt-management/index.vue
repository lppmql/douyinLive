<script setup lang="ts">
import { h, onMounted, ref, computed } from 'vue';
import {
  NButton, NCard, NSpace, NDataTable, NTag,
  NDrawer, NDrawerContent, NInput, NForm, NFormItem,
  NSelect, NPopconfirm, NAlert, NEmpty, NModal,
  useMessage, NSplit, NScrollbar, NSpin, NTag as NTag2,
} from 'naive-ui';
import {
  fetchActivePrompts, fetchPrompts, updatePrompt, deletePrompt,
} from '@/service/api/douyin';
import { unwrapServiceData, getServiceErrorMessage } from '@/utils/service';

defineOptions({ name: 'PromptManagement' });

const ms = useMessage();
const REQ = ((window as any).__soybean_request__) || ((url: string, opts: any) => fetch(url, opts).then(r => r.json()));

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
const editDrawerOpen = ref(false);
const editForm = ref({ type: 'speech_score', name: '', content: '', description: '' });
const editId = ref<number | null>(null);
const versionHistory = ref<Api.Douyin.PromptTemplate[]>([]);
const saving = ref(false);
const tableError = ref('');
/** 测试弹窗 */
const testModalOpen = ref(false);
const testResult = ref('');
const testLoading = ref(false);
const testError = ref('');
/** 选中的用于 diff 的版本 */
const diffVersion = ref<Api.Douyin.PromptTemplate | null>(null);

/* ===== 加载数据 ===== */
async function getData() {
  loading.value = true;
  tableError.value = '';
  try {
    const result = await fetchActivePrompts();
    prompts.value = unwrapServiceData(result, '加载失败');
  } catch (err: unknown) {
    tableError.value = getServiceErrorMessage(err, '加载失败');
  } finally {
    loading.value = false;
  }
}

/* ===== 提取变量占位符 ===== */
const extractedVars = computed(() => {
  const matches = editForm.value.content.match(/\{[a-zA-Z_][a-zA-Z0-9_]*\}/g);
  if (!matches) return [];
  return [...new Set(matches)].sort();
});

/* ===== 行号 + 字符数 ===== */
const lineCount = computed(() => editForm.value.content.split('\n').length);
const charCount = computed(() => editForm.value.content.length);

/* ===== 简单行级 diff ===== */
function computeDiff(oldText: string, newText: string) {
  const oldLines = oldText.split('\n');
  const newLines = newText.split('\n');
  const result: { line: string; type: 'same' | 'added' | 'removed'; idx: number }[] = [];
  const maxLen = Math.max(oldLines.length, newLines.length);
  for (let i = 0; i < maxLen; i++) {
    if (i >= oldLines.length) {
      result.push({ line: newLines[i], type: 'added', idx: i + 1 });
    } else if (i >= newLines.length) {
      result.push({ line: oldLines[i], type: 'removed', idx: i + 1 });
    } else if (oldLines[i] === newLines[i]) {
      result.push({ line: oldLines[i], type: 'same', idx: i + 1 });
    } else {
      result.push({ line: oldLines[i], type: 'removed', idx: i + 1 });
      result.push({ line: newLines[i], type: 'added', idx: i + 1 });
    }
  }
  return result;
}

const diffLines = computed(() => {
  if (!diffVersion.value) return [];
  return computeDiff(diffVersion.value.content, editForm.value.content);
});

/* ===== 编辑 ===== */
async function openEdit(row: Api.Douyin.PromptTemplate) {
  editId.value = row.id;
  editForm.value = { type: row.type, name: row.name || '', content: row.content, description: row.description || '' };
  diffVersion.value = null;
  try {
    const result = await fetchPrompts(row.type);
    const all = unwrapServiceData(result, '获取历史版本失败');
    versionHistory.value = [...all].sort((a, b) => b.version - a.version);
  } catch { versionHistory.value = []; }
  editDrawerOpen.value = true;
}

function restoreVersion(v: Api.Douyin.PromptTemplate) {
  editForm.value.content = v.content;
  editForm.value.name = v.name || '';
  editForm.value.description = v.description || '';
  diffVersion.value = null;
  ms.success(`已恢复 v${v.version} 的内容`);
}

function showDiff(v: Api.Douyin.PromptTemplate) {
  diffVersion.value = diffVersion.value?.id === v.id ? null : v;
}

/* ===== 保存 ===== */
async function handleSave() {
  if (!editForm.value.content.trim()) { ms.warning('内容不能为空'); return; }
  saving.value = true;
  try {
    const result = await updatePrompt(editId.value!, editForm.value);
    const updated = unwrapServiceData(result, '保存失败');
    ms.success(`已创建 v${updated.version}`);
    editDrawerOpen.value = false;
    getData();
  } catch (err: unknown) {
    ms.error(getServiceErrorMessage(err, '保存失败'));
  } finally { saving.value = false; }
}

/* ===== 删除 ===== */
async function handleDelete(id: number) {
  try { await deletePrompt(id); ms.success('已删除'); getData(); }
  catch (err: unknown) { ms.error(getServiceErrorMessage(err, '删除失败')); }
}

/* ===== 测试 ===== */
async function handleTest() {
  testLoading.value = true;
  testResult.value = '';
  testError.value = '';
  testModalOpen.value = true;
  try {
    const resp = await fetch('/api/v1/ai/prompts/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: editForm.value.type, content: editForm.value.content }),
    });
    const data = await resp.json();
    if (data.error) { testError.value = data.error; return; }
    testResult.value = JSON.stringify(data.result || data, null, 2);
  } catch (err: any) {
    testError.value = err.message || '测试请求失败';
  } finally { testLoading.value = false; }
}

/* ===== 表格列 ===== */
const columns = [
  { title: '类型', key: 'type', width: 180,
    render: (row: Api.Douyin.PromptTemplate) => h(NTag, { size: 'small', type: 'primary' }, { default: () => TYPE_OPTIONS.find(t => t.value === row.type)?.label || row.type }),
  },
  { title: '名称', key: 'name', width: 200, render: (row: Api.Douyin.PromptTemplate) => row.name || '-' },
  { title: '版本', key: 'version', width: 80, render: (row: Api.Douyin.PromptTemplate) => h(NTag, { size: 'small', type: 'info' }, { default: () => `v${row.version}` }) },
  { title: '用途说明', key: 'description', minWidth: 180, render: (row: Api.Douyin.PromptTemplate) => row.description || '-' },
  { title: '内容预览', key: 'content', minWidth: 240, ellipsis: { tooltip: true }, render: (row: Api.Douyin.PromptTemplate) => row.content.length > 100 ? row.content.slice(0, 100) + '...' : row.content },
  { title: '最后更新', key: 'created_at', width: 170, render: (row: Api.Douyin.PromptTemplate) => row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-' },
  { title: '操作', key: 'actions', width: 120, fixed: 'right' as const, render: (row: Api.Douyin.PromptTemplate) => [
    h(NButton, { size: 'small', type: 'primary', secondary: true, onClick: () => openEdit(row) }, { default: () => '编辑' }),
    h(NPopconfirm, { onPositiveClick: () => handleDelete(row.id), positiveButtonProps: { type: 'error' } }, {
      default: () => '确认删除该版本？',
      trigger: () => h(NButton, { size: 'small', type: 'error', secondary: true, style: 'margin-left: 8px' }, { default: () => '删除' }),
    }),
  ]},
];

onMounted(getData);
</script>

<template>
  <NSpace vertical :size="16" class="business-page">
    <NCard :bordered="false" class="card-wrapper h-full" title="Prompt 管理（项目生效提示词）">
      <NAlert v-if="tableError" class="mb-16px" type="error" :bordered="false" show-icon>
        {{ tableError }}
        <NButton size="small" secondary @click="getData">重新加载</NButton>
      </NAlert>
      <div class="business-toolbar mb-16px">
        <div class="business-toolbar__info">
          <NTag type="success" round size="small">6 种提示词类型</NTag>
          <span style="margin-left: 8px; font-size: 13px; color: #999;">编辑自动创建新版本</span>
        </div>
      </div>
      <div class="business-table-shell">
        <NDataTable
          :loading="loading" :columns="columns" :data="prompts"
          :row-key="(row: Api.Douyin.PromptTemplate) => row.id"
          :scroll-x="1100" :max-height="520" size="small" striped :bordered="false" class="min-h-0"
        />
        <NEmpty v-if="!loading && prompts.length === 0" description="暂无生效提示词" class="py-40px" />
      </div>
    </NCard>

    <!-- 编辑抽屉 -->
    <NDrawer v-model:show="editDrawerOpen" :width="780" placement="right">
      <NDrawerContent title="编辑提示词（自动创建新版本）" :native-scrollbar="false">
        <NForm label-placement="top" label-width="auto">
          <NFormItem label="类型">
            <NSelect v-model:value="editForm.type" :options="TYPE_OPTIONS" disabled />
          </NFormItem>
          <NFormItem label="名称">
            <NInput v-model:value="editForm.name" placeholder="提示词名称" />
          </NFormItem>
          <NFormItem label="用途说明">
            <NInput v-model:value="editForm.description" placeholder="简短说明用途" />
          </NFormItem>

          <!-- 代码编辑器（方案 A3） -->
          <NFormItem label="提示词内容">
            <div class="code-editor-wrapper">
              <div class="code-editor-gutter">
                <div v-for="n in lineCount" :key="n" class="code-editor-line-number">{{ n }}</div>
              </div>
              <textarea
                v-model="editForm.content"
                class="code-editor-textarea"
                placeholder="输入提示词模板内容，使用 {变量名} 作为占位符"
                spellcheck="false"
              />
            </div>
            <div class="code-editor-footer">
              <span>{{ lineCount }} 行 · {{ charCount }} 字符</span>
              <!-- 变量占位符检测（方案 B1） -->
              <span v-if="extractedVars.length" class="code-editor-vars">
                <NTag v-for="v in extractedVars" :key="v" size="tiny" type="warning" style="margin-left: 4px;">{{ v }}</NTag>
              </span>
              <span v-else style="margin-left: 12px; color: #999; font-size: 12px;">未检测到变量占位符</span>
            </div>
          </NFormItem>

          <!-- 测试运行按钮（方案 C） -->
          <NFormItem label="运行测试">
            <NSpace>
              <NButton size="small" type="info" secondary :loading="testLoading" @click="handleTest">
                <template #icon><SvgIcon icon="mdi:play" /></template>
                使用最近场次真实数据测试
              </NButton>
              <span style="font-size: 12px; color: #999;">调用 DeepSeek 查看提示词效果</span>
            </NSpace>
          </NFormItem>
        </NForm>

        <!-- 版本历史 + diff（方案 A1+A2） -->
        <template #footer>
          <details v-if="versionHistory.length" style="margin-top: 12px;">
            <summary style="cursor: pointer; font-weight: 600; font-size: 14px; margin-bottom: 8px;">
              版本历史（{{ versionHistory.length }}）
            </summary>
            <NScrollbar style="max-height: 300px;">
              <div v-for="v in versionHistory" :key="v.id"
                class="version-item"
                :class="{ 'version-item--selected': diffVersion?.id === v.id }">
                <div class="version-item__header">
                  <NTag size="small" type="info">v{{ v.version }}</NTag>
                  <span style="margin-left: 8px; font-weight: 500;">{{ v.name || v.type }}</span>
                  <span style="margin-left: 12px; color: #999; font-size: 12px;">
                    {{ v.created_at ? new Date(v.created_at).toLocaleString('zh-CN') : '' }}
                  </span>
                </div>
                <div style="white-space: pre-wrap; font-size: 12px; max-height: 60px; overflow: hidden; color: #666; margin-top: 4px;">
                  {{ v.content.slice(0, 120) }}{{ v.content.length > 120 ? '...' : '' }}
                </div>
                <div class="version-item__actions">
                  <NButton size="tiny" type="primary" quaternary @click="restoreVersion(v)">恢复此版本</NButton>
                  <NButton size="tiny" type="warning" quaternary style="margin-left: 4px;" @click="showDiff(v)">
                    {{ diffVersion?.id === v.id ? '关闭对比' : '对比当前' }}
                  </NButton>
                </div>
                <!-- diff 视图 -->
                <div v-if="diffVersion?.id === v.id" class="diff-view">
                  <div v-for="dl in diffLines" :key="dl.idx + dl.type"
                    class="diff-line"
                    :class="'diff-line--' + dl.type">
                    <span class="diff-line-num">{{ dl.idx }}</span>
                    <span class="diff-line-sign">{{ dl.type === 'added' ? '+' : dl.type === 'removed' ? '-' : ' ' }}</span>
                    <span class="diff-line-text">{{ dl.line }}</span>
                  </div>
                </div>
              </div>
            </NScrollbar>
          </details>

          <NSpace justify="end" style="margin-top: 16px;">
            <NButton @click="editDrawerOpen = false">取消</NButton>
            <NButton type="primary" :loading="saving" @click="handleSave">保存为新版本</NButton>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>

    <!-- 测试结果弹窗 -->
    <NModal v-model:show="testModalOpen" title="测试结果" :mask-closable="false" preset="card" style="width: 700px;">
      <NSpin :show="testLoading">
        <div v-if="testError" style="color: #e74c3c; white-space: pre-wrap;">{{ testError }}</div>
        <pre v-else style="max-height: 500px; overflow: auto; background: #f5f5f5; padding: 12px; border-radius: 6px; font-size: 12px; white-space: pre-wrap;">{{ testResult }}</pre>
      </NSpin>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="testModalOpen = false">关闭</NButton>
        </NSpace>
      </template>
    </NModal>
  </NSpace>
</template>

<style scoped>
.business-page { height: 100%; }
.card-wrapper { height: 100%; }
.business-toolbar { display: flex; justify-content: space-between; align-items: center; }
.business-toolbar__info { display: flex; align-items: center; }
.business-table-shell { flex: 1; min-height: 0; overflow: auto; }

/* 代码编辑器 */
.code-editor-wrapper {
  display: flex;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  overflow: hidden;
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 13px;
  line-height: 1.6;
  min-height: 200px;
}
.code-editor-gutter {
  width: 40px;
  background: #f8f8f8;
  border-right: 1px solid #e8e8e8;
  text-align: right;
  padding: 8px 6px;
  user-select: none;
  color: #999;
  font-size: 12px;
  overflow: hidden;
}
.code-editor-line-number {
  line-height: 1.6;
  height: 1.6em;
}
.code-editor-textarea {
  flex: 1;
  border: none;
  outline: none;
  padding: 8px 12px;
  resize: vertical;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  tab-size: 2;
  background: #fff;
  min-height: 200px;
}
.code-editor-textarea:focus { background: #fafafa; }
.code-editor-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: #999;
}
.code-editor-vars { display: flex; flex-wrap: wrap; gap: 2px; }

/* 版本历史 */
.version-item {
  padding: 8px 12px;
  margin-bottom: 6px;
  border-radius: 6px;
  border: 1px solid #eee;
  background: #fafafa;
  transition: all 0.15s;
}
.version-item--selected { border-color: #2080f0; background: #f0f7ff; }
.version-item__header { display: flex; align-items: center; flex-wrap: wrap; }
.version-item__actions { margin-top: 6px; }

/* diff */
.diff-view {
  margin-top: 8px;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.5;
  max-height: 300px;
  overflow: auto;
}
.diff-line { display: flex; padding: 1px 8px; }
.diff-line--added { background: #e6ffed; }
.diff-line--removed { background: #ffeef0; }
.diff-line--same { background: #fff; }
.diff-line-num { width: 30px; color: #999; text-align: right; margin-right: 8px; flex-shrink: 0; }
.diff-line-sign { width: 14px; flex-shrink: 0; font-weight: bold; }
.diff-line--added .diff-line-sign { color: #28a745; }
.diff-line--removed .diff-line-sign { color: #d73a49; }
.diff-line-text { flex: 1; white-space: pre-wrap; }
</style>
