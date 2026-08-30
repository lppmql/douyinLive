/**
 * Api Douyin
 *
 * 零食店避坑直播运营复盘系统 — 业务类型定义
 */
declare namespace Api {
  namespace Douyin {
    /** 验证码登录响应（对应后端 TokenData） */
    interface TokenResponse {
      token: string;
      refreshToken: string;
    }

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
      private_message_rate: number;
      lead_conversion_rate: number;
      total_exposure_users: number;
      total_enter_users: number;
      total_card_click_users: number;
      open_review_action_count: number;
    }

    interface AnchorSummaryItem {
      anchor_key: string;
      douyin_id: string;
      anchor_name: string;
      anchor_avatar_url: string;
      anchor_avatar_session_id: number | null;
      session_count: number;
      total_viewers: number;
      total_comments: number;
      total_private_messages: number;
      total_leads: number;
      total_ad_cost: number;
      total_interactions: number;
      total_new_followers: number;
    }

    interface AnchorSummaryResponse {
      anchors: AnchorSummaryItem[];
      total: Record<string, number>;
    }

    interface DashboardTrendPoint {
      date_key: string;
      session_count: number;
      total_viewers: number;
      total_comments: number;
      total_private_messages: number;
      total_leads: number;
      total_ad_cost: number;
    }

    interface DashboardFunnelStep {
      label: string;
      value: number;
      step_rate: number;
    }

    interface DashboardSessionItem {
      id: number;
      anchor_name: string;
      anchor_avatar_url: string;
      douyin_id: string;
      session_title: string;
      live_start_time: string | null;
      live_duration_seconds: number;
      total_viewers: number;
      total_comments: number;
      total_private_messages: number;
      total_leads: number;
      total_ad_cost: number;
      lead_cost: number;
    }

    interface DashboardOperations {
      summary: DashboardSummary;
      anchors: AnchorSummaryItem[];
      trend: DashboardTrendPoint[];
      funnel: DashboardFunnelStep[];
      recent_sessions: DashboardSessionItem[];
    }

    /* ---------- 主播排班 ---------- */
    type AnchorScheduleStatus = 'upcoming' | 'live' | 'completed' | 'missing' | 'duration_short' | 'invalid' | 'extra';

    interface AnchorScheduleActualSession {
      id: number;
      anchor_name: string | null;
      anchor_avatar_url: string | null;
      live_start_time: string | null;
      live_end_time: string | null;
      live_duration_seconds: number;
      live_status: string;
    }

    interface AnchorScheduleRow {
      id: number;
      schedule_date: string;
      source_anchor_name: string;
      display_name: string;
      room_name: string;
      network_name: string | null;
      session_index: number;
      extra_index: number | null;
      is_extra: boolean;
      planned_start_time: string | null;
      planned_end_time: string | null;
      expected_duration_minutes: number;
      status: AnchorScheduleStatus;
      warnings: string[];
      actual_session: AnchorScheduleActualSession | null;
    }

    interface AnchorScheduleReminder {
      type: 'missing' | 'invalid' | 'duration' | 'cross_hour';
      severity: 'warning' | 'error';
      anchor_name: string;
      session_index: number;
      message: string;
      schedule_date: string;
      planned_start_time: string | null;
      session_id: number | null;
      is_extra: boolean;
    }

    interface AnchorScheduleAnchor {
      source_anchor_name: string;
      display_name: string;
      room_name: string;
      network_name: string | null;
      expected_count: number;
      matched_count: number;
      completed_count: number;
      warning_count: number;
      missing_count: number;
      missing_by_date: Array<{
        schedule_date: string;
        count: number;
        session_indexes: number[];
      }>;
      invalid_count: number;
      invalid_by_date: Array<{
        schedule_date: string;
        count: number;
        session_ids: number[];
        live_start_times: Array<string | null>;
        durations_seconds: number[];
        extra_flags: boolean[];
      }>;
      extra_count: number;
      extra_by_date: Array<{
        schedule_date: string;
        count: number;
        session_ids: number[];
        live_start_times: string[];
      }>;
      anchor_avatar_url: string | null;
      anchor_avatar_session_id: number | null;
      actual_anchor_name: string | null;
    }

