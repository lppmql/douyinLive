<script setup lang="ts">
import { ref, h, onMounted } from 'vue';
import { NTag, useMessage } from 'naive-ui';
import { $t } from '@/locales';
import { fetchPrompts, askKnowledge, saveToKnowledgeBase } from '@/service/api/douyin';

defineOptions({ name: 'Knowledge' });

const message = useMessage();

/* ---------- 知识库列表 ---------- */
interface KbItem {
  id: number;
  title: string;
  category: string;
  typeColor: 'success' | 'warning' | 'info';
  summary: string;
  source: string;
  time: string;
}

const items = ref<KbItem[]>([]);
const loading = ref(false);

onMounted(async () => {
  // try { const res = await fetchPrompts(); console.log(res); } catch {}
});

/* ---------- 聊天 ---------- */
const question = ref('');
const chatting = ref(false);
const messages = ref<{ role: 'user' | 'ai'; content: string }[]>([]);
const chatEndRef = ref<HTMLElement | null>(null);

async function sendQuestion() {
  const q = question.value.trim();
  if (!q) return;
  messages.value.push({ role: 'user', content: q });
  question.value = '';
  chatting.value = true;
  try {
    const res = await askKnowledge(q);
    messages.value.push({ role: 'ai', content: res.answer || '暂无回答' });
  } catch {
    messages.value.push({ role: 'ai', content: '请求失败，请稍后重试' });
  }
  chatting.value = false;
  setTimeout(() => chatEndRef.value?.scrollIntoView({ behavior: 'smooth' }), 100);
}

/* ---------- 保存到知识库 ---------- */
async function handleSave() {
  try {
    const res = await saveToKnowledgeBase(0);
    message.success(`已保存 ${res.analysis_saved + res.transcript_saved} 条`);
  } catch { message.error('保存失败'); }
}
</script>

<template>
  <NGrid :x-gap="16" :y-gap="16" cols="1 m:3" responsive="screen">
    <!-- 知识库列表 -->
    <NGi span="2">
      <NCard :bordered="false" class="card-wrapper">
        <template #header>
          <NSpace>
            <SvgIcon icon="mdi:book-open-variant" class="text-22px" />
            <span class="text-16px font-bold">{{ $t('page.knowledge.title') }}</span>
          </NSpace>
        </template>
        <NAlert type="info" closable>
          无数据时，可先在场次页面运行 AI 分析后保存到知识库
        </NAlert>
        <NEmpty v-if="items.length === 0" class="py-40px" description="知识库为空" />
      </NCard>
    </NGi>

    <!-- AI 聊天窗 -->
    <NGi span="1">
      <NCard :bordered="false" class="card-wrapper h-full" style="position: sticky; top: 16px">
        <template #header>
          <NSpace>
            <SvgIcon icon="mdi:chat-question" class="text-18px" />
            <span class="text-15px font-bold">AI 助手</span>
          </NSpace>
        </template>

        <!-- 消息列表 -->
        <div class="h-400px overflow-y-auto mb-12px px-4px" ref="chatEndRef">
          <div v-if="messages.length === 0" class="flex flex-col items-center justify-center py-40px text-center">
            <SvgIcon icon="mdi:robot-outline" class="text-64px text-gray-300 dark:text-gray-600 mb-16px" />
            <p class="text-14px text-gray-500 mb-8px">{{ $t('page.knowledge.chatPlaceholder') }}</p>
            <p class="text-12px text-gray-400">{{ $t('page.knowledge.chatDesc') }}</p>
          </div>
          <div v-for="(msg, i) in messages" :key="i"
            :class="['mb-12px', msg.role === 'user' ? 'text-right' : 'text-left']">
            <NTag :type="msg.role === 'user' ? 'primary' : 'success'" size="small" class="mb-4px">
              {{ msg.role === 'user' ? '我' : 'AI' }}
            </NTag>
            <div :class="['rounded-8px p-10px inline-block max-w-90% text-left leading-22px text-13px',
              msg.role === 'user' ? 'bg-primary-light text-white' : 'bg-gray-100 dark:bg-dark-300'">
              {{ msg.content }}
            </div>
          </div>
        </div>

        <!-- 输入框 -->
        <NSpace>
          <NInput v-model:value="question" type="text" placeholder="输入问题..." :disabled="chatting"
            @keyup.enter="sendQuestion" />
          <NButton type="primary" :loading="chatting" @click="sendQuestion">发送</NButton>
        </NSpace>
      </NCard>
    </NGi>
  </NGrid>
</template>

<style scoped></style>
