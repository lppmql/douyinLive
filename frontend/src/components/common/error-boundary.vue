<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue';

/**
 * ErrorBoundary — 组件级错误边界
 *
 * 干什么用：当子组件渲染或更新时崩溃（比如数据为 undefined 调了 .map()），
 * 这个组件会捕获错误，显示一个友好的"出错了"提示，而不是整个页面白屏。
 *
 * 原理：Vue 3 的 onErrorCaptured 钩子，类似 React 的 ErrorBoundary。
 * 返回 false 阻止错误继续向上冒泡（上层不会再触发 app.config.errorHandler）。
 */
defineOptions({ name: 'ErrorBoundary' });

// ===== 错误状态 =====
const hasError = ref(false);
const errorMessage = ref('');
const errorStack = ref('');

// ===== 捕获子组件错误 =====
onErrorCaptured((err, _instance, info) => {
  hasError.value = true;
  errorMessage.value = err instanceof Error ? err.message : String(err);
  errorStack.value = err instanceof Error ? (err.stack || '') : '';

  // 输出到浏览器控制台，方便开发者排查
  console.error(
    `[ErrorBoundary] 捕获到组件崩溃:\n  组件: ${info}\n  错误: ${errorMessage.value}\n  堆栈: ${errorStack.value}`
  );

  // 返回 false：阻止错误继续往上冒泡到 app.config.errorHandler
  return false;
});

// ===== 重试：清除错误状态，让子组件重新渲染 =====
function retry() {
  hasError.value = false;
  errorMessage.value = '';
  errorStack.value = '';
}
</script>

<template>
  <!-- 出错了 → 显示友好降级界面 -->
  <div v-if="hasError" class="size-full min-h-400px flex-col-center gap-16px px-20px text-center">
    <div class="text-80px text-red-400">
      <SvgIcon icon="mdi:alert-circle-outline" />
    </div>
    <div>
      <h2 class="m-0 text-20px font-600">页面组件渲染出错</h2>
      <p class="mb-0 mt-8px max-w-400px text-13px text-gray-500">
        {{ errorMessage || '未知错误，请尝试重试或返回首页。' }}
      </p>
    </div>
    <NSpace>
      <NButton @click="retry">
        <template #icon><SvgIcon icon="mdi:refresh" /></template>
        重试
      </NButton>
      <NButton type="primary" tag="a" href="/">
        <template #icon><SvgIcon icon="mdi:home" /></template>
        返回首页
      </NButton>
    </NSpace>
    <!-- 调试用：展开看错误堆栈 -->
    <details v-if="errorStack" class="mt-8 w-full max-w-600px text-left">
      <summary class="cursor-pointer text-11px text-gray-400 select-none">
        错误详情（调试用，点击展开）
      </summary>
      <pre class="mt-8px text-11px text-gray-500 whitespace-pre-wrap break-all max-h-200px overflow-auto rounded-8px bg-gray-50 p-12px dark:bg-gray-800">{{ errorStack }}</pre>
    </details>
  </div>

  <!-- 正常 → 透传子组件 -->
  <slot v-else />
</template>

<style scoped></style>