    interface AnchorScheduleDashboard {
      schedule_date: string;
      start_date: string;
      end_date: string;
      day_count: number;
      generated_at: string;
      source_name: string;
      rule: {
        expected_duration_minutes: number;
        minimum_valid_duration_minutes: number;
        four_session_anchors: string[];
        default_session_count: number;
        cross_hour_definition: string;
      };
      summary: {
        planned_count: number;
        matched_count: number;
        completed_count: number;
        live_count: number;
        upcoming_count: number;
        missing_count: number;
        duration_short_count: number;
        invalid_count: number;
        extra_count: number;
        cross_hour_count: number;
        duration_compliant_count: number;
        reminder_count: number;
      };
      anchors: AnchorScheduleAnchor[];
      rows: AnchorScheduleRow[];
      reminders: AnchorScheduleReminder[];
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
      share_rate: number;
      like_rate: number;
      comment_rate: number;
      interaction_rate: number;
      natural_traffic_ratio: number;
      marketing_traffic_ratio: number;
      other_traffic_ratio: number;
      live_exposure_users: number;
      live_enter_users: number;
      card_click_users: number;
      comments_count: number;
      leads_count: number;
      created_at: string;
      updated_at: string;
    }

    type LiveSessionListItem = Pick<
      LiveSession,
      | 'id'
      | 'anchor_name'
      | 'anchor_nickname'
      | 'anchor_avatar_url'
      | 'douyin_id'
      | 'session_title'
      | 'detail_collection_status'
      | 'detail_collection_error'
      | 'live_start_time'
      | 'live_end_time'
      | 'live_duration_seconds'
      | 'live_status'
      | 'peak_online_count'
      | 'new_followers'
      | 'comments_count'
      | 'leads_count'
    >;

    interface LiveSessionAnchorOption {
      anchor_key: string;
      anchor_name: string;
      anchor_nickname: string | null;
      anchor_avatar_url: string | null;
      douyin_id: string | null;
      douyin_uid: string | null;
      latest_session_id: number;
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
      user_avatar_url: string | null;
      user_douyin_id: string | null;
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
      transcript_quality: TranscriptQuality;
      conversion_summary: ConversionSummary;
      hook_events: HookEvent[];
      audience_users: AudienceUserInsight[];
      data_coverage: SessionDataCoverage;
      unified_ai_review: UnifiedAiReview | null;
    }

    interface ConversionSummary {
      hook_count: number;
      effective_hook_count: number;
      strong_hook_count: number;
      incomplete_hook_count: number;
      session_lead_count: number;
      hook_window_lead_count: number;
      exact_matched_user_count: number;
      comment_user_count: number;
    }

    interface HookEvent {
      id: number;
      start_seconds: number;
      end_seconds: number;
      hook_types: string[];
      is_formal_hook: boolean;
      stage: '正式钩子' | '钩子铺垫' | string;
      strength: 'strong' | 'medium' | 'weak';
      missing_elements: string[];
      evidence_text: string;
      related_lead_count: number;
      comment_after_5m: number;
      comment_after_15m: number;
      comment_after_30m: number;
      lead_after_5m: number;
      lead_after_15m: number;
      lead_after_30m: number;
      high_intent_user_count: number;
      attribution_label: string;
    }

