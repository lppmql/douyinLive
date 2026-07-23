<script setup lang="ts">
import { computed } from 'vue';
import { getLiveSessionAvatarUrl } from '@/service/api/douyin';
import AnchorAvatar from './anchor-avatar.vue';

defineOptions({ name: 'AnchorIdentity' });

const props = withDefaults(
  defineProps<{
    /** 场次 ID 存在时，头像统一走后端代理，避免抖音图片防盗链。 */
    sessionId?: number | null;
    avatarUrl?: string | null;
    name?: string | null;
    nickname?: string | null;
    douyinId?: string | null;
    description?: string | null;
    size?: number;
    showDouyinId?: boolean;
    dense?: boolean;
  }>(),
  {
    sessionId: null,
    avatarUrl: '',
    name: '',
    nickname: '',
    douyinId: '',
    description: '',
    size: 34,
    showDouyinId: true,
    dense: false
  }
);

const displayName = computed(() => props.nickname?.trim() || props.name?.trim() || '未知主播');

const displayAvatarUrl = computed(() => {
  if (!props.avatarUrl) return '';
  return props.sessionId ? getLiveSessionAvatarUrl(props.sessionId) : props.avatarUrl;
});

const secondaryText = computed(() => {
  if (props.description?.trim()) return props.description.trim();
  if (!props.showDouyinId) return '';
  return `抖音号 ${props.douyinId?.trim() || '未获取'}`;
});
</script>

<template>
  <div class="anchor-identity" :class="{ 'anchor-identity--dense': dense }">
    <AnchorAvatar :size="size" :src="displayAvatarUrl" :name="displayName" />
    <div class="min-w-0 flex-1">
      <div class="anchor-identity__name" :title="displayName">{{ displayName }}</div>
      <div v-if="secondaryText" class="anchor-identity__secondary" :title="secondaryText">
        {{ secondaryText }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.anchor-identity {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 9px;
}

.anchor-identity__name,
.anchor-identity__secondary {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.anchor-identity__name {
  color: var(--n-text-color, inherit);
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.anchor-identity__secondary {
  color: var(--n-text-color-3, #94a3b8);
  font-size: 11px;
  line-height: 17px;
}

.anchor-identity--dense {
  gap: 7px;
}

.anchor-identity--dense .anchor-identity__name {
  line-height: 17px;
}

.anchor-identity--dense .anchor-identity__secondary {
  line-height: 14px;
}
</style>
