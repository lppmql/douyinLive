<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';

defineOptions({ name: 'SessionWorkflowNav' });

type WorkflowPage = 'detail' | 'transcripts' | 'analysis' | 'knowledge';

const props = withDefaults(
  defineProps<{
    sessionId?: number | null;
    active: WorkflowPage;
  }>(),
  { sessionId: null }
);

const router = useRouter();
const validSessionId = computed(() => (Number(props.sessionId) > 0 ? Number(props.sessionId) : null));

const steps: Array<{ key: WorkflowPage; label: string; icon: string }> = [
  { key: 'detail', label: '场次详情', icon: 'mdi:video-outline' },
  { key: 'transcripts', label: '主播话术', icon: 'mdi:text-box-outline' },
  { key: 'analysis', label: 'AI 复盘', icon: 'mdi:chart-box-outline' },
  { key: 'knowledge', label: '知识库问答', icon: 'mdi:chat-question-outline' }
];

function navigate(target: WorkflowPage) {
  if (target === props.active) return;
  const sessionId = validSessionId.value;
  if (target === 'detail') {
    if (sessionId) void router.push({ name: 'live-session-detail', params: { id: String(sessionId) } });
    return;
  }
  void router.push({
    name: target,
    query: sessionId ? { sessionId: String(sessionId) } : undefined
  });
}
</script>

<template>
  <div class="session-workflow-nav">
    <div class="session-workflow-nav__context">
      <SvgIcon icon="mdi:link-variant" class="text-17px text-primary" />
      <span>{{ validSessionId ? `场次 #${validSessionId}` : '未指定场次' }}</span>
    </div>
    <div class="session-workflow-nav__steps">
      <NButton
        v-for="step in steps"
        :key="step.key"
        size="small"
        :type="active === step.key ? 'primary' : 'default'"
        :secondary="active !== step.key"
        :disabled="step.key === 'detail' && !validSessionId"
        @click="navigate(step.key)"
      >
        <template #icon><SvgIcon :icon="step.icon" /></template>
        {{ step.label }}
      </NButton>
    </div>
  </div>
</template>

<style scoped>
.session-workflow-nav {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid rgba(128, 128, 128, 0.14);
  border-radius: 10px;
  background: var(--n-color, rgba(255, 255, 255, 0.78));
}

.session-workflow-nav__context,
.session-workflow-nav__steps {
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-workflow-nav__context {
  flex-shrink: 0;
  color: var(--n-text-color-2, #64748b);
  font-size: 12px;
  font-weight: 600;
}

.session-workflow-nav__steps {
  min-width: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
}

@media (max-width: 640px) {
  .session-workflow-nav {
    align-items: flex-start;
    flex-direction: column;
  }

  .session-workflow-nav__steps {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
