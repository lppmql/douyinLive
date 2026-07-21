// Api 是全局命名空间（douyin.d.ts 中 declare namespace Api），无需 import
import { toStringArray, toNumber } from '@/utils/analysisHelpers';

/**
 * AI 报告解析适配器
 *
 * 把后端返回的原始 AnalysisReport（report_content 是任意 JSON）
 * 解析为前端类型安全的 AiScoreResult / AiOptimizationResult。
 *
 * 核心逻辑：
 * 1. parseScoreReport  —— 从 report_content 提取五维评分 + 证据
 * 2. parseOptimizationReport —— 提取优化建议，兼容 summary 字段缺失
 * 3. restoreSavedReports —— 从报告列表恢复评分和优化结果
 */

/** 把原始报告内容解析为标准 AiScoreResult，解析失败返回 null */
export function parseScoreReport(
  report?: Api.Douyin.AnalysisReport
): Api.Douyin.AiScoreResult | null {
  const content = report?.report_content;
  // report_content 可能是字符串（旧格式）或对象，且必须有 total_score 才算有效评分
  if (!content || typeof content.total_score !== 'number') return null;

  return {
    completeness_score: toNumber(content.completeness_score),
    interactivity_score: toNumber(content.interactivity_score),
    lead_guidance_score: toNumber(content.lead_guidance_score),
    affinity_score:
      typeof content.affinity_score === 'number' ? content.affinity_score : undefined,
    knowledge_value_score:
      typeof content.knowledge_value_score === 'number' ? content.knowledge_value_score : undefined,
    total_score: toNumber(content.total_score),
    strengths: toStringArray(content.strengths),
    weaknesses: toStringArray(content.weaknesses),
    suggestions: toStringArray(content.suggestions),
    evidence: Array.isArray(content.evidence)
      ? (content.evidence as unknown[]).filter(
          (item): item is Api.Douyin.AiScoreEvidence =>
            Boolean(item) &&
            typeof item === 'object' &&
            typeof (item as Record<string, unknown>).quote === 'string'
        )
      : []
  };
}

/** 把原始报告内容解析为标准 AiOptimizationResult */
export function parseOptimizationReport(
  report?: Api.Douyin.AnalysisReport
): Api.Douyin.AiOptimizationResult | null {
  const content = report?.report_content;
  if (!content) return null;

  const result = content as Api.Douyin.AiOptimizationResult;

  // 如果已有有效建议列表，直接返回
  if (toStringArray(result.suggestions).length) return result;

  // 兜底：把 content 中除 summary 外的字符串字段都拼成建议列表
  const fallback = Object.entries(content)
    .filter(([key, value]) => key !== 'summary' && typeof value === 'string' && Boolean(value.trim()))
    .map(([key, value]) => `${key}：${value}`);

  return { ...result, suggestions: fallback };
}

/** 从已保存的报告列表中恢复评分和优化结果（原地修改传入的 Ref） */
export function restoreReportsFromList<T extends { report_type: string }>(
  reports: T[],
  scoreSetter: (result: Api.Douyin.AiScoreResult | null) => void,
  optimizeSetter: (result: Api.Douyin.AiOptimizationResult | null) => void
): void {
  const typedReports = reports as unknown as Api.Douyin.AnalysisReport[];
  scoreSetter(parseScoreReport(typedReports.find(r => r.report_type === 'speech_score')));
  optimizeSetter(parseOptimizationReport(typedReports.find(r => r.report_type === 'optimization')));
}
