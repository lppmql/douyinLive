<script setup lang="ts">
import { ref, watch } from 'vue';

defineOptions({ name: 'AnchorAvatar' });

const props = withDefaults(
  defineProps<{
    src?: string;
    name?: string;
    size?: number;
  }>(),
  {
    src: '',
    name: '主播',
    size: 32
  }
);

const hasLoadError = ref(false);

watch(
  () => props.src,
  () => {
    hasLoadError.value = false;
  }
);
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-gray-200 text-gray-500"
    :style="{ width: `${size}px`, height: `${size}px` }"
  >
    <img
      v-if="src && !hasLoadError"
      :src="src"
      :alt="`${name}头像`"
      class="size-full object-cover"
      @error="hasLoadError = true"
    />
    <template v-else>{{ name.slice(0, 1) || '播' }}</template>
  </span>
</template>
