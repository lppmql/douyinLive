<!--
  扫码登录弹窗 — 从 collector/index.vue 拆分
  展示二维码、登录步骤、状态提示，不包含登录逻辑（由父组件处理轮询）
-->
<script setup lang="ts">
import { NButton, NModal, NAlert, NSpin, NStep, NSteps, NSpace } from 'naive-ui';
import { $t } from '@/locales';

defineOptions({ name: 'CollectorQRLogin' });

/** 登录流程状态：idle=空闲 / pending=等待二维码 / scanning=等待扫码 / success=成功 / failed=失败 / timeout=超时 */
type LoginState = 'idle' | 'pending' | 'scanning' | 'success' | 'failed' | 'timeout' | 'not_found';

defineProps<{
  /** 弹窗是否可见 */
  visible: boolean;
  /** Base64 编码的二维码图片 */
  qrImage: string;
  /** 当前登录状态 */
  status: LoginState;
  /** 状态提示消息 */
  message: string;
}>();

const emit = defineEmits<{
  /** 关闭弹窗 */
  (e: 'close'): void;
  /** 重新生成二维码 */
  (e: 'retry'): void;
}>();

/** 弹窗关闭后的清理回调 */
function handleAfterLeave() {
  emit('close');
}
</script>

<template>
  <NModal
    :show="visible"
    :mask-closable="false"
    preset="card"
    class="w-420px max-w-[calc(100vw-32px)]"
    @after-leave="handleAfterLeave"
  >
    <template #header>
      {{ $t('page.collector.scanLogin') }}
    </template>

    <div class="flex flex-col items-center py-12px">
      <!-- 登录步骤指示器 -->
      <NSteps class="mb-20px" size="small" :current="status === 'pending' ? 1 : 2" status="process">
        <NStep title="生成二维码" />
        <NStep title="抖音扫码确认" />
        <NStep title="保存登录状态" />
      </NSteps>

      <!-- 二维码区域：加载中显示 spinner，加载完显示二维码 -->
      <div v-if="qrImage" class="mb-16px size-240px rounded-12px bg-white p-10px shadow-sm ring-1 ring-gray-200">
        <img :src="`data:image/png;base64,${qrImage}`" class="size-full" alt="抖音扫码登录二维码" />
      </div>
      <div v-else class="mb-16px size-240px flex-center rounded-12px bg-gray-100 dark:bg-white/5">
        <NSpin :size="24" />
      </div>

      <!-- 状态提示 -->
      <NAlert
        class="w-full"
        :type="status === 'failed' || status === 'timeout' ? 'error' : 'info'"
        :show-icon="true"
      >
        {{ message || $t('page.collector.scanQrCode') }}
      </NAlert>

      <!-- 键盘提示 -->
      <div class="mt-10px text-center text-11px text-gray-400">
        按 <kbd class="rounded-4px border border-gray-300 bg-gray-100 px-4px py-1px text-11px dark:border-white/15 dark:bg-white/8">Esc</kbd> 或点击「取消」关闭此窗口
      </div>
    </div>

    <template #footer>
      <NSpace justify="end">
        <NButton @click="handleAfterLeave">{{ $t('common.cancel') }}</NButton>
        <NButton
          v-if="status === 'failed' || status === 'timeout'"
          type="primary"
          @click="emit('retry')"
        >
          重新生成二维码
        </NButton>
      </NSpace>
    </template>
  </NModal>
</template>
