/**
 * Api Douyin
 *
 * 零食店避坑直播运营复盘系统 — 业务类型定义
 */
declare namespace Api {
  namespace Douyin {
    interface DashboardSummary {
      anchor_count: number;
      session_count: number;
      live_session_count: number;
      detail_complete_count: number;
      detail_completion_rate: number;
      total_viewers: number;
      total_comments: number;
      high_intent_comment_count: number;
      total_private_messages: number;
      total_leads: number;
      total_ad_cost: number;
      average_lead_cost: number;
      open_review_action_count: number;
    }

    /* ---------- 直播间 ---------- */
    interface LiveRoom {
      id: number;
      accountName: string;
      anchorName: string;
      anchorNickname: string | null;
      anchorAvatarUrl: string | null;
      douyinId: string;
      douyinUid: string | null;
      teamName: string;
      status: 'active' | 'inactive';
    }

    /* ---------- 直播场次 ---------- */
    interface LiveSession {
      id: number;
      room_id: number;
      anchor_name: string;
      anchor_nickname: string | null;
      anchor_avatar_url: string | null;
      douyin_id: string | null;
      douyin_uid: string | null;
      detail_collection_status: 'pending' | 'complete' | 'retryable' | 'unavailable' | string;
      detail_collection_error: string | null;
      session_title: string | null;
      dashboard_url: string | null;
      stream_url: string | null;
      live_start_time: string | null;
      live_end_time: string | null;
      live_duration_seconds: number;
      live_status: string;
      total_viewers: number;
      viewed_count: number;
      avg_online_count: number;
      avg_watch_seconds: number;
      fans_avg_watch_seconds: number;
      peak_online_count: number;
      realtime_online_count: number;
      private_message_count: number;
      private_message_longterm_count: number;
      scene_leads_count: number;
      ad_cost: number;
      mini_windmill_click_count: number;
      mini_windmill_click_rate: number;
      card_click_count: number;
      card_click_rate: number;
      new_followers: number;
      follow_rate: number;
      share_count: number;
      share_users: number;
      like_count: number;
      like_users: number;
      comment_users: number;
      interaction_count: number;
      interaction_users: number;
      watch_count: number;
      watch_over_1m_count: number;
      fans_club_join_count: number;
      fans_club_join_rate: number;
      gift_count: number;
      gift_amount: number;
      dislike_count: number;
      dislike_users: number;
      wechat_add_count: number;
      wechat_add_cost: number;
      form_submit_count: number;
      form_submit_users: number;
      form_submit_cost: number;
      exposure_enter_rate: number;
      fans_view_ratio: number;
      scene_lead_conversion_rate: number;
      comment_rate: number;
      interaction_rate: number;
      comments_count: number;
      leads_count: number;
      created_at: string;
      updated_at: string;
    }

    interface LiveMetric {
      metric_time: string;
      exposure_count: number;
      online_count: number;
      enter_count: number;
      enter_fans_count: number;
      leave_count: number;
      like_count: number;
      comment_count: number;
      follow_count: number;
      clue_count: number;
      windmill_click_count: number;
      card_click_count: number;
      wechat_add_count: number;
      form_submit_count: number;
      form_submit_users: number;
      cost_amount: number;
      natural_traffic_count: number;
      marketing_traffic_count: number;
    }

    interface LiveComment {
      id: number;
      session_id: number;
      user_nickname: string | null;
      user_sec_uid: string | null;
      webcast_uid: string | null;
      comment_content: string | null;
      comment_time: string | null;
      is_high_intent: number;
      sentiment: string | null;
      keywords: string | null;
      created_at: string;
    }

    interface LiveSessionDetail {
      session: LiveSession;
      metrics: LiveMetric[];
      comments: LiveComment[];
      profiles: LiveAudienceProfile[];
      stream_url: string | null;
      stream_source_count: number;
    }

    interface LiveAudienceProfile {
      dimension_type: string;
      dimension_name: string;
      ratio: number;
      count: number;
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
      cookie_saved: boolean;
      fingerprint_saved: boolean;
      viewport_width: number | null;
      viewport_height: number | null;
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
      task_type: 'login' | 'collect_all' | 'metrics' | 'comments' | 'leads' | 'profile';
      status: 'pending' | 'running' | 'completed' | 'failed';
      started_at: string | null;
      completed_at: string | null;
      error_message: string | null;
      idempotency_key: string | null;
      trace_id: string | null;
      worker_id: string | null;
      heartbeat_at: string | null;
      retry_count: number;
      max_retries: number;
      priority: number;
      progress_percent: number;
      progress_current: number;
      progress_total: number;
      progress_stage: string | null;
      progress_message: string | null;
      collected_anchor_count: number;
      collected_session_count: number;
      new_session_count: number;
      mapped_session_count: number;
      checked_detail_count: number;
      refreshed_detail_count: number;
      failed_detail_count: number;
      remaining_detail_count: number;
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

