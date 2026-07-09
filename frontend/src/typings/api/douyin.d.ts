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
      roomId: number;
      anchorName: string;
      startTime: string;
      endTime: string | null;
      duration: number;
      onlineUsers: number;
      viewCount: number;
      totalLeads: number;
      validLeads: number;
      newFollowers: number;
      trafficSource: TrafficSource[];
      conversion: ConversionStep[];
    }

    interface TrafficSource {
      label: string;
      value: number;
    }

    interface ConversionStep {
      step: string;
      count: number;
    }

    /* ---------- 采集 ---------- */
    interface CollectorStatus {
      connected: boolean;
      connectTime: string;
      accountName: string;
    }

    interface CollectorAccount {
      id: number;
      name: string;
      douyinId: string;
      status: 'valid' | 'expired';
      lastLogin: string;
    }

    interface CollectorLog {
      id: number;
      time: string;
      level: 'info' | 'warn' | 'error';
      message: string;
    }

    /* ---------- 话术 ---------- */
    interface TranscriptSegment {
      id: number;
      sessionId: number;
      timePoint: string;
      content: string;
      duration: number;
      score: number;
      label: string;
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
  }
}
