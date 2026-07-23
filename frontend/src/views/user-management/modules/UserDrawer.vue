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

type UserFormField = 'username' | 'password' | 'nickname' | 'email' | 'phone' | 'roles' | 'status';

const props = defineProps<{
  visible: boolean;
  operateType: 'add' | 'edit';
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
  (e: 'updateField', field: UserFormField, value: string | string[]): void;
  (e: 'save'): void;
}>();

/** 表单值由父级统一保存，避免子组件直接修改传入对象。 */
function updateField(field: UserFormField, value: string | string[]) {
  emit('updateField', field, value);
}
</script>

<template>
  <NDrawer :show="visible" :width="460" @update:show="(v: boolean) => emit('update:visible', v)">
    <NDrawerContent :title="operateType === 'add' ? '新增用户' : '编辑用户'" closable>
      <NAlert class="mb-16px" type="info" :bordered="false">
        普通用户用于日常查看；仅确有管理需要时授予超级管理员角色。
      </NAlert>
      <NForm label-placement="top" :rules="formRules">
        <NFormItem label="用户名" path="username" required>
          <NInput
            :value="props.formData.username"
            placeholder="请输入用户名"
            @update:value="value => updateField('username', value)"
          />
        </NFormItem>
        <NFormItem :label="operateType === 'add' ? '密码' : '新密码'" :path="operateType === 'add' ? 'password' : ''">
          <NInput
            :value="props.formData.password"
            type="password"
            show-password-on="click"
            :placeholder="operateType === 'add' ? '请输入密码' : '留空则不修改'"
            @update:value="value => updateField('password', value)"
          />
        </NFormItem>
        <NFormItem label="昵称">
          <NInput
            :value="props.formData.nickname"
            placeholder="请输入昵称"
            @update:value="value => updateField('nickname', value)"
          />
        </NFormItem>
        <NFormItem label="邮箱">
          <NInput
            :value="props.formData.email"
            placeholder="请输入邮箱"
            @update:value="value => updateField('email', value)"
          />
        </NFormItem>
        <NFormItem label="手机号">
          <NInput
            :value="props.formData.phone"
            placeholder="请输入手机号"
            @update:value="value => updateField('phone', value)"
          />
        </NFormItem>
        <NFormItem label="角色">
          <NSelect
            :value="props.formData.roles"
            :options="roleOptions"
            multiple
            @update:value="value => updateField('roles', value)"
          />
        </NFormItem>
        <NFormItem label="状态">
          <NSelect
            :value="props.formData.status"
            :options="statusOptions"
            @update:value="value => updateField('status', value)"
          />
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
