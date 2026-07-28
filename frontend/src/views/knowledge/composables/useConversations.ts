/**
 * 对话历史 — 侧边栏状态管理
 *
 * 职责：加载对话列表、切换/新建/删除对话、加载对话消息。
 * 2026-07-28 方案 C Chat UI 全面升级
 */
import { ref } from 'vue';
import { useMessage } from 'naive-ui';
import {
  fetchConversations,
  fetchConversationDetail,
  createConversation,
  deleteConversation,
  appendConversationMessages,
} from '@/service/api/douyin';
import { formatRelativeTime } from '@/utils/format';
import type { ChatMessage } from './useKnowledgeChat';

export function useConversations() {
  const message = useMessage();

  /** 对话列表 */
  const conversations = ref<Api.Douyin.ConversationListItem[]>([]);
  /** 当前选中的对话 ID（null 表示新对话） */
  const activeConvId = ref<number | null>(null);
  /** 列表加载中 */
  const listLoading = ref(false);
  /** 详情加载中 */
  const detailLoading = ref(false);

  /** 加载对话列表 */
  async function loadConversations() {
    listLoading.value = true;
    try {
      const data = await fetchConversations();
      // backendRequest 返回 FlatResponseData（联合类型），但运行时实际返回 T
      conversations.value = (data as Api.Douyin.ConversationListItem[] | null) || [];
    } catch (err) {
      console.error('[useConversations] 加载对话列表失败:', err);
    } finally {
      listLoading.value = false;
    }
  }

  /** 选中一个对话并加载其消息 */
  async function selectConversation(convId: number): Promise<ChatMessage[]> {
    activeConvId.value = convId;
    detailLoading.value = true;
    try {
      const raw = await fetchConversationDetail(convId);
      // 运行时实际返回 ConversationDetail
      const detail = raw as Api.Douyin.ConversationDetail | null;
      if (!detail) {
        message.error('对话不存在');
        return [];
      }
      // 把后端消息格式转为前端 ChatMessage 格式
      return (detail.messages || []).map((msg: Api.Douyin.ConversationMessage) => ({
        id: msg.id,
        role: msg.role as 'user' | 'ai',
        content: msg.content,
        sources: (msg.sources as Api.Douyin.KnowledgeSource[]) || [],
        error: msg.error,
        timestamp: msg.created_at
          ? new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
          : undefined,
      }));
    } catch (err) {
      console.error('[useConversations] 加载对话详情失败:', err);
      message.error('加载对话失败');
      return [];
    } finally {
      detailLoading.value = false;
    }
  }

  /** 新建对话（不立即发消息，只是切换到新对话状态） */
  function startNewConversation() {
    activeConvId.value = null;
  }

  /** 删除对话 */
  async function removeConversation(convId: number) {
    try {
      await deleteConversation(convId);
      conversations.value = conversations.value.filter(c => c.id !== convId);
      if (activeConvId.value === convId) {
        activeConvId.value = null;
      }
      message.success('对话已删除');
    } catch (err) {
      console.error('[useConversations] 删除对话失败:', err);
      message.error('删除失败');
    }
  }

  /** 创建对话并设置为首条消息（发送第一条用户消息后调用） */
  async function createConvWithFirstMsg(
    firstMessage: string,
    aiAnswer: string,
    sources?: Api.Douyin.KnowledgeSource[]
  ): Promise<number> {
    try {
      // 1. 创建对话（带首条用户消息）
      const raw = await createConversation(
        firstMessage.slice(0, 50), // 标题 = 前50字
        firstMessage
      );
      const conv = raw as Api.Douyin.ConversationDetail | null;
      if (!conv) return 0;
      activeConvId.value = conv.id;

      // 2. 追加 AI 回答
      if (aiAnswer) {
        const appendResult = await appendConversationMessages(conv.id, {
          question: firstMessage,
          ai_answer: aiAnswer,
          sources,
        });
        // 更新消息列表中的消息 ID（用于后续反馈）
        if (appendResult) {
          const result = appendResult as { ai_msg_id?: number };
          if (result.ai_msg_id) {
            return conv.id;
          }
        }
      }

      // 3. 刷新列表
      await loadConversations();
      return conv.id;
    } catch (err) {
      console.error('[useConversations] 创建对话失败:', err);
      return 0;
    }
  }

  /** 向已有对话追加消息 */
  async function appendMessages(
    convId: number,
    question: string,
    aiAnswer: string,
    sources?: Api.Douyin.KnowledgeSource[]
  ) {
    try {
      await appendConversationMessages(convId, { question, ai_answer: aiAnswer, sources });
      // 刷新列表以更新 message_count
      await loadConversations();
    } catch (err) {
      console.error('[useConversations] 追加消息失败:', err);
    }
  }

  return {
    // 状态
    conversations,
    activeConvId,
    listLoading,
    detailLoading,
    // 方法
    loadConversations,
    selectConversation,
    startNewConversation,
    removeConversation,
    createConvWithFirstMsg,
    appendMessages,
    formatTime: formatRelativeTime,
  };
}
