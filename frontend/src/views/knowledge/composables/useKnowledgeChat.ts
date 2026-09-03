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
import { useRoute, useRouter } from 'vue-router';
import { useMessage } from 'naive-ui';
import {
  askKnowledgeStream,
  fetchSessionSelectorOptions,
  setMessageFeedback
} from '@/service/api/douyin';
import { buildCommonSessionOptions } from '@/adapters/session-selector-adapter';
import {
  appendUniqueSelectorPage,
  useSessionSelectorFilters,
  type SessionSelectorChangeContext
} from '@/hooks/business/session-selector';
import { unwrapServiceData } from '@/utils/service';
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
  const router = useRouter();

  /* ===== 对话历史管理 ===== */
  const conv = useConversations();

  /* ===== 状态 ===== */
  const question = ref('');
  const chatting = ref(false);
  const messages = ref<ChatMessage[]>([]);
  const sessions = ref<Api.Douyin.LiveSessionListItem[]>([]);
  const sessionLoading = ref(false);
  const selectedSessionId = ref<number | null>(null);
  let messageId = 0;
  const contextSessionId = computed(() => selectedSessionId.value);
  const sessionOptions = computed(() => buildCommonSessionOptions(sessions.value));

  /** 右侧引用面板：默认显示最后一条有来源的 AI 消息 */
  const activeSources = ref<Api.Douyin.KnowledgeSource[]>([]);
  const activeSourceMsgId = ref<number | null>(null);

  /** 流式取消控制器 */
  let streamAbortController: AbortController | null = null;
  let streamGeneration = 0;
  let conversationLoadGeneration = 0;
  let scopeGeneration = 0;

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
    // 历史对话详情落稳前 activeConvId 仍可能指向旧对话，此时禁止发送。
    // 页面按钮同时禁用是交互防线，这里的入口校验是业务防线。
    if (!content || chatting.value || conv.detailLoading.value) return;

    const requestGeneration = ++streamGeneration;
    const requestSessionId = selectedSessionId.value;
    const requestConversationId = conv.activeConvId.value;
    const isCurrentStream = () =>
      requestGeneration === streamGeneration && selectedSessionId.value === requestSessionId;

    console.log('[sendQuestion] 开始发送:', content.slice(0, 30));
    const now = new Date();
    const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    messages.value.push({ id: ++messageId, role: 'user', content, timestamp: timeStr });
    question.value = '';
    chatting.value = true;

    // 创建 AbortController
    const controller = new AbortController();
    streamAbortController = controller;

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
      await askKnowledgeStream(
        content,
        {
          onToken(token: string) {
            if (!isCurrentStream()) return;
            const msg = getAiMsg();
            if (msg) msg.content += token;
          },
          onDone(sources, _hasResult) {
            if (!isCurrentStream()) return;
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
            void saveMessages(
              content,
              msg.content,
              sources,
              msg,
              requestConversationId,
              requestSessionId,
              isCurrentStream
            );
          },
          onError(errorMsg: string) {
            if (!isCurrentStream()) return;
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
        requestSessionId || undefined,
        controller.signal
      );
    } catch (error: any) {
      // AbortController 主动取消不算错误
      if (error?.name === 'AbortError' || error?.name === 'CanceledError') {
        if (!isCurrentStream()) return;
        const msg = getAiMsg();
        if (msg && !msg.content) {
          msg.content = '已停止生成。';
        }
        return;
      }

      console.error('[sendQuestion] 异常:', error);
      if (!isCurrentStream()) return;
      const msg = getAiMsg();
      if (msg) {
        msg.content = error instanceof Error ? error.message : '知识检索请求失败，请确认 AI 服务状态后重试。';
        msg.error = true;
      }
    } finally {
      if (requestGeneration === streamGeneration) {
        chatting.value = false;
        streamAbortController = null;
      }
    }
  }

  /** 🆕 持久化保存消息到后端 */
  async function saveMessages(
    questionText: string,
    aiAnswer: string,
    sources?: Api.Douyin.KnowledgeSource[],
    targetAiMsg?: ChatMessage,
    conversationId?: number | null,
    sessionId?: number | null,
    isCurrent: () => boolean = () => true
  ) {
    try {
      if (conversationId) {
        // 已有对话：追加消息
        const aiMsgId = await conv.appendMessages(conversationId, questionText, aiAnswer, sources);
        // 只回填本次生成的 AI 消息，避免保存期间用户切换对话后写到别的消息上。
        if (isCurrent() && targetAiMsg && aiMsgId) {
          targetAiMsg.backendMsgId = aiMsgId;
        }
      } else {
        // 新对话：创建对话 + 保存
        const { convId, aiMsgId } = await conv.createConvWithFirstMsg(
          questionText,
          aiAnswer,
          sources,
          sessionId,
          isCurrent
        );
        if (convId) {
          // 更新消息列表中 AI 消息的 backend ID（以便后续反馈）
          // 只回填本次生成的 AI 消息，避免保存期间用户切换对话后写到别的消息上。
          if (isCurrent() && targetAiMsg) {
            targetAiMsg.backendMsgId = aiMsgId;
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
    if (chatting.value) {
      const pendingAnswer = [...messages.value].reverse().find(item => item.role === 'ai');
      if (pendingAnswer && !pendingAnswer.content) pendingAnswer.content = '已停止生成。';
    }
    streamGeneration += 1;
    streamAbortController?.abort();
    streamAbortController = null;
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
    startNewConversation();
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
    const loadGeneration = ++conversationLoadGeneration;
    scopeGeneration += 1;
    stopGeneration();
    const detail = await conv.selectConversation(convId);
    if (!detail || loadGeneration !== conversationLoadGeneration) return;
    await applySessionScope(detail.sessionId, false);
    if (loadGeneration !== conversationLoadGeneration) return;
    conv.activateConversation(convId);
    // 即使后端返回空消息，也要清空当前聊天区，避免旧对话内容残留。
    messages.value = detail.messages;
    activeSources.value = [];
    activeSourceMsgId.value = null;
    // 恢复 messageId 计数器；空对话从 0 重新开始。
    messageId = detail.messages.length ? Math.max(...detail.messages.map(m => m.id), 0) + 1 : 0;
  }

  async function loadSessionOptions(
    includeSessionId?: number | null,
    context?: SessionSelectorChangeContext
  ) {
    if (!context || context.mode === 'replace') sessionLoading.value = true;
    try {
      const response = await fetchSessionSelectorOptions(selectorFilters.buildQuery(includeSessionId, context));
      if (context && !context.isCurrent()) return 0;
      const records = unwrapServiceData(response, '知识库场次读取失败');
      sessions.value = context?.mode === 'append'
        ? appendUniqueSelectorPage(sessions.value, records, item => item.id)
        : records;
      if (!context) selectorFilters.registerInitialPage(records.length);
      return records.length;
    } finally {
      if ((!context || context.isCurrent()) && (!context || context.mode === 'replace')) sessionLoading.value = false;
    }
  }

  /** 应用问答范围；人工切换范围时开启新对话，但不会删除已保存的旧对话。 */
  async function applySessionScope(value: number | null, startNew = true) {
    if (value === selectedSessionId.value && !startNew) return;
    if (startNew) startNewConversation();
    else stopGeneration();
    const scopeRequest = ++scopeGeneration;
    selectedSessionId.value = value;
    const nextQuery = { ...route.query };
    if (value) nextQuery.sessionId = String(value);
    else delete nextQuery.sessionId;
    void router.replace({ query: nextQuery });
    if (value && !sessions.value.some(item => item.id === value)) {
      const scopeContext: SessionSelectorChangeContext = {
        isCurrent: () => scopeRequest === scopeGeneration,
        mode: 'replace',
        offset: 0,
        limit: 100
      };
      void loadSessionOptions(value, scopeContext).catch(error => {
        if (scopeContext.isCurrent()) {
          message.error(error instanceof Error ? error.message : '场次范围读取失败');
        }
      });
    }
  }

  async function reloadFilteredSessions(context: SessionSelectorChangeContext) {
    try {
      const count = await loadSessionOptions(undefined, context);
      if (!context.isCurrent() || context.mode === 'append') return count;
      if (selectedSessionId.value && !sessions.value.some(item => item.id === selectedSessionId.value)) {
        await applySessionScope(sessions.value[0]?.id || null);
      }
      return count;
    } catch (error) {
      if (!context.isCurrent()) return;
      message.error(error instanceof Error ? error.message : '知识库场次筛选失败');
    }
  }

  const selectorFilters = useSessionSelectorFilters(reloadFilteredSessions);

  async function initializeSessionSelector() {
    const raw = Array.isArray(route.query.sessionId) ? route.query.sessionId[0] : route.query.sessionId;
    const routeSessionId = Number(raw);
    selectedSessionId.value = Number.isInteger(routeSessionId) && routeSessionId > 0 ? routeSessionId : null;
    await Promise.all([
      selectorFilters.loadAnchors(),
      loadSessionOptions(selectedSessionId.value)
    ]);
  }

  function startNewConversation() {
    conversationLoadGeneration += 1;
    scopeGeneration += 1;
    stopGeneration();
    messages.value = [];
    activeSources.value = [];
    activeSourceMsgId.value = null;
    messageId = 0;
    conv.startNewConversation();
  }

  async function removeConversation(convId: number) {
    const removingActive = conv.activeConvId.value === convId;
    await conv.removeConversation(convId);
    if (removingActive) startNewConversation();
  }

  return {
    // 状态
    question,
    contextSessionId,
    selectedSessionId,
    sessionOptions,
    sessionLoading,
    selectorAnchorKey: selectorFilters.anchorKey,
    selectorDateRange: selectorFilters.dateRange,
    selectorAnchorOptions: selectorFilters.anchorOptions,
    selectorHasMore: selectorFilters.hasMore,
    selectorLoadingMore: selectorFilters.loadingMore,
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
    startNewConversation,
    initializeSessionSelector,
    changeSession: (value: number | null) => applySessionScope(value),
    updateSelectorAnchor: selectorFilters.updateAnchor,
    updateSelectorDateRange: selectorFilters.updateDateRange,
    searchSelectorSessions: selectorFilters.search,
    loadMoreSelectorSessions: selectorFilters.loadMore,
    resetSelectorFilters: selectorFilters.reset,
    removeConversation,
  };
}
