<script setup lang="ts">
import { h, onMounted, ref, computed, nextTick } from 'vue';
import {
  NButton, NCard, NSpace, NDataTable, NTag,
  NDrawer, NDrawerContent, NInput, NForm, NFormItem,
  NSelect, NPopconfirm, NAlert, NEmpty, NModal,
  useMessage, NScrollbar, NSpin, NTag as NTag2, NDivider,
} from 'naive-ui';
import {
  fetchActivePrompts, fetchPrompts, updatePrompt, deletePrompt,
} from '@/service/api/douyin';
import { unwrapServiceData, getServiceErrorMessage } from '@/utils/service';

defineOptions({ name: 'PromptManagement' });

const ms = useMessage();

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
const editVersion = ref(0);
const versionHistory = ref<Api.Douyin.PromptTemplate[]>([]);
const saving = ref(false);
const tableError = ref('');

/* ===== 测试弹窗 ===== */
const testModalOpen = ref(false);
const testResult = ref('');
const testLoading = ref(false);
const testError = ref('');

/* ===== diff 对比弹窗 ===== */
const diffModalOpen = ref(false);
const diffVersion = ref<Api.Douyin.PromptTemplate | null>(null);

/* ===== 文本域 ref（用于光标插入） ===== */
const textareaRef = ref<HTMLTextAreaElement | null>(null);

/* ===== 加载 ===== */
async function getData() {
  loading.value = true;
  tableError.value = '';
  try {
    const result = await fetchActivePrompts();
    prompts.value = unwrapServiceData(result, '加载失败');
  } catch (err: unknown) {
    tableError.value = getServiceErrorMessage(err, '加载失败');
  } finally { loading.value = false; }
}

/* ===== 变量提取 ===== */
const extractedVars = computed(() => {
  const matches = editForm.value.content.match(/\{[a-zA-Z_][a-zA-Z0-9_]*\}/g);
  if (!matches) return [];
  return [...new Set(matches)].sort();
});
const lineCount = computed(() => editForm.value.content.split('\n').length);
const charCount = computed(() => editForm.value.content.length);

/** 点击变量标签 → 插入到光标位置 */
function insertVar(varName: string) {
  const ta = textareaRef.value;
  if (!ta) { editForm.value.content += varName; return; }
  const start = ta.selectionStart;
  const end = ta.selectionEnd;
  const before = editForm.value.content.slice(0, start);
  const after = editForm.value.content.slice(end);
  editForm.value.content = before + varName + after;
  nextTick(() => {
    const pos = start + varName.length;
    ta.setSelectionRange(pos, pos);
    ta.focus();
  });
}

/* ===== diff 计算 ===== */
function computeDiff(oldText: string, newText: string) {
  const oldLines = oldText.split('\n');
  const newLines = newText.split('\n');
  const result: { line: string; type: 'same' | 'added' | 'removed'; idx: number }[] = [];
  const maxLen = Math.max(oldLines.length, newLines.length);
  for (let i = 0; i < maxLen; i++) {
    if (i >= oldLines.length) result.push({ line: newLines[i], type: 'added', idx: i + 1 });
    else if (i >= newLines.length) result.push({ line: oldLines[i], type: 'removed', idx: i + 1 });
    else if (oldLines[i] === newLines[i]) result.push({ line: oldLines[i], type: 'same', idx: i + 1 });
    else {
      result.push({ line: oldLines[i], type: 'removed', idx: i + 1 });
      result.push({ line: newLines[i], type: 'added', idx: i + 1 });
    }
  }
  return result;
}

function openDiff(version: Api.Douyin.PromptTemplate) {
  diffVersion.value = version;
  diffModalOpen.value = true;
}

const diffLines = computed(() => {
  if (!diffVersion.value) return [];
  return computeDiff(diffVersion.value.content, editForm.value.content);
});

/* ===== 编辑 ===== */
async function openEdit(row: Api.Douyin.PromptTemplate) {
  editId.value = row.id;
  editVersion.value = row.version;
  editForm.value = { type: row.type, name: row.name || '', content: row.content, description: row.description || '' };
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
  ms.success(`已恢复 v${v.version} 的内容`);
}

/** 保存并关闭 */
async function handleSave() { await doSave(true); }
/** 保存并继续 */
async function handleSaveContinue() { await doSave(false); }

