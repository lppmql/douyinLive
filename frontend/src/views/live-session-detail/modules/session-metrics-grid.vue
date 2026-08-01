<script setup lang="ts">
import { computed } from 'vue';

defineOptions({ name: 'LiveSessionMetricsGrid' });
const props = defineProps<{ session: Api.Douyin.LiveSession }>();

const groups = computed(() => [
  {
    title: '流量与停留',
    items: [
      ['累计观看', props.session.total_viewers, '次'], ['看过人数', props.session.viewed_count, '人'],
      ['平均在线', props.session.avg_online_count, '人'], ['峰值在线', props.session.peak_online_count, '人'],
      ['平均停留', props.session.avg_watch_seconds, '秒'], ['粉丝平均停留', props.session.fans_avg_watch_seconds, '秒'],
      ['观看超过 1 分钟', props.session.watch_over_1m_count, '人'], ['曝光进入率', props.session.exposure_enter_rate, '%'],
      ['粉丝观看占比', props.session.fans_view_ratio, '%'], ['直播间曝光人数', props.session.live_exposure_users, '人'],
      ['直播进入人数', props.session.live_enter_users, '人'], ['自然流量占比', props.session.natural_traffic_ratio, '%'],
      ['营销流量占比', props.session.marketing_traffic_ratio, '%'], ['其他流量占比', props.session.other_traffic_ratio, '%']
    ]
  },
  {
    title: '互动与关系沉淀',
    items: [
      ['评论用户', props.session.comment_users, '人'], ['评论总数', props.session.comments_count, '条'],
      ['评论率', props.session.comment_rate, '%'], ['互动次数', props.session.interaction_count, '次'],
      ['互动用户', props.session.interaction_users, '人'], ['互动率', props.session.interaction_rate, '%'],
      ['点赞次数', props.session.like_count, '次'], ['点赞用户', props.session.like_users, '人'],
      ['点赞率', props.session.like_rate, '%'],
      ['分享次数', props.session.share_count, '次'], ['分享用户', props.session.share_users, '人'],
      ['分享率', props.session.share_rate, '%'],
      ['新增关注', props.session.new_followers, '人'], ['关注率', props.session.follow_rate, '%'],
      ['加入粉丝团', props.session.fans_club_join_count, '人'], ['粉丝团加入率', props.session.fans_club_join_rate, '%']
    ]
  },
  {
    title: '留资与广告转化',
    items: [
      ['私信人数', props.session.private_message_count, '人'], ['长期私信线索', props.session.private_message_longterm_count, '人'],
      ['场景线索', props.session.scene_leads_count, '条'], ['有效客资', props.session.leads_count, '条'],
      ['线索转化率', props.session.scene_lead_conversion_rate, '%'], ['小风车点击', props.session.mini_windmill_click_count, '次'],
      ['小风车点击率', props.session.mini_windmill_click_rate, '%'], ['卡片点击', props.session.card_click_count, '次'],
      ['卡片点击率', props.session.card_click_rate, '%'], ['卡片点击用户', props.session.card_click_users, '人'],
      ['微信添加', props.session.wechat_add_count, '人'],
      ['微信添加成本', props.session.wechat_add_cost, '元'], ['表单提交', props.session.form_submit_count, '次'],
      ['表单提交用户', props.session.form_submit_users, '人'], ['表单成本', props.session.form_submit_cost, '元'],
      ['广告消耗', props.session.ad_cost, '元']
    ]
  },
  {
    title: '礼物与负反馈',
    items: [
      ['礼物次数', props.session.gift_count, '次'], ['礼物金额', props.session.gift_amount, '元'],
      ['不喜欢次数', props.session.dislike_count, '次'], ['不喜欢用户', props.session.dislike_users, '人']
    ]
  }
]);

function display(value: string | number, unit: string) {
  const number = Number(value || 0);
  const normalized = unit === '%' ? number * 100 : number;
  const formatted = unit === '元' ? normalized.toFixed(2) : unit === '%' || unit === '秒' ? normalized.toFixed(1) : normalized.toLocaleString();
  return `${formatted} ${unit}`;
}
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" title="本场全部已采集指标">
    <NAlert type="default" :show-icon="true" class="mb-16px">
      这里展示平台已返回并保存到数据库的场次级字段；数值为 0 不等同于字段缺失。
    </NAlert>
    <NCollapse :default-expanded-names="['流量与停留', '留资与广告转化']">
      <NCollapseItem v-for="group in groups" :key="group.title" :title="group.title" :name="group.title">
        <NGrid :x-gap="12" :y-gap="12" cols="2 s:3 m:4 xl:6" responsive="screen">
          <NGi v-for="item in group.items" :key="String(item[0])">
            <div class="rounded-8px bg-gray-50 p-10px dark:bg-dark">
              <div class="text-11px text-gray-500">{{ item[0] }}</div>
              <div class="mt-4px text-16px font-650">{{ display(item[1], String(item[2])) }}</div>
            </div>
          </NGi>
        </NGrid>
      </NCollapseItem>
    </NCollapse>
  </NCard>
</template>
