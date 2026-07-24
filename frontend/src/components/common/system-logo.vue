<template>
  <div class="app-logo">
    <!-- 简洁的零食店避坑主题 Logo：盾牌 + 购物袋抽象组合 -->
    <svg width="100%" height="100%" viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- 外圈圆形底色 -->
      <circle cx="100" cy="100" r="92" fill="var(--logo-bg)" />
      <!-- 购物袋/资料袋造型 -->
      <path d="M60 70 L60 155 L140 155 L140 70 Z" fill="var(--logo-primary)" opacity="0.15" />
      <!-- 文档/盾牌造型 -->
      <path d="M100 40 L130 55 L130 100 Q130 135 100 150 Q70 135 70 100 L70 55 Z"
        fill="var(--logo-primary)" opacity="0.25" />
      <path d="M100 48 L122 59 L122 100 Q122 130 100 142 Q78 130 78 100 L78 59 Z"
        fill="var(--logo-primary)" opacity="0.9" />
      <!-- 对勾/数据标记 -->
      <path d="M87 95 L97 105 L113 85" stroke="var(--logo-check)" stroke-width="6" stroke-linecap="round"
        stroke-linejoin="round" />
      <!-- 底部文字 -->
      <text x="100" y="182" text-anchor="middle" font-size="14" font-weight="700"
        fill="var(--logo-primary)" font-family="system-ui">系统</text>
    </svg>
  </div>
</template>

<style scoped>
.app-logo {
  --logo-bg: rgb(var(--primary-100-color));
  --logo-primary: rgb(var(--primary-600-color));
  --logo-check: rgb(var(--success-500-color));
}
</style>
