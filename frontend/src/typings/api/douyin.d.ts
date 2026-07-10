/**
 * Api Douyin
 *
 * 抖音留资直播数据分析系统 — 业务类型定义
 */
declare namespace Api {
  namespace Douyin {
    /* ---------- 直播间 ---------- */
    interface LiveRoom {
      id: number;
      accountName: string;
      anchorName: string;
      douyinId: string;
      teamName: string;
      status: 'active' | 'inactive';
    }

    /* ---------- 直播场次 ---------- */
    interface LiveSession {
      id: number;
      room_id: number;
      anchor_name: string;
      session_title: string | null;
      dashboard_url: string | null;
      stream_url: string | null;
      live_start_time: string | null;
      live_end_time: string | null;
      live_duration_seconds: number;
      live_status: string;
      total_viewers: number;
      avg_watch_seconds: number;
      peak_online_count: number;
      realtime_online_count: number;
      ad_cost: number;
      new_followers: number;
      exposure_enter_rate: number;
      comment_rate: number;
      interaction_rate: number;
      comments_count: number;
      leads_count: number;
      created_at: string;
      updated_at: string;
    }

    /* ---------- 采集（后端返回 snake_case） ---------- */
    interface CollectorStatus {
      connected: boolean;
      active_task_count: number;
      default_account: CollectorAccount | null;
    }

    interface CollectorAccount {
      id: number;
      account_name: string | null;
      douyin_id: string | null;
      login_status: 'logged_in' | 'expired' | 'never';
      storage_state_path: string | null;
      last_login_at: string | null;
      expires_at: string | null;
      created_at: string;
    }

    interface CollectorLog {
      id: number;
      task_id: number | null;
      level: 'info' | 'warn' | 'error';
      message: string | null;
      raw_json: unknown;
      created_at: string;
    }

    interface CollectorTask {
      id: number;
      account_id: number | null;
      session_id: number | null;
      task_type: 'login' | 'metrics' | 'comments' | 'leads' | 'profile';
      status: 'pending' | 'running' | 'completed' | 'failed';
      started_at: string | null;
      completed_at: string | null;
      error_message: string | null;
      created_at: string;
    }

    interface LoginStartResponse {
      task_id: number;
      message: string;
    }

    interface LoginStatusResponse {
      status: 'pending' | 'scanning' | 'success' | 'failed' | 'timeout' | 'not_found';
      account: CollectorAccount | null;
      message: string;
    }

    /* ---------- 监控 ---------- */
    interface MonitorStatus {
      enabled: boolean;
      running: boolean;
      mock_mode: boolean;
      active_session_count: number;
      active_sessions: number[];
    }

    interface MonitorAction {
      success: boolean;
      message: string;
    }

    interface MonitorRoom {
      room_id: number;
      account_name: string | null;
      anchor_name: string | null;
      monitored: boolean;
    }

    /* ---------- 话术/ASR ---------- */
    interface TranscriptSegment {
      id: number;
      session_id: number;
      segment_start: number;
      segment_end: number;
      text_content: string;
      segment_type: string;
      asr_status: 'pending' | 'processing' | 'completed' | 'failed';
      ai_score: number | null;
    }

    interface TranscriptFullText {
      id: number;
      full_text: string;
    }

    /* ---------- AI 分析 ---------- */
    interface AnalysisScore {
      completeness: number;
      interactivity: number;
      leadGuidance: number;
      overall: number;
    }

    interface AlertItem {
      key: string;
      title: string;
      desc: string;
      type: 'warning' | 'error' | 'info';
    }

    /* ---------- 知识库 ---------- */
    interface KnowledgeItem {
      id: number;
      title: string;
      category: string;
      summary: string;
      source: string;
      time: string;
    }

    /* ---------- 一键采集 ---------- */
    interface CollectRoomResult {
      room_id: string;
      anchor_name: string;
      is_live: boolean;
      metrics_count: number;
      comments_count: number;
      profiles_count: number;
      session_id: number | null;
      error: string | null;
    }

    interface CollectAllResponse {
      total_rooms: number;
      collected_rooms: number;
      results: CollectRoomResult[];
      message: string | null;
    }

    /* ---------- AI 分析 ---------- */
    interface PromptTemplate {
      id: number;
      type: string;
      name: string | null;
      content: string;
      version: number;
      description: string | null;
      created_at: string | null;
    }

    interface AiScoreResult {
      completeness_score: number;
      interactivity_score: number;
      lead_guidance_score: number;
      affinity_score?: number;
      total_score: number;
      strengths: string[];
      weaknesses: string[];
      suggestions: string[];
    }

    interface QaResult {
      answer: string;
      sources: { id: number; title: string | null; category: string | null }[];
      has_result: boolean;
    }
  }
}
