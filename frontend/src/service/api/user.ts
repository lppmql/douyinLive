import { backendRequest } from '../request';

/** 用户管理 API */

export interface UserRecord {
  id: number;
  username: string;
  nickname: string | null;
  email: string | null;
  phone: string | null;
  avatar: string | null;
  roles: string[];
  status: string;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserPageResult {
  records: UserRecord[];
  total: number;
  current: number;
  size: number;
}

/** 获取用户列表（分页） */
export function fetchUserList(params: { current: number; size: number; username?: string; status?: string }) {
  return backendRequest<UserPageResult>({ url: '/api/v1/users/', method: 'get', params });
}

/** 新建用户 */
export function fetchCreateUser(data: {
  username: string;
  password: string;
  nickname?: string;
  email?: string;
  phone?: string;
  roles?: string[];
  status?: string;
}) {
  return backendRequest<UserRecord>({ url: '/api/v1/users/', method: 'post', data });
}

/** 编辑用户 */
export function fetchUpdateUser(
  id: number,
  data: {
    username?: string;
    password?: string;
    nickname?: string;
    email?: string;
    phone?: string;
    roles?: string[];
    status?: string;
  }
) {
  return backendRequest<UserRecord>({ url: `/api/v1/users/${id}`, method: 'put', data });
}

/** 删除用户 */
export function fetchDeleteUser(id: number) {
  return backendRequest<any>({ url: `/api/v1/users/${id}`, method: 'delete' });
}
