<script setup lang="ts">
import { computed } from 'vue';
import type { Component } from 'vue';
import { getPaletteColorByNumber, mixColor } from '@sa/color';
import { loginModuleRecord } from '@/constants/app';
import { useAppStore } from '@/store/modules/app';
import { useThemeStore } from '@/store/modules/theme';
import { $t } from '@/locales';
import PwdLogin from './modules/pwd-login.vue';
import CodeLogin from './modules/code-login.vue';
import Register from './modules/register.vue';
import ResetPwd from './modules/reset-pwd.vue';
import BindWechat from './modules/bind-wechat.vue';

interface Props {
  /** The login module */
  module?: UnionKey.LoginModule;
}

const props = defineProps<Props>();

const appStore = useAppStore();
const themeStore = useThemeStore();

interface LoginModule {
  label: App.I18n.I18nKey;
  component: Component;
}

const moduleMap: Record<UnionKey.LoginModule, LoginModule> = {
  'pwd-login': { label: loginModuleRecord['pwd-login'], component: PwdLogin },
  'code-login': { label: loginModuleRecord['code-login'], component: CodeLogin },
  register: { label: loginModuleRecord.register, component: Register },
  'reset-pwd': { label: loginModuleRecord['reset-pwd'], component: ResetPwd },
  'bind-wechat': { label: loginModuleRecord['bind-wechat'], component: BindWechat }
};

const activeModule = computed(() => moduleMap[props.module || 'pwd-login']);

const bgThemeColor = computed(() =>
  themeStore.darkMode ? getPaletteColorByNumber(themeStore.themeColor, 600) : themeStore.themeColor
);

const bgColor = computed(() => {
  const COLOR_WHITE = '#ffffff';

  const ratio = themeStore.darkMode ? 0.5 : 0.2;

  return mixColor(COLOR_WHITE, themeStore.themeColor, ratio);
});
</script>

<template>
  <div class="relative size-full flex-center overflow-hidden" :style="{ backgroundColor: bgColor }">
    <WaveBg :theme-color="bgThemeColor" />
    <div class="relative z-4 grid items-stretch gap-18px lg:grid-cols-[360px_440px]">
      <section
        class="login-intro hidden overflow-hidden rounded-14px p-32px text-white lg:flex lg:flex-col lg:justify-between"
      >
        <div>
          <NTag :bordered="false" round class="!bg-white/16 !text-white">真实数据 · 全链路经营</NTag>
          <h1 class="mb-0 mt-22px text-30px font-700 leading-42px">从采集到分析，一处掌握每场直播</h1>
          <p class="mb-0 mt-14px text-14px leading-24px text-white/78">
            统一管理主播、场次、评论、分钟趋势、ASR 话术、AI 分析与知识库，所有经营结论都可追溯到真实数据。
          </p>
        </div>
        <div class="flex flex-col gap-12px text-13px text-white/85">
          <span class="flex items-center gap-8px">
            <SvgIcon icon="mdi:shield-check-outline" />
            登录后再访问业务数据
          </span>
          <span class="flex items-center gap-8px">
            <SvgIcon icon="mdi:database-check-outline" />
            缺失数据明确标记，不伪造补值
          </span>
          <span class="flex items-center gap-8px">
            <SvgIcon icon="mdi:chart-timeline-variant" />
            采集进度与失败原因全程可见
          </span>
        </div>
      </section>

      <NCard :bordered="false" class="w-auto rd-14px shadow-xl">
        <div class="w-400px lt-sm:w-300px">
          <header class="flex-y-center justify-between">
            <SystemLogo class="size-64px lt-sm:size-48px" />
            <h3 class="text-28px text-primary font-500 lt-sm:text-22px">{{ $t('system.title') }}</h3>
            <div class="i-flex-col">
              <ThemeSchemaSwitch
                :theme-schema="themeStore.themeScheme"
                :show-tooltip="false"
                class="text-20px lt-sm:text-18px"
                @switch="themeStore.toggleThemeScheme"
              />
              <LangSwitch
                v-if="themeStore.header.multilingual.visible"
                :lang="appStore.locale"
                :lang-options="appStore.localeOptions"
                :show-tooltip="false"
                @change-lang="appStore.changeLocale"
              />
            </div>
          </header>
          <main class="pt-24px">
            <h3 class="text-18px text-primary font-medium">{{ $t(activeModule.label) }}</h3>
            <p class="mb-0 mt-6px text-12px text-gray-500">登录后可访问已授权的直播经营数据</p>
            <div class="pt-24px">
              <Transition :name="themeStore.page.animateMode" mode="out-in" appear>
                <component :is="activeModule.component" />
              </Transition>
            </div>
          </main>
        </div>
      </NCard>
    </div>
  </div>
</template>

<style scoped>
.login-intro {
  background:
    radial-gradient(circle at 85% 15%, rgba(255, 255, 255, 0.22), transparent 30%),
    linear-gradient(145deg, #155eef, #0d9488);
  box-shadow: 0 24px 60px rgba(21, 94, 239, 0.25);
}
</style>