async function doSave(closeAfterSave: boolean) {
  if (!editForm.value.content.trim()) { ms.warning('内容不能为空'); return; }
  saving.value = true;
  try {
    const result = await updatePrompt(editId.value!, editForm.value);
    const updated = unwrapServiceData(result, '保存失败');
    ms.success(`已创建 v${updated.version}`);
    if (closeAfterSave) { editDrawerOpen.value = false; getData(); }
    else {
      editVersion.value = updated.version;
      // 刷新版本历史
      const r2 = await fetchPrompts(editForm.value.type);
      versionHistory.value = [...unwrapServiceData(r2, '')].sort((a, b) => b.version - a.version);
    }
  } catch (err: unknown) {
    ms.error(getServiceErrorMessage(err, '保存失败'));
  } finally { saving.value = false; }
}

/* ===== 删除 ===== */
async function handleDelete(id: number) {
  try { await deletePrompt(id); ms.success('已删除'); getData(); }
  catch (err: unknown) { ms.error(getServiceErrorMessage(err, '删除失败')); }
}

/* ===== Ctrl+S 快捷键 ===== */
function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's' && editDrawerOpen.value) {
    e.preventDefault();
    handleSave();
  }
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
  } catch (err: any) { testError.value = err.message || '测试请求失败'; }
  finally { testLoading.value = false; }
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
  <NSpace vertical :size="16" class="business-page" @keydown="onKeydown">
    <NCard :bordered="false" class="card-wrapper h-full" title="Prompt 管理（项目生效提示词）">
      <NAlert v-if="tableError" class="mb-16px" type="error" :bordered="false" show-icon>
        {{ tableError }}
        <NButton size="small" secondary @click="getData">重新加载</NButton>
      </NAlert>
      <div class="business-toolbar mb-16px">
        <div class="business-toolbar__info">
          <NTag type="success" round size="small">6 种提示词类型</NTag>
          <span style="margin-left: 8px; font-size: 13px; color: #999;">编辑自动创建新版本 · Ctrl+S 保存</span>
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

    <!-- 编辑抽屉：左右分栏 -->
    <NDrawer v-model:show="editDrawerOpen" :width="960" placement="right">
      <NDrawerContent
        :title="`编辑：${TYPE_OPTIONS.find(t => t.value === editForm.type)?.label || editForm.type} — v${editVersion}`"
        :native-scrollbar="false"
      >
        <div class="drawer-split">
          <!-- 左侧：编辑表单 -->
          <div class="drawer-left">
            <NForm label-placement="top" label-width="auto" size="small">
              <NFormItem label="名称">
                <NInput v-model:value="editForm.name" placeholder="提示词名称" />
              </NFormItem>
              <NFormItem label="用途说明">
                <NInput v-model:value="editForm.description" placeholder="简短说明用途" />
              </NFormItem>

              <!-- 代码编辑器 -->
              <NFormItem label="提示词内容">
                <div class="code-editor-wrapper">
                  <div class="code-editor-gutter">
                    <div v-for="n in lineCount" :key="n" class="code-editor-line-number">{{ n }}</div>
                  </div>
                  <textarea
                    ref="textareaRef"
                    v-model="editForm.content"
                    class="code-editor-textarea"
                    placeholder="输入提示词模板，使用 {变量名} 作为占位符"
                    spellcheck="false"
                  />
                </div>
                <div class="code-editor-footer">
                  <span>{{ lineCount }} 行 · {{ charCount }} 字符</span>
                </div>
              </NFormItem>

              <!-- 变量占位符（点击即插入） -->
              <template v-if="extractedVars.length">
                <NFormItem label="变量占位符（点击即插入）">
                  <div class="var-tags">
                    <NTag v-for="v in extractedVars" :key="v" size="small" type="warning"
                      style="cursor: pointer;" @click="insertVar(v)">
                      {{ v }}
                    </NTag>
                  </div>
                </NFormItem>
              </template>
              <NFormItem v-else label="变量占位符">
                <div style="color: #999; font-size: 12px;">未检测到变量占位符</div>
              </NFormItem>

              <!-- 测试按钮 -->
              <NFormItem label="运行测试">
                <NSpace>
                  <NButton size="small" type="info" secondary :loading="testLoading" @click="handleTest">
                    <template #icon><SvgIcon icon="mdi:play" /></template>
                    使用最近场次数据测试
                  </NButton>
                </NSpace>
              </NFormItem>
            </NForm>
          </div>

          <!-- 右侧：版本历史面板 -->
          <div class="drawer-right">
            <div class="history-panel-title">版本历史（{{ versionHistory.length }}）</div>
            <NScrollbar style="flex: 1; max-height: calc(100vh - 220px);">
              <div v-for="v in versionHistory" :key="v.id"
                class="version-item" :class="{ 'version-item--current': v.version === editVersion }">
                <div class="version-item__header">
                  <NTag size="small" :type="v.version === editVersion ? 'success' : 'info'">v{{ v.version }}</NTag>
                  <span class="version-item__date">
                    {{ v.created_at ? new Date(v.created_at).toLocaleString('zh-CN') : '' }}
                  </span>
                </div>
                <div class="version-item__actions">
                  <NButton size="tiny" type="primary" quaternary @click="restoreVersion(v)">恢复</NButton>
                  <NButton size="tiny" type="warning" quaternary style="margin-left: 4px;" @click="openDiff(v)">对比</NButton>
                </div>
              </div>
            </NScrollbar>
          </div>
        </div>

        <!-- 底部按钮 -->
        <template #footer>
          <NSpace justify="space-between" style="width: 100%;">
            <span style="color: #999; font-size: 12px;">编辑后自动创建新版本，Ctrl+S 快捷保存</span>
            <NSpace>
              <NButton @click="editDrawerOpen = false">取消</NButton>
              <NButton :loading="saving" @click="handleSaveContinue">保存并继续</NButton>
              <NButton type="primary" :loading="saving" @click="handleSave">保存并关闭</NButton>
            </NSpace>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>

    <!-- diff 对比弹窗（独立全屏 Modal） -->
    <NModal v-model:show="diffModalOpen" preset="card" title="版本对比" style="width: 800px; max-height: 80vh;">
      <div v-if="diffVersion" style="margin-bottom: 12px;">
        <NTag type="info">v{{ diffVersion.version }}</NTag>
        <span style="margin-left: 8px; color: #666; font-size: 12px;">
          {{ diffVersion.created_at ? new Date(diffVersion.created_at).toLocaleString('zh-CN') : '' }}
        </span>
        <span style="margin-left: 16px; color: #999; font-size: 12px;">红色 = 已删除 · 绿色 = 新增</span>
      </div>
      <div class="diff-modal-body">
        <div v-for="dl in diffLines" :key="dl.idx + dl.type"
          class="diff-line" :class="'diff-line--' + dl.type">
          <span class="diff-line-num">{{ dl.idx }}</span>
          <span class="diff-line-sign">{{ dl.type === 'added' ? '+' : dl.type === 'removed' ? '-' : ' ' }}</span>
          <span class="diff-line-text">{{ dl.line }}</span>
        </div>
      </div>
      <template #footer>
        <NSpace justify="end"><NButton @click="diffModalOpen = false">关闭</NButton></NSpace>
      </template>
    </NModal>

    <!-- 测试结果弹窗 -->
    <NModal v-model:show="testModalOpen" preset="card" title="测试结果" style="width: 700px; max-height: 80vh;">
      <NSpin :show="testLoading">
        <div v-if="testError" class="test-error">{{ testError }}</div>
        <pre v-else class="test-result">{{ testResult }}</pre>
      </NSpin>
      <template #footer>
        <NSpace justify="end"><NButton @click="testModalOpen = false">关闭</NButton></NSpace>
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

