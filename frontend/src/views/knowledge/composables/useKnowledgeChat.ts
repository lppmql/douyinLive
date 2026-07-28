/**
 * 知识库 — 聊天状态与操作管理（2026-07-28 方案 C 升级）
 *
 * 新增：
 * - 对话持久化（自动保存到后端）
 * - 停止生成（AbortController）
 * - 反馈（赞/踩）
 * - 对话历史管理集成
 */
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useMessage } from 'naive-ui';
import { askKnowledgeStream, setMessageFeedback } from '@/service/api/douyin';
import { useConversations } from './useConversations';

export type ChatMessage = {
  id: number;
  role: 'user' | 'ai';
  content: string;
  sources?: Api.Douyin.KnowledgeSource[];
  error?: boolean;
  /** 消息发送时间（用户消息专用），格式如 "14:30" */
  timestamp?: string;
  /** 赞/踩反馈 */
  feedback?: 'like' | 'dislike' | null;
  /** 后端消息 ID（用于反馈 API） */
  backendMsgId?: number;
};

export function useKnowledgeChat() {
  const message = useMessage();
  const route = useRoute();

  /* ===== 对话历史管理 ===== */
  const conv = useConversations();

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

  /** 流式取消控制器 */
  let streamAbortController: AbortController | null = null;

  /* ===== 自动选中最后一条带来源的消息 ===== */
  watch(messages, () => {
    const lastWithSources = [...messages.value].reverse().find(m => m.role === 'ai' && m.sources?.length);
    if (lastWithSources) {
      activeSources.value = lastWithSources.sources!;
      activeSourceMsgId.value = lastWithSources.id;
    }
  }, { deep: true });

  /** 手动选择某条消息的来源 */
  function selectSources(chatMsg: ChatMessage) {
    activeSources.value = chatMsg.sources || [];
    activeSourceMsgId.value = chatMsg.id;
  }

  /* ===== 发送问题（流式） ===== */
  async function sendQuestion(preset?: string) {
    const content = (preset || question.value).trim();
    if (!content || chatting.value) return;

    console.log('[sendQuestion] 开始发送:', content.slice(0, 30));
    const now = new Date();
    const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    messages.value.push({ id: ++messageId, role: 'user', content, timestamp: timeStr });
    question.value = '';
    chatting.value = true;

    // 创建 AbortController
    streamAbortController = new AbortController();

    // 创建空 AI 消息占位
    const aiMsgId = ++messageId;
    messages.value.push({
      id: aiMsgId,
      role: 'ai',
      content: '',
      sources: [],
    });

    const getAiMsg = (): ChatMessage | undefined =>
      messages.value.find(m => m.id === aiMsgId);

    try {
      const knowledgeQuestion = contextSessionId.value
        ? `请只结合直播场次 ${contextSessionId.value} 的真实资料回答：${content}`
        : content;

      await askKnowledgeStream(
        knowledgeQuestion,
        {
          onToken(token: string) {
            const msg = getAiMsg();
            if (msg) msg.content += token;
          },
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

            // 🆕 持久化：保存用户问题和 AI 回答到后端
            saveMessages(content, msg.content, sources);
          },
          onError(errorMsg: string) {
            const msg = getAiMsg();
            if (msg) {
              msg.content = errorMsg;
              msg.error = true;
            }
          },
        },
        undefined,
        // 历史消息转换为后端期望的格式 { role, content }
        // slice(0, -1)：排除最后一条 AI 占位消息，不把自己的空内容传给后端当上下文
        messages.value.slice(0, -1).map(m => ({
          role: m.role === 'ai' ? 'assistant' as const : 'user' as const,
          content: m.content,
        })),
      );
    } catch (error: any) {
      // AbortController 主动取消不算错误
      if (error?.name === 'AbortError' || error?.name === 'CanceledError') {
        const msg = getAiMsg();
        if (msg && !msg.content) {
          msg.content = '已停止生成。';
        }
        return;
      }

      console.error('[sendQuestion] 异常:', error);
      const msg = getAiMsg();
      if (msg) {
        msg.content = error instanceof Error ? error.message : '知识检索请求失败，请确认 AI 服务状态后重试。';
        msg.error = true;
      }
    } finally {
      chatting.value = false;
      streamAbortController = null;
    }
  }

  /** 🆕 持久化保存消息到后端 */
  async function saveMessages(
    questionText: string,
    aiAnswer: string,
    sources?: Api.Douyin.KnowledgeSource[],
  ) {
    try {
      if (conv.activeConvId.value) {
        // 已有对话：追加消息
        await conv.appendMessages(conv.activeConvId.value, questionText, aiAnswer, sources);
      } else {
        // 新对话：创建对话 + 保存
        const newId = await conv.createConvWithFirstMsg(questionText, aiAnswer, sources);
        if (newId) {
          // 更新消息列表中 AI 消息的 backend ID（以便后续反馈）
          const lastAi = [...messages.value].reverse().find(m => m.role === 'ai');
          if (lastAi) {
            lastAi.backendMsgId = undefined; // 新对话时消息 ID 会变化
          }
        }
      }
    } catch (err) {
      console.error('[saveMessages] 保存失败:', err);
      // 不影响用户体验，静默失败
    }
  }

  /* ===== 停止生成 ===== */
  function stopGeneration() {
    streamAbortController?.abort();
    chatting.value = false;
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
    conv.startNewConversation();
    message.success('对话已清空');
  }

  /* ===== 🆕 反馈（赞/踩） ===== */
  async function handleFeedback(chatMsg: ChatMessage, type: 'like' | 'dislike') {
    // 更新本地状态
    chatMsg.feedback = type === chatMsg.feedback ? null : type; // 再次点击取消
    message.success(chatMsg.feedback ? (type === 'like' ? '已点赞' : '已点踩') : '已取消反馈');

    // 如果知道后端消息 ID，同步到后端
    if (chatMsg.backendMsgId && conv.activeConvId.value && chatMsg.feedback) {
      try {
        await setMessageFeedback(conv.activeConvId.value, chatMsg.backendMsgId, chatMsg.feedback);
      } catch (err) {
        console.error('[handleFeedback] 后端同步失败:', err);
      }
    }
  }

  /* ===== 复制文本 ===== */
  async function copyText(content: string) {
    await navigator.clipboard.writeText(content);
    message.success('已复制');
  }

  /* ===== 🆕 加载历史对话 ===== */
  async function loadConversation(convId: number) {
    const msgs = await conv.selectConversation(convId);
    if (msgs.length) {
      messages.value = msgs;
      // 恢复 messageId 计数器
      messageId = Math.max(...msgs.map(m => m.id), 0) + 1;
    }
  }

  return {
    // 状态
    question,
    contextSessionId,
    chatting,
    messages,
    activeSources,
    activeSourceMsgId,
    // 🆕 对话历史
    conversations: conv.conversations,
    activeConvId: conv.activeConvId,
    listLoading: conv.listLoading,
    detailLoading: conv.detailLoading,
    // 方法
    selectSources,
    sendQuestion,
    stopGeneration,
    handleQuestionKeydown,
    clearConversation,
    handleFeedback,
    copyText,
    // 🆕 对话管理
    loadConversations: conv.loadConversations,
    loadConversation,
    startNewConversation: conv.startNewConversation,
    removeConversation: conv.removeConversation,
  };
}
