/**
 * 安全取值工具函数
 *
 * 为什么要写这些函数？
 *   后端返回的数据结构可能在运行时和 TypeScript 类型不一致（比如 null 代替了数组，
 *   或者字段名变了），直接用 `.` 链式取值会崩溃。
 *   这些工具函数像"安全气囊"——数据不对时不会崩，而是返回一个安全的默认值。
 *
 * 使用场景：
 *   - 页面从 API 拿到数据后，不确定某个深层字段是否存在
 *   - 数组操作（.map / .filter / .forEach）前先确保值确实是数组
 *   - 后端可能返回 null 的数字字段，前端需要安全转成 0
 */

/**
 * 安全地从对象中取出深层嵌套的值
 *
 * 像 lodash 的 _.get() 一样工作，但零依赖。
 * 路径中的任何一层是 null/undefined，都不会崩溃，而是返回默认值。
 *
 * 使用示例：
 *   safeGet(response, 'data.user.name', '未知用户')
 *   // 等价于 response?.data?.user?.name ?? '未知用户'，但更简洁
 *
 * @param obj   - 要取值的目标对象
 * @param path  - 点号分隔的路径，如 'data.user.name'
 * @param defaultValue - 取不到时的默认值
 */
export function safeGet<T = unknown>(
  obj: unknown,
  path: string,
  defaultValue: T
): T {
  // 如果目标本身是 null/undefined，直接返回默认值
  if (obj === null || obj === undefined) {
    return defaultValue;
  }

  const keys = path.split('.');
  let current: unknown = obj;

  for (const key of keys) {
    // 每一层都检查：当前值是否是对象、key 是否存在
    if (current === null || current === undefined || typeof current !== 'object') {
      return defaultValue;
    }
    current = (current as Record<string, unknown>)[key];
  }

  // 最终值如果是 null/undefined，也返回默认值
  return (current as T) ?? defaultValue;
}

/**
 * 确保一个值是数组
 *
 * 后端可能返回 null、undefined 或根本不是数组的东西。
 * 这个函数保证你拿到的永远是数组，可以安全地 .map() / .filter() / .forEach()
 *
 * 使用示例：
 *   const list = ensureArray(response.data?.records);
 *   list.map(item => item.name); // 安全！不会崩溃
 *
 * @param val - 可能是数组、null、undefined 或任何值
 * @returns   - 如果 val 是数组就返回它，否则返回空数组 []
 */
export function ensureArray<T = unknown>(val: unknown): T[] {
  return Array.isArray(val) ? (val as T[]) : [];
}

/**
 * 安全地把一个值转成数字
 *
 * 后端可能返回 null、undefined、字符串（如 "123"）或 NaN。
 * 这个函数保证你拿到的永远是有效的数字。
 *
 * 使用示例：
 *   const count = safeNumber(response.data?.totalViewers, 0);
 *   // 如果 response.data?.totalViewers 是 null/"abc"/undefined → 返回 0
 *
 * @param val      - 可能是数字、null、字符串等
 * @param defaultVal - 无法转换时的默认值（默认 0）
 * @returns        - 有效的数字
 */
export function safeNumber(val: unknown, defaultVal: number = 0): number {
  if (val === null || val === undefined) {
    return defaultVal;
  }
  if (typeof val === 'number' && Number.isFinite(val)) {
    return val;
  }
  const num = Number(val);
  return Number.isFinite(num) ? num : defaultVal;
}