    interface AudienceUserInsight {
      identity_key: string;
      user_nickname: string | null;
      user_avatar_comment_id: number | null;
      user_douyin_id: string | null;
      user_unique_id: string | null;
      user_short_id: string | null;
      douyin_id_type: 'unique_id' | 'short_id' | null;
      profile_status: 'pending' | 'running' | 'success' | 'partial' | 'failed' | 'blocked' | string;
      comment_count: number;
      comments: Array<{ id: number; content: string; comment_time: string | null }>;
      intent_topics: string[];
      intent_level: 'high' | 'medium' | 'low';
      has_lead: boolean;
      lead_match_method: 'douyin_id_exact' | 'unique_id_exact' | 'short_id_exact' | null;
      lead_time: string | null;
      lead_contacts: Array<{
        type: 'phone' | 'wechat';
        value: string;
        converted_at: string | null;
        gap_seconds: number;
      }>;
      host_responded: boolean;
      hook_action_detected: boolean;
      host_evidence: string | null;
      related_hook_ids: number[];
      recommendation: string;
      ai_analysis: UnifiedAiUserAnalysis | null;
    }

    interface UnifiedAiEvidence {
      evidence_id: string;
      conclusion: string;
      reason: string;
      text?: string;
      time?: string | null;
      second?: number | null;
    }

    interface UnifiedAiUserAnalysis {
      id: number;
      identity_key: string;
      user_nickname: string | null;
      business_stage:
        | 'preparing'
        | 'selecting_location'
        | 'comparing_brand'
        | 'opened_store'
        | 'suspected_paid'
        | 'unknown';
      follow_up_status: 'not_lead' | 'confirmed_lead' | 'suspected_contacted' | 'unknown';
      demand_scope: 'snack_store' | 'non_snack_store' | 'industry_peer' | 'unknown';
      interaction_type:
        | 'normal_inquiry'
        | 'high_intent'
        | 'rational_question'
        | 'malicious'
        | 'casual'
        | 'information_insufficient';
      precision_status:
        | 'precision_new_lead'
        | 'nurture'
        | 'existing_store'
        | 'in_follow_up'
        | 'existing_customer'
        | 'non_target'
        | 'industry_peer'
        | 'malicious'
        | 'information_insufficient';
      is_precision_lead: boolean;
      exclusion_reason: string | null;
      host_response_status: 'excellent' | 'effective' | 'average' | 'irrelevant' | 'no_response' | 'unknown';
      host_response_score: number | null;
      missed_opportunity: boolean;
      recommendation: string;
      suggested_reply: string | null;
      confidence: number;
      evidence: UnifiedAiEvidence[];
      manual_confirmed: boolean;
      user_avatar_comment_id: number | null;
      user_douyin_id: string | null;
      douyin_id_type: 'unique_id' | 'short_id' | null;
      profile_status: string;
      has_lead: boolean;
      lead_match_method: 'douyin_id_exact' | 'unique_id_exact' | 'short_id_exact' | null;
      lead_time: string | null;
      lead_contacts: Array<{
        type: 'phone' | 'wechat';
        value: string;
        converted_at: string | null;
        gap_seconds: number;
      }>;
    }

    interface UnifiedAiReview {
      status: 'pending' | 'running' | 'completed' | 'failed' | 'stale';
      analysis_version: string;
      model_name: string | null;
      input_hash: string;
      summary: {
        precision_new_lead_count?: number;
        confirmed_lead_count?: number;
        precision_unconverted_count?: number;
        opened_store_count?: number;
        suspected_paid_count?: number;
        suspected_contacted_count?: number;
        non_target_count?: number;
        rational_question_count?: number;
        malicious_count?: number;
        missed_opportunity_count?: number;
        response_counts?: Record<string, number>;
        summary?: string;
        strengths?: string[];
        problems?: string[];
        next_actions?: string[];
      };
      analyzed_user_count: number;
      completed_at: string | null;
      error_message: string | null;
      users: UnifiedAiUserAnalysis[];
    }

    interface SessionDataCoverage {
      comment_count: number;
      analysis_comment_count: number;
      analysis_truncated: boolean;
      comment_user_count: number;
      avatar_user_count: number;
      douyin_id_user_count: number;
      transcript_segment_count: number;
      session_lead_count: number;
      avatar_coverage_percent: number;
      douyin_id_coverage_percent: number;
      profile_enrichment_status: string;
      profile_enrichment_completed: number;
      profile_enrichment_total: number;
    }

