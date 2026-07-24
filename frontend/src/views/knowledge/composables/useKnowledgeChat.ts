/**
 * 知识库 — 聊天状态与操作管理
 *
 * 职责：管理对话消息、发送问题、清空对话、复制文本。
 * 滚动逻辑由 ChatPanel 子组件自行管理。
 */
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useMessage } from 'naive-ui';
import { askKnowledgeStream } from '@/service/api/douyin';

export type ChatMessage = {
  id: number;
  role: 'user' | 'ai';
  content: string;
  sources?: Api.Douyin.KnowledgeSource[];
  error?: boolean;
  /** 消息发送时间（用户消息专用），格式如 "14:30" */
  timestamp?: string;
};

export function useKnowledgeChat() {
  const message = useMessage();
  const route = useRoute();

  /* ===== 状态 ===== */
  const question = ref('');
  const chatting = ref(false);
  const messages = ref<ChatMessage[]>([]);
  let messageId = 0;
  const contextSessionId = computed(() => {
    const raw = Array.isArray(route.query.sessionId) ? route.query.sessionId[0] : route.query.sessionId;
    const value = Number(raw);
    return Number.isInteger(value) && value > 0 ? value : null;
  });

  /** 右侧引用面板：默认显示最后一条有来源的 AI 消息 */
  const activeSources = ref<Api.Douyin.KnowledgeSource[]>([]);
  const activeSourceMsgId = ref<number | null>(null);

  /* ===== 自动选中最后一条带来源的消息 ===== */
  watch(messages, () => {
    const lastWithSources = [...messages.value].reverse().find(m => m.role === 'ai' && m.sources?.length);
    if (lastWithSources) {
      activeSources.value = lastWithSources.sources!;
      activeSourceMsgId.value = lastWithSources.id;
    }
  }, { deep: true });

  /** 手动选择某条消息的来源 */
  function selectSources(chatMessage: ChatMessage) {
    activeSources.value = chatMessage.sources || [];
    activeSourceMsgId.value = chatMessage.id;
  }

  /* ===== 发送问题（流式） ===== */
  async function sendQuestion(preset?: string) {
    const content = (preset || question.value).trim();
    if (!content || chatting.value) return;

    // 1. 先显示用户消息（带当前时间）
    console.log('[sendQuestion] 开始发送:', content.slice(0, 30));
    const now = new Date();
    const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    messages.value.push({ id: ++messageId, role: 'user', content, timestamp: timeStr });
    question.value = '';
    chatting.value = true;

    // 2. 创建一个空的 AI 消息占位（内容会在流式回调中逐字填充）
    const aiMsgId = ++messageId;
    messages.value.push({
      id: aiMsgId,
      role: 'ai',
      content: '',       // 空内容，token 到达后逐字追加
      sources: [],
    });

    /** 通过 messages 响应式数组获取 AI 消息引用（确保修改能被 Vue 追踪到） */
    const getAiMsg = (): ChatMessage | undefined =>
      messages.value.find(m => m.id === aiMsgId);

    try {
      const knowledgeQuestion = contextSessionId.value
        ? `请只结合直播场次 ${contextSessionId.value} 的真实资料回答：${content}`
        : content;

      await askKnowledgeStream(
        knowledgeQuestion,
        {
          // 每收到一个文字片段，追加到消息内容
          onToken(token: string) {
            const msg = getAiMsg();
            if (msg) msg.content += token;
          },
          // 流结束，设置引用来源
          onDone(sources, _hasResult) {
            const msg = getAiMsg();
            if (!msg) return;
            msg.sources = sources;
            if (!msg.content) {
              msg.content = '当前真实知识库没有返回可用结论。';
            }
            if (msg.sources?.length) {
              activeSources.value = msg.sources;
              activeSourceMsgId.value = msg.id;
            }
          },
          // 流中出错
          onError(errorMsg: string) {
            const msg = getAiMsg();
            if (msg) {
              msg.content = errorMsg;
              msg.error = true;
            }
          },
        }
      );
    } catch (error) {
      console.error('[sendQuestion] 异常:', error);
      const msg = getAiMsg();
      if (msg) {
        msg.content = error instanceof Error ? error.message : '知识检索请求失败，请确认 AI 服务状态后重试。';
        msg.error = true;
      }
    } finally {
      chatting.value = false;
    }
  }

  /* ===== 键盘事件 ===== */
  function handleQuestionKeydown(event: KeyboardEvent) {
    if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    void sendQuestion();
  }

  /* ===== 清空对话 ===== */
  function clearConversation() {
    messages.value = [];
    activeSources.value = [];
    activeSourceMsgId.value = null;
    message.success('对话已清空');
  }

  /* ===== 复制文本 ===== */
  async function copyText(content: string) {
    await navigator.clipboard.writeText(content);
    message.success('已复制');
  }

  return {
    // 状态
    question,
    contextSessionId,
    chatting,
    messages,
    activeSources,
    activeSourceMsgId,
    // 方法
    selectSources,
    sendQuestion,
    handleQuestionKeydown,
    clearConversation,
    copyText
  };
}