/* 抽屉左右分栏 */
.drawer-split { display: flex; gap: 16px; height: 100%; }
.drawer-left { flex: 1; min-width: 0; overflow-y: auto; padding-right: 4px; }
.drawer-right {
  width: 200px;
  flex-shrink: 0;
  border-left: 1px solid #eee;
  padding-left: 12px;
  display: flex;
  flex-direction: column;
}
.history-panel-title { font-weight: 600; font-size: 14px; margin-bottom: 8px; }

/* 代码编辑器 */
.code-editor-wrapper {
  width: 100%;
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
.code-editor-line-number { line-height: 1.6; height: 1.6em; }
.code-editor-textarea {
  flex: 1; border: none; outline: none; padding: 8px 12px;
  resize: vertical; font-family: inherit; font-size: inherit;
  line-height: inherit; tab-size: 2; background: #fff; min-height: 200px;
}
.code-editor-textarea:focus { background: #fafafa; }
.code-editor-footer { display: flex; align-items: center; gap: 8px; margin-top: 6px; font-size: 12px; color: #999; }

/* 变量标签 */
.var-tags { display: flex; flex-wrap: wrap; gap: 4px; }

/* 版本历史右侧面板 */
.version-item {
  padding: 6px 8px;
  margin-bottom: 4px;
  border-radius: 4px;
  border: 1px solid #eee;
  background: #fafafa;
}
.version-item--current { border-color: #18a058; background: #f0faf0; }
.version-item__header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.version-item__date { color: #999; font-size: 11px; }
.version-item__actions { margin-top: 4px; }

/* diff 弹窗 */
.diff-modal-body {
  max-height: 55vh;
  overflow: auto;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.5;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
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

/* 测试结果 */
.test-error { color: #e74c3c; white-space: pre-wrap; }
.test-result {
  max-height: 55vh; overflow: auto; background: #f5f5f5;
  padding: 12px; border-radius: 6px; font-size: 12px; white-space: pre-wrap;
}
</style>
