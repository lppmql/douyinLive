<script lang="ts" setup>
import { computed } from 'vue';
import { useRouterPush } from '@/hooks/common/router';
import { $t } from '@/locales';

defineOptions({ name: 'ExceptionBase' });

type ExceptionType = '403' | '404' | '500';

interface Props {
  /**
   * Exception type
   *
   * - 403: no permission
   * - 404: not found
   * - 500: service error
   */
  type: ExceptionType;
}

const props = defineProps<Props>();

const { routerPushByKey } = useRouterPush();

const iconMap: Record<ExceptionType, string> = {
  '403': 'no-permission',
  '404': 'not-found',
  '500': 'service-error'
};

const icon = computed(() => iconMap[props.type]);

const contentMap: Record<ExceptionType, { title: string; description: string }> = {
  '403': { title: '没有访问权限', description: '当前账号不能访问此页面，请联系管理员调整角色权限。' },
  '404': { title: '页面不存在', description: '链接可能已失效，建议返回首页后从左侧菜单重新进入。' },
  '500': { title: '页面暂时无法加载', description: '请先刷新重试；如果仍失败，请检查后端健康状态和对应操作日志。' }
};

const content = computed(() => contentMap[props.type]);

function reloadPage() {
  window.location.reload();
}
</script>

<template>
  <div class="size-full min-h-520px flex-col-center gap-16px overflow-hidden px-20px text-center">
    <div class="flex text-260px text-primary lt-sm:text-180px">
      <SvgIcon :local-icon="icon" />
    </div>
    <div>
      <h1 class="m-0 text-26px font-700">{{ content.title }}</h1>
      <p class="mb-0 mt-8px text-14px text-gray-500">{{ content.description }}</p>
    </div>
    <NSpace>
      <NButton v-if="type === '500'" @click="reloadPage">刷新重试</NButton>
      <NButton type="primary" @click="routerPushByKey('root')">{{ $t('common.backToHome') }}</NButton>
    </NSpace>
  </div>
</template>

<style scoped></style>
