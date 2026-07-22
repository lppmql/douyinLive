<!-- 用户编辑抽屉（NDrawer 替代 NModal） -->
<script setup lang="ts">
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpace,
  NAlert
} from 'naive-ui';

defineOptions({ name: 'UserDrawer' });

defineProps<{
  visible: boolean;
  operateType: 'add' | 'edit';
  editingId: number | null;
  formData: {
    username: string;
    password: string;
    nickname: string;
    email: string;
    phone: string;
    roles: string[];
    status: string;
  };
  formRules: Record<string, { required: boolean; message: string; trigger: string }[]>;
  roleOptions: Array<{ label: string; value: string }>;
  statusOptions: Array<{ label: string; value: string }>;
  saving: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void;
  (e: 'save'): void;
}>();
</script>

<template>
  <NDrawer :show="visible" :width="460" @update:show="(v: boolean) => emit('update:visible', v)">
    <NDrawerContent :title="operateType === 'add' ? '新增用户' : '编辑用户'" closable>
      <NAlert class="mb-16px" type="info" :bordered="false">
        普通用户用于日常查看；仅确有管理需要时授予超级管理员角色。
      </NAlert>
      <NForm label-placement="top" :rules="formRules">
        <NFormItem label="用户名" path="username" required>
          <NInput v-model:value="formData.username" placeholder="请输入用户名" />
        </NFormItem>
        <NFormItem :label="operateType === 'add' ? '密码' : '新密码'" :path="operateType === 'add' ? 'password' : ''">
          <NInput
            v-model:value="formData.password"
            type="password"
            show-password-on="click"
            :placeholder="operateType === 'add' ? '请输入密码' : '留空则不修改'"
          />
        </NFormItem>
        <NFormItem label="昵称">
          <NInput v-model:value="formData.nickname" placeholder="请输入昵称" />
        </NFormItem>
        <NFormItem label="邮箱">
          <NInput v-model:value="formData.email" placeholder="请输入邮箱" />
        </NFormItem>
        <NFormItem label="手机号">
          <NInput v-model:value="formData.phone" placeholder="请输入手机号" />
        </NFormItem>
        <NFormItem label="角色">
          <NSelect v-model:value="formData.roles" :options="roleOptions" multiple />
        </NFormItem>
        <NFormItem label="状态">
          <NSelect v-model:value="formData.status" :options="statusOptions" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="emit('update:visible', false)">取消</NButton>
          <NButton type="primary" :loading="saving" @click="emit('save')">保存</NButton>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