    interface CommentProfileEnrichmentStatus {
      status: 'idle' | 'starting' | 'running' | 'completed' | 'failed' | 'blocked';
      scope: string | null;
      total: number;
      completed: number;
      success: number;
      partial: number;
      failed: number;
      message: string;
      configured: boolean;
      cookie_file_secure: boolean;
      fingerprint_configured: boolean;
      batch_size: number;
      request_interval_seconds: number;
      cooldown_seconds: number;
    }

    interface TranscriptQuality {
      status: 'complete' | 'incomplete' | 'repairing' | 'repair_failed' | 'waiting_duration' | 'waiting_transcript';
      coverage_percent: number | null;
      covered_seconds: number;
      duration_seconds: number;
      missing_ranges: [number, number][];
      speech_char_count: number;
      speech_seconds: number;
      speech_rate_cpm: number | null;
      rate_source: 'offline_final' | 'realtime_estimate';
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
      douyin_nickname: string | null;
      douyin_id: string | null;
      login_status: 'logged_in' | 'expired' | 'never';
      cookie_status: 'valid' | 'expired' | 'unchecked' | 'missing';
      cookie_saved: boolean;
      fingerprint_saved: boolean;
      viewport_width: number | null;
      viewport_height: number | null;
      last_login_at: string | null;
      cookie_checked_at: string | null;
      cookie_refreshed_at: string | null;
      expires_at: string | null;
      created_at: string;
      updated_at: string;
    }

    interface CollectorLog {
      id: number;
      task_id: number | null;
      level: 'info' | 'warn' | 'error';
      message: string | null;
      raw_json: unknown;
      session_id: number | null;
      anchor_name: string | null;
      anchor_nickname: string | null;
      anchor_avatar_url: string | null;
      douyin_id: string | null;
      session_title: string | null;
      live_start_time: string | null;
      room_id_str: string | null;
      task_type: string | null;
      event_type: string | null;
      stage: string | null;
      data_details: Record<string, unknown>;
      created_at: string;
    }

    interface CollectorTask {
      id: number;
      account_id: number | null;
      session_id: number | null;
      task_type: 'login' | 'collect_all' | 'live_detail' | 'metrics' | 'comments' | 'leads' | 'profile';
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
      cookie_status: 'valid' | 'expired' | 'unchecked' | 'missing';
      douyin_nickname: string | null;
      douyin_id: string | null;
      checked_at: string;
      message: string;
    }

    type CollectorModuleKey = 'data_refresh' | 'monitor' | 'asr' | 'ai_review' | 'knowledge';

    interface CollectorModuleStatus {
      key: CollectorModuleKey;
      label: string;
      mode: 'action' | 'service' | 'automatic';
      enabled: boolean;
      running: boolean;
      status: string;
      pending_count: number;
      processing_count: number;
      completed_count: number;
      failed_count: number;
      summary: string;
      disabled_reason: string;
      interval_seconds: number;
      enabled_at: string | null;
      last_scheduled_at: string | null;
      next_run_at: string | null;
    }

    interface ResourceComponentUsage {
      key: string;
      label: string;
      running: boolean;
      cpu_percent: number;
      memory_bytes: number;
    }

    interface ComputerResourceUsage {
      sampled_at: string;
      cpu_percent: number;
      memory_percent: number;
      memory_used_bytes: number;
      memory_total_bytes: number;
      disk_used_percent: number;
      disk_free_bytes: number;
      app_memory_bytes: number;
      pressure_level: 'normal' | 'high' | 'critical';
      pressure_message: string;
      components: ResourceComponentUsage[];
    }