    interface AccountHealthResponse {
      account_id: number;
      valid: boolean;
      login_status: 'logged_in' | 'expired';
      checked_at: string;
      message: string;
    }

    interface AsrControlStatus {
      enabled: boolean;
      engine_running: boolean;
      worker_running: boolean;
      queued_count: number;
      processing_count: number;
      message: string;
    }

    interface DataEaseStatus {
      source_session_count: number;
      synced_session_count: number;
      pending_session_count: number;
      outdated_session_count: number;
      coverage_rate: number;
      metric_row_count: number;
      profile_row_count: number;
      comment_summary_count: number;
      transcript_summary_count: number;
      ai_summary_count: number;
      last_synced_at: string | null;
    }

    interface DataEaseSyncResult {
      status: 'ok' | 'partial';
      selected_count: number;
      synced_count: number;
      failed_count: number;
      removed_stale_row_count: number;
      errors: Array<{ session_id: number; message: string }>;
      dataease: DataEaseStatus;
    }

    /* ---------- 监控 ---------- */
    interface MonitorStatus {
      enabled: boolean;
      running: boolean;
      paused_for_collection: boolean;
      mock_mode: boolean;
      active_session_count: number;
      active_sessions: number[];
      last_error: string | null;
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
      id: number | null;
      full_text: string;
      available: boolean;
    }

    interface TranscriptTask {
      id: number;
      session_id: number;
      status: 'queued' | 'processing' | 'completed' | 'failed';
      task_type: string;
      anchor_name: string;
      session_title: string;
      live_start_time: string | null;
      live_duration_seconds: number;
      segment_count: number;
      error_message: string | null;
      retry_count: number;
      max_retries: number;
      started_at: string | null;
      completed_at: string | null;
      created_at: string;
      updated_at: string;
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

    interface ReviewCompletenessComponent {
      name: string;
      weight: number;
      score: number;
      captured: number;
      expected: number;
      status: 'complete' | 'partial' | 'missing';
    }

    interface ReviewCompleteness {
      score: number;
      level: 'complete' | 'usable' | 'insufficient';
      analysis_ready: boolean;
      duration_seconds: number;
      components: ReviewCompletenessComponent[];
    }

    interface ReviewTranscriptSegment {
      id: number;
      segment_start: number;
      segment_end: number;
      text_content: string | null;
      segment_type: string | null;
      ai_score: number | null;
    }

    interface ReviewFinding {
      id: number;
      session_id: number;
      report_id: number | null;
      finding_type: 'observation' | 'opportunity' | 'risk';
      category: string;
      title: string;
      description: string | null;
      severity: 'info' | 'warning' | 'critical';
      start_seconds: number | null;
      end_seconds: number | null;
      evidence_type: 'metric' | 'comment' | 'transcript' | 'session';
      evidence_text: string | null;
      metric_name: string | null;
      metric_before: number | null;
      metric_after: number | null;
      confidence: number;
      source: 'rule' | 'ai' | 'manual';
      status: 'open' | 'confirmed' | 'dismissed' | 'resolved';
      created_at: string;
    }

    interface ReviewAction {
      id: number;
      session_id: number;
      finding_id: number | null;
      title: string;
      description: string | null;
      owner_name: string | null;
      priority: 'low' | 'medium' | 'high';
      status: 'pending' | 'in_progress' | 'completed' | 'verified';
      due_at: string | null;
      verification_session_id: number | null;
      verification_note: string | null;
      created_at: string;
      updated_at: string;
    }

    interface ReviewActionPayload {
      finding_id?: number | null;
      title: string;
      description?: string | null;
      owner_name?: string | null;
      priority?: 'low' | 'medium' | 'high';
      due_at?: string | null;
    }

    interface ScriptAsset {
      id: number;
      session_id: number;
      transcript_segment_id: number | null;
      category: string;
      title: string;
      content: string;
      start_seconds: number | null;
      end_seconds: number | null;
      performance_note: string | null;
      status: 'candidate' | 'approved' | 'archived';
      created_at: string;
      updated_at: string;
    }

