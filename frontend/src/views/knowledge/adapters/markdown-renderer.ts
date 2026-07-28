/**
 * Markdown 渲染适配器（2026-07-28 方案 C）
 *
 * 职责：使用 markdown-it 把 AI 回答的纯文本渲染成 HTML。
 * 支持：加粗、斜体、列表、代码块、链接、引用块。
 * 安全：禁用 HTML 标签注入，只允许安全的内联格式。
 */
import MarkdownIt from 'markdown-it';

/** 单例 markdown-it 实例，避免重复创建 */
const md = new MarkdownIt({
  html: false,          // 禁用原始 HTML（安全）
  breaks: true,         // 换行 → <br>
  linkify: true,        // 自动识别链接
  typographer: true,    // 智能引号、破折号
});

/**
 * 渲染 Markdown → 安全 HTML
 * @param text - AI 返回的原始文本
 * @returns 安全的 HTML 字符串
 */
export function renderMarkdown(text: string): string {
  if (!text) return '';
  try {
    return md.render(text);
  } catch {
    // 解析失败时回退到纯文本（用 <br> 保留换行）
    return text.replace(/\n/g, '<br>');
  }
}

/**
 * 从 Markdown 文本中提取纯文本（用于复制等场景）
 * @param text - AI 返回的原始 Markdown
 * @returns 去除 Markdown 标记的纯文本
 */
export function stripMarkdown(text: string): string {
  if (!text) return '';
  return text
    .replace(/#{1,6}\s/g, '')          // 标题
    .replace(/\*\*(.+?)\*\*/g, '$1')   // 加粗
    .replace(/\*(.+?)\*/g, '$1')       // 斜体
    .replace(/`(.+?)`/g, '$1')         // 行内代码
    .replace(/\[(.+?)]\(.+?\)/g, '$1') // 链接
    .replace(/>\s/g, '')               // 引用
    .replace(/[-*+]\s/g, '')           // 无序列表
    .replace(/\d+\.\s/g, '')           // 有序列表
    .trim();
}