    interface UnifiedCollectorTask {
      task_key: string;
      source: 'scraper' | 'asr';
      id: number;
      module_key: CollectorModuleKey;
      task_type: string;
      task_label: string;
      status: 'pending' | 'queued' | 'running' | 'processing' | 'completed' | 'failed' | 'cancelled';
      progress_percent: number;
      progress_current: number;
      progress_total: number;
      progress_stage: string | null;
      progress_message: string | null;
      account_id: number | null;
      session_id: number | null;
      anchor_name: string | null;
      anchor_nickname: string | null;
      anchor_avatar_url: string | null;
      douyin_id: string | null;
      session_title: string | null;
      error_message: string | null;
      trace_id: string | null;
      worker_id: string | null;
      heartbeat_at: string | null;
      retry_count: number;
      max_retries: number;
      retry_of_task_id: number | null;
      can_stop: boolean;
      can_retry: boolean;
      created_at: string;
      started_at: string | null;
      completed_at: string | null;
      result_json: Record<string, unknown> | null;
      collected_anchor_count: number;
      collected_session_count: number;
      new_session_count: number;
      checked_detail_count: number;
      refreshed_detail_count: number;
      failed_detail_count: number;
      remaining_detail_count: number;
    }

    interface CollectorControlCenter {
      modules: CollectorModuleStatus[];
      current_task: UnifiedCollectorTask | null;
      active_task_count: number;
      queued_task_count: number;
      latest_task: UnifiedCollectorTask | null;
      resource_usage: ComputerResourceUsage;
    }

    interface LeadSyncStatus {
      configured: boolean;
      source_system: 'kezi';
      status: 'not_configured' | 'idle' | 'running' | 'completed' | 'failed';
      last_external_id: number;
      last_synced_at: string | null;
      last_error: string | null;
      synced_count: number;
      duplicate_count: number;
      pending_count: number;
      interval_seconds: number;
    }

    interface LeadSyncResult {
      success: boolean;
      added_count: number;
      duplicate_count: number;
      matched_count: number;
      pending_count: number;
      last_external_id: number;
      page_count: number;
    }

    interface CollectorTaskAction {
      success: boolean;
      message: string;
      task: UnifiedCollectorTask | null;
    }

    interface AsrControlStatus {
      enabled: boolean;
      engine_running: boolean;
      worker_running: boolean;
      worker_healthy: boolean;
      worker_status: 'healthy' | 'stale' | 'stopped' | string;
      worker_heartbeat_at: number | null;
      worker_heartbeat_age_seconds: number | null;
      queued_count: number;
      processing_count: number;
      postprocess_pending_count: number;
      postprocess_processing_count: number;
      postprocess_completed_count: number;
      postprocess_failed_count: number;
      message: string;
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
      compliance_hits: TranscriptComplianceHit[];
    }

    interface TranscriptComplianceHit {
      rule_code: string;
      name: string;
      category: string;
      matched_keyword: string;
      severity: 'warning' | 'critical' | string;
      guidance: string;
      review_status: 'suspected';
    }

    interface TranscriptFullText {
      id: number | null;
      full_text: string;
      available: boolean;
    }

    interface TranscriptTask {
      id: number;
      session_id: number;
      status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
      task_type: 'realtime' | 'offline';
      queue_source: 'auto' | 'manual';
      priority: number;
      queue_position: number | null;
      cancel_requested: boolean;
      anchor_name: string;
      session_title: string;
      live_start_time: string | null;
      live_duration_seconds: number;
      segment_count: number;
      error_message: string | null;
      postprocess_status: 'pending' | 'processing' | 'completed' | 'failed' | 'skipped';
      postprocess_error: string | null;
      postprocess_result: Record<string, unknown> | null;
      postprocess_attempt_count: number;
      postprocess_started_at: string | null;
      postprocess_completed_at: string | null;
      retry_count: number;
      max_retries: number;
      started_at: string | null;
      completed_at: string | null;
      created_at: string;
      updated_at: string;
      /** 音频分片总数（转写进度分母） */
      total_chunks: number;
      /** 已处理音频分片数（包含因时长修正而安全跳过的技术分片） */
      completed_chunks: number;
      /** 转写进度百分比 0-100 */
      progress_percent: number;
    }