    interface ScriptAssetPayload {
      transcript_segment_id?: number | null;
      category: string;
      title: string;
      content: string;
      start_seconds?: number | null;
      end_seconds?: number | null;
      performance_note?: string | null;
      status?: 'candidate' | 'approved' | 'archived';
    }

    interface DomainCoverageItem {
      category: string;
      covered: boolean;
      segment_count: number;
      first_seconds: number | null;
    }

    interface ReviewLiveAlert {
      key: string;
      severity: 'info' | 'warning' | 'critical';
      title: string;
      description: string;
      start_seconds: number | null;
    }

    interface ReviewLatestReport {
      id: number;
      report_type: string;
      report_title: string | null;
      summary: string | null;
      report_content: Record<string, unknown> | null;
      created_at: string;
    }

    interface ReviewWorkbench {
      session_id: number;
      business_context: string;
      completeness: ReviewCompleteness;
      transcript_segments: ReviewTranscriptSegment[];
      domain_coverage: DomainCoverageItem[];
      findings: ReviewFinding[];
      actions: ReviewAction[];
      script_assets: ScriptAsset[];
      live_alerts: ReviewLiveAlert[];
      latest_reports: ReviewLatestReport[];
    }

    interface ComparisonDimension {
      key: string;
      label: string;
      current: number;
      baseline: number;
      delta: number;
      delta_rate: number | null;
    }

    interface ComparisonSeriesPoint {
      minute: number;
      online_count: number;
      comment_count: number;
      clue_count: number;
      follow_count: number;
    }

    interface ComparisonSession {
      id: number;
      anchor_name: string | null;
      session_title: string | null;
      live_start_time: string | null;
      duration_seconds: number;
      completeness: number;
    }

    interface SessionComparison {
      current: ComparisonSession;
      baseline: ComparisonSession;
      dimensions: ComparisonDimension[];
      current_series: ComparisonSeriesPoint[];
      baseline_series: ComparisonSeriesPoint[];
      comparison_note: string;
    }

    /* ---------- 知识库 ---------- */
    interface KnowledgeItem {
      id: number;
      session_id: number | null;
      title: string | null;
      category: string | null;
      content: string | null;
      source_type: string | null;
      created_at: string;
    }

    interface KnowledgeSource {
      id: number;
      title: string | null;
      category: string | null;
      source_type: string | null;
      session_id: number | null;
      anchor_name?: string | null;
      time_range?: string;
      slice_start_seconds?: number;
      slice_end_seconds?: number;
      source_types?: string[];
      excerpt?: string;
      score?: number;
    }

    interface KnowledgeSyncResult {
      status: string;
      live_data_saved: number;
      comments_saved: number;
      transcript_saved: number;
      analysis_saved: number;
      time_slices_created: number;
      time_slices_updated: number;
      time_slices_unchanged: number;
      time_slices_total: number;
      unmapped_comments: number;
    }

    interface KnowledgeTimeSliceStatus {
      slice_count: number;
      session_count: number;
      transcript_slice_count: number;
      comment_slice_count: number;
      metric_slice_count: number;
      unmapped_comment_count: number;
      slice_seconds: number;
      parser_version: string;
    }

    interface KnowledgeTimeSlice {
      id: number;
      session_id: number;
      anchor_name: string | null;
      session_title: string | null;
      slice_start_seconds: number;
      slice_end_seconds: number;
      slice_start_time: string | null;
      slice_end_time: string | null;
      transcript_text: string | null;
      comments_text: string | null;
      comment_count: number;
      high_intent_comment_count: number;
      unmapped_comment_count: number;
      metric_point_count: number;
      avg_online_count: number;
      peak_online_count: number;
      updated_at: string;
    }

    /* ---------- 刷新数据采集 ---------- */
    interface CollectRoomResult {
      room_id: string;
      anchor_name: string;
      anchor_nickname: string;
      douyin_id: string;
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
      history_synced_count: number;
      enterprise_anchor_count: number;
      enterprise_session_synced_count: number;
      enterprise_session_discovered_count: number;
      anchor_profile_synced_count: number;
      unmapped_session_pruned_count: number;
      history_detail_synced_count: number;
      history_detail_checked_count: number;
      history_detail_remaining_count: number;
      history_detail_batch_size: number;
      history_detail_failed_count: number;
      dataease_synced_count: number;
      dataease_failed_count: number;
      asr_queued_count: number;
      asr_active_count: number;
      asr_queue_capacity: number;
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
