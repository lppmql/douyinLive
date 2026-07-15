<script setup lang="ts">
import type { TagProps } from 'naive-ui';

defineOptions({ name: 'BusinessPageHeader' });

interface Props {
  title: string;
  description: string;
  icon: string;
  eyebrow?: string;
  status?: string;
  statusType?: TagProps['type'];
}

withDefaults(defineProps<Props>(), {
  eyebrow: '直播经营中台',
  status: '',
  statusType: 'default'
});
</script>

<template>
  <NCard :bordered="false" class="business-page-header card-wrapper overflow-hidden">
    <div class="relative z-1 flex flex-wrap items-center justify-between gap-18px">
      <div class="min-w-0 flex items-start gap-14px">
        <div class="size-46px flex-center shrink-0 rounded-14px bg-primary-100 text-primary dark:bg-primary-900/30">
          <SvgIcon :icon="icon" class="text-25px" />
        </div>
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-8px">
            <span class="text-12px font-600 tracking-1px text-primary">{{ eyebrow }}</span>
            <NTag v-if="status" :type="statusType" round size="small" :bordered="false">{{ status }}</NTag>
          </div>
          <h1 class="mb-0 mt-4px text-24px font-700 leading-32px lt-sm:text-21px">{{ title }}</h1>
          <p class="mb-0 mt-5px max-w-760px text-13px leading-21px text-gray-500">{{ description }}</p>
        </div>
      </div>
      <div v-if="$slots.actions" class="flex shrink-0 flex-wrap items-center gap-8px lt-sm:w-full">
        <slot name="actions" />
      </div>
    </div>
    <div
      class="pointer-events-none absolute right--36px top--70px size-190px rounded-full bg-primary-100/65 blur-3xl dark:bg-primary-900/20"
    ></div>
    <div v-if="$slots.default" class="relative z-1 mt-14px border-t border-gray-100 pt-12px dark:border-white/8">
      <slot />
    </div>
  </NCard>
</template>

<style scoped>
.business-page-header {
  position: relative;
  background: linear-gradient(120deg, rgba(255, 255, 255, 0.98), rgba(242, 247, 255, 0.92)), var(--n-color);
}

:global(.dark) .business-page-header {
  background: linear-gradient(120deg, rgba(24, 24, 28, 0.98), rgba(31, 38, 52, 0.96));
}
</style>