    interface TranscriptTaskSummary {
      queued: number;
      processing: number;
      completed: number;
      failed: number;
      cancelled: number;
      needs_attention: number;
    }

    interface TranscriptTaskAction {
      task_id: number;
      status: TranscriptTask['status'];
      queue_source: TranscriptTask['queue_source'];
      message: string;
    }

    interface TranscriptDispatchPolicy {
      order_mode: 'smart' | 'latest' | 'fifo';
      manual_active: boolean;
      manual_task_id: number | null;
      manual_session_id: number | null;
      auto_scope_timezone: string;
      auto_scope_description: string;
    }

    interface AnalysisReport {
      id: number;
      session_id: number;
      report_type: 'speech_score' | 'optimization' | 'anomaly' | 'trend' | string;
      report_title: string | null;
      summary: string | null;
      report_content: Record<string, unknown> | null;
      created_at: string;
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
      asr_status: 'pending' | 'processing' | 'completed' | 'failed';
      compliance_hits: TranscriptComplianceHit[];
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
      unified_ai_review: UnifiedAiReview | null;
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
      anchor_nickname?: string | null;
      anchor_avatar_url?: string | null;
      douyin_id?: string | null;
      time_range?: string;
      slice_start_seconds?: number;
      slice_end_seconds?: number;
      source_types?: string[];
      excerpt?: string;
      score?: number;
    }

    interface KnowledgeChatHistory {
      role: 'user' | 'assistant';
      content: string;
    }

    interface KnowledgeSyncResult {
      status: string;
      live_data_saved: number;
      comments_saved: number;
      transcript_saved: number;
      analysis_saved: number;
      review_saved: number;
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
      high_intent_slice_count: number;
      unmapped_comment_count: number;
      knowledge_item_count: number;
      latest_updated_at: string | null;
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

    /* ---------- 对话历史 ---------- */
    interface ConversationListItem {
      id: number;
      session_id: number | null;
      title: string | null;
      message_count: number;
      created_at: string | null;
      updated_at: string | null;
    }

    interface ConversationMessage {
      id: number;
      role: 'user' | 'assistant';
      content: string;
      sources: KnowledgeSource[] | null;
      feedback: 'like' | 'dislike' | null;
      error: boolean;
      created_at: string | null;
    }

    interface ConversationDetail {
      id: number;
      session_id: number | null;
      title: string | null;
      messages: ConversationMessage[];
      created_at: string | null;
      updated_at: string | null;
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
      asr_queued_count: number;
      asr_active_count: number;
      asr_queue_capacity: number;
      postprocess_pending_count: number;
      postprocess_processing_count: number;
      postprocess_completed_count: number;
      postprocess_failed_count: number;
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
      knowledge_value_score?: number;
      total_score: number;
      strengths: string[];
      weaknesses: string[];
      suggestions: string[];
      evidence?: AiScoreEvidence[];
    }

    interface AiScoreEvidence {
      quote: string;
      category: string;
      start_seconds: number | null;
    }

    interface AiOptimizationFinding {
      category?: string;
      title?: string;
      evidence?: string;
      start_seconds?: number | null;
      severity?: 'info' | 'warning' | 'critical' | string;
    }

    interface AiNextLivePlan {
      stage?: string;
      action?: string;
      success_metric?: string;
    }

    interface AiOptimizationResult {
      summary?: string;
      findings?: AiOptimizationFinding[];
      suggestions?: string[];
      next_live_plan?: AiNextLivePlan[];
      compliance_notes?: string[];
      [key: string]: unknown;
    }

    interface QaResult {
      answer: string;
      sources: { id: number; title: string | null; category: string | null }[];
      has_result: boolean;
    }

    /* ---------- AI 自动剪辑 ---------- */

    interface ClipSegment {
      start: number;
      end: number;
      text: string;
      transcript_segment_id?: number | null;
      words?: Array<{ text: string; start: number; end: number }>;
      subtitle_precision?: 'funasr_exact' | 'funasr_aligned' | 'funasr_remapped' | 'segment_estimated';
    }

