import json5 from 'json5';

/**
 * Create service config by current env
 *
 * @param env The current env
 */
export function createServiceConfig(env: Env.ImportMeta) {
  const { VITE_SERVICE_BASE_URL, VITE_OTHER_SERVICE_BASE_URL } = env;

  let other = {} as Record<App.Service.OtherBaseURLKey, string>;
  try {
    other = json5.parse(VITE_OTHER_SERVICE_BASE_URL);
  } catch {
    // eslint-disable-next-line no-console
    console.error('VITE_OTHER_SERVICE_BASE_URL is not a valid json5 string');
  }

  const httpConfig: App.Service.SimpleServiceConfig = {
    baseURL: VITE_SERVICE_BASE_URL,
    other
  };

  const otherHttpKeys = Object.keys(httpConfig.other) as App.Service.OtherBaseURLKey[];

  const otherConfig: App.Service.OtherServiceConfigItem[] = otherHttpKeys.map(key => {
    return {
      key,
      baseURL: httpConfig.other[key],
      proxyPattern: createProxyPattern(key)
    };
  });

  const config: App.Service.ServiceConfig = {
    baseURL: httpConfig.baseURL,
    proxyPattern: createProxyPattern(),
    other: otherConfig
  };

  return config;
}

/**
 * get backend service base url
 *
 * @param env - the current env
 * @param isProxy - if use proxy
 */
export function getServiceBaseURL(env: Env.ImportMeta, isProxy: boolean) {
  const { baseURL, other } = createServiceConfig(env);

  const otherBaseURL = {} as Record<App.Service.OtherBaseURLKey, string>;

  other.forEach(item => {
    otherBaseURL[item.key] = isProxy ? item.proxyPattern : item.baseURL;
  });

  return {
    baseURL: isProxy ? createProxyPattern() : baseURL,
    otherBaseURL
  };
}

/** Convert an HTTP service base URL to an absolute WebSocket base URL. */
export function getWebSocketBaseURL(baseURL: string, origin = window.location.origin) {
  const absoluteBaseURL = /^https?:\/\//.test(baseURL)
    ? baseURL
    : `${origin}${baseURL.startsWith('/') ? '' : '/'}${baseURL}`;

  return absoluteBaseURL.replace(/^http/, 'ws').replace(/\/$/, '');
}

/** Convert flat Axios errors into a message that can be shown in page-level feedback. */
export function getServiceErrorMessage(error: unknown, fallback: string) {
  if (!error || typeof error !== 'object') return fallback;

  const responseData = (error as { response?: { data?: unknown } }).response?.data;
  if (responseData && typeof responseData === 'object') {
    const detail = (responseData as { detail?: unknown; message?: unknown }).detail;
    const message = (responseData as { detail?: unknown; message?: unknown }).message;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (typeof message === 'string' && message.trim()) return message;
  }

  const message = (error as { message?: unknown }).message;
  return typeof message === 'string' && message.trim() ? message : fallback;
}

/** Unwrap SoybeanAdmin's flat request result and keep page error handling consistent. */
export function unwrapServiceData<T>(result: { data: T | null; error: unknown }, fallback: string): T {
  if (result.error) throw new Error(getServiceErrorMessage(result.error, fallback));
  if (result.data === null) throw new Error(fallback);
  return result.data;
}

/**
 * Get proxy pattern of backend service base url
 *
 * @param key If not set, will use the default key
 */
function createProxyPattern(key?: App.Service.OtherBaseURLKey) {
  if (!key) {
    return '/proxy-default';
  }

  return `/proxy-${key}`;
}
