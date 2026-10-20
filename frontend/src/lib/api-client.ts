export const getApiKey = (): string => {
  const envKey = import.meta.env.VITE_KYOMA_API_KEY;
  if (envKey) return envKey;
  return localStorage.getItem("KYOMA_API_KEY") || "";
};

export const API_KEY = getApiKey();

export const apiFetch = (url: string, opts: RequestInit = {}) => {
  const key = getApiKey();
  const headers: Record<string, string> = {
    ...(opts.headers as Record<string, string> || {}),
  };
  if (key) {
    headers["X-API-Key"] = key;
  }
  return fetch(url, {
    ...opts,
    headers,
  });
};
