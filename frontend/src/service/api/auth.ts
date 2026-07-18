import { backendRequest } from '../request';

/**
 * Login
 *
 * @param userName User name
 * @param password Password
 */
export function fetchLogin(userName: string, password: string) {
  return backendRequest<Api.Auth.LoginToken>({
    url: '/api/v1/auth/login',
    method: 'post',
    data: {
      username: userName,
      password
    }
  });
}

/** Get user info */
export function fetchGetUserInfo() {
  return backendRequest<Api.Auth.UserInfo>({ url: '/api/v1/auth/getUserInfo' });
}

/**
 * Refresh token
 *
 * @param refreshToken Refresh token
 */
export function fetchRefreshToken(refreshToken: string) {
  return backendRequest<Api.Auth.LoginToken>({
    url: '/api/v1/auth/refreshToken',
    method: 'post',
    data: {
      refreshToken
    }
  });
}
