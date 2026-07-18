<script setup lang="ts">
defineOptions({
  name: 'Dashboard'
});

const dataeaseShareUrl = import.meta.env.VITE_DATAEASE_URL || 'http://localhost:8100/#/de-link/ioyH1hYC';
</script>

<template>
  <iframe
    class="dataease-screen"
    :src="dataeaseShareUrl"
    title="DataEase 数据大屏"
    loading="eager"
    referrerpolicy="strict-origin-when-cross-origin"
    allow="fullscreen; clipboard-read; clipboard-write"
    allowfullscreen
  />
</template>

<style scoped>
.dataease-screen {
  display: block;
  width: 100%;
  height: calc(100vh - 112px);
  min-height: 640px;
  border: 0;
  border-radius: 8px;
  background: #0b1220;
}

@media (max-width: 768px) {
  .dataease-screen {
    height: calc(100vh - 96px);
    min-height: 560px;
    border-radius: 0;
  }
}
</style>
