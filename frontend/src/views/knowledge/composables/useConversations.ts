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
import { unwrapServiceData } from '@/utils/service';
import { formatRelativeTime } from '@/utils/format';
import type { ChatMessage } from './useKnowledgeChat';

function toChatRole(role: string): ChatMessage['role'] {
  // 后端保存 AI 消息时使用 assistant，前端聊天气泡只认识 ai。
  // 这里集中转换，避免历史消息加载后被当成用户消息显示。
  return role === 'assistant' || role === 'ai' ? 'ai' : 'user';
}

function toChatMessage(msg: Api.Douyin.ConversationMessage): ChatMessage {
  return {
    id: msg.id,
    role: toChatRole(msg.role),
    content: msg.content,
    sources: (msg.sources as Api.Douyin.KnowledgeSource[]) || [],
    error: msg.error,
    feedback: msg.feedback as ChatMessage['feedback'],
    backendMsgId: msg.id,
    timestamp: msg.created_at
      ? new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      : undefined,
  };
}

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
      const response = await fetchConversations();
      conversations.value = unwrapServiceData(response, '对话列表为空');
    } catch (err) {
      console.error('[useConversations] 加载对话列表失败:', err);
      conversations.value = [];
    } finally {
      listLoading.value = false;
    }
  }

  /** 选中一个对话并加载其消息 */
  async function selectConversation(convId: number): Promise<ChatMessage[]> {
    activeConvId.value = convId;
    detailLoading.value = true;
    try {
      const response = await fetchConversationDetail(convId);
      const detail = unwrapServiceData(response, '对话不存在');
      return (detail.messages || []).map(toChatMessage);
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
  ): Promise<{ convId: number; aiMsgId?: number }> {
    try {
      // 1. 先创建空对话并设置标题；问答内容统一交给追加接口保存。
      // 这样可以避免首条用户问题被“创建对话”和“追加消息”各保存一次。
      const raw = await createConversation(
        firstMessage.slice(0, 50) // 标题 = 前50字
      );
      const conv = unwrapServiceData(raw, '创建对话失败');
      activeConvId.value = conv.id;
      let aiMsgId: number | undefined;

      // 2. 追加 AI 回答
      if (aiAnswer) {
        const appendResponse = await appendConversationMessages(conv.id, {
          question: firstMessage,
          ai_answer: aiAnswer,
          sources,
        });
        // 更新消息列表中的消息 ID（用于后续反馈）
        const appendResult = unwrapServiceData(appendResponse, '保存 AI 回答失败');
        if (appendResult.ai_msg_id) {
          aiMsgId = appendResult.ai_msg_id;
        }
      }

      // 3. 刷新列表
      await loadConversations();
      return { convId: conv.id, aiMsgId };
    } catch (err) {
      console.error('[useConversations] 创建对话失败:', err);
      return { convId: 0 };
    }
  }

  /** 向已有对话追加消息 */
  async function appendMessages(
    convId: number,
    question: string,
    aiAnswer: string,
    sources?: Api.Douyin.KnowledgeSource[]
  ): Promise<number | undefined> {
    try {
      const response = await appendConversationMessages(convId, { question, ai_answer: aiAnswer, sources });
      const data = unwrapServiceData(response, '保存对话消息失败');
      // 刷新列表以更新 message_count
      await loadConversations();
      return data.ai_msg_id;
    } catch (err) {
      console.error('[useConversations] 追加消息失败:', err);
      return undefined;
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