    interface ClipClip {
      id: number;
      session_id: number;
      clip_order: number;
      status: 'draft' | 'approved' | 'discarded' | 'failed';
      title: string | null;
      theme: string | null;
      description: string | null;
      topics: string[];
      segments: ClipSegment[];
      duration_seconds: number | null;
      video_path: string | null;
      cover_path: string | null;
      subtitle_path: string | null;
      subtitle_srt_path: string | null;
      subtitle_precision: 'funasr_exact' | 'funasr_aligned' | 'funasr_remapped' | 'segment_estimated';
      render_version: number;
      can_rerender_subtitle: boolean;
      artifact_versions: Array<Record<string, unknown>>;
      selection_evidence: {
        signal_score?: number;
        segments?: Array<{
          transcript_segment_id?: number | null;
          signal_score?: number;
          comment_count?: number;
          high_intent_comment_count?: number;
          hook_count?: number;
          hook_strength?: string | null;
          hook_types?: string[];
          related_lead_count?: number;
          lead_after_5m_count?: number;
          attribution_label?: string;
        }>;
      };
      qc: Record<string, unknown>;
      is_manual: number;
      error_message: string | null;
      created_at: string | null;
      updated_at: string | null;
    }

    interface ClipTaskInfo {
      id: number;
      status: string;
      progress_percent: number;
      progress_stage: string | null;
      progress_message: string | null;
      error_message: string | null;
      created_at: string | null;
      completed_at: string | null;
    }

    interface ClipSessionOverview {
      session_id: number;
      session_title: string | null;
      anchor_name: string | null;
      anchor_nickname: string | null;
      anchor_avatar_url: string | null;
      douyin_id: string | null;
      live_start_time: string | null;
      live_duration_seconds: number | null;
      detail_collection_status: string | null;
      task: ClipTaskInfo | null;
      clips: ClipClip[];
    }

    interface ClipTaskListResult {
      total: number;
      items: Array<Record<string, unknown>>;
    }

    interface ClipActionResult {
      success: boolean;
      message: string;
      task: ClipTaskInfo | null;
    }

    interface ClipStats {
      pending_confirm_count: number;
      failed_task_count: number;
      storage_root: string;
      storage_available: boolean;
      subtitle_precision_counts: Record<string, number>;
      precise_clip_count: number;
      estimated_clip_count: number;
      publish_ready_count: number;
      subtitle_health: 'healthy' | 'degraded';
      estimated_approval_enabled: boolean;
      replay_count: number;
      replay_bytes: number;
      replay_cleanup_enabled: boolean;
      replay_capacity_exceeded: boolean;
      replay_retention_days: number;
      replay_max_gb: number;
    }

    interface ClipCandidateSession {
      session_id: number;
      session_title: string | null;
      anchor_name: string | null;
      anchor_nickname: string | null;
      anchor_avatar_url: string | null;
      douyin_id: string | null;
      live_start_time: string | null;
      live_duration_seconds: number | null;
      transcript_segment_count: number;
      transcript_completed_count: number;
      transcript_status: 'none' | 'processing' | 'partial' | 'completed';
      clip_count: number;
      clip_available_count: number;
      clip_status: 'none' | 'has_clips';
    }

    interface ReviewReadinessFunnel {
      steps: Array<{ key: string; label: string; count: number }>;
      lead_attribution: { total: number; attributed: number; pending: number; rate: number };
    }

    interface PendingLeadPairCandidate {
      session_id: number;
      session_title: string | null;
      anchor_name: string | null;
      live_start_time: string | null;
      live_end_time: string | null;
      distance_seconds: number;
    }

    interface PendingLeadPair {
      id: number;
      anchor_name: string;
      douyin_id: string;
      contact_type: 'phone' | 'wechat';
      contact_value: string;
      converted_at: string;
      gap_seconds: number;
      candidate_sessions: PendingLeadPairCandidate[];
    }
  }
}
