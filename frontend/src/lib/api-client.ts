export const getApiKey = (): string => {
  const envKey = import.meta.env.VITE_KYOMA_API_KEY;
  if (envKey) return envKey;
  return localStorage.getItem("KYOMA_API_KEY") || "";
};

export const API_KEY = getApiKey();

// Safe GET cache with short TTL (5 seconds) and in-flight promise sharing to eliminate duplicate requests
const getCache = new Map<string, { data: unknown; status: number; ok: boolean; headers: [string, string][]; timestamp: number }>();
const inFlightGets = new Map<string, Promise<Response>>();

export const apiFetch = async (url: string, opts: RequestInit = {}): Promise<Response> => {
  const key = getApiKey();
  const headers: Record<string, string> = {
    ...(opts.headers as Record<string, string> || {}),
  };
  if (key) {
    headers["X-API-Key"] = key;
  }

  const method = (opts.method || "GET").toUpperCase();
  const isSafeGet = method === "GET" && !opts.body && !opts.signal;

  if (isSafeGet) {
    const cached = getCache.get(url);
    const now = Date.now();
    if (cached && now - cached.timestamp < 5000) {
      return new Response(JSON.stringify(cached.data), {
        status: cached.status,
        headers: new Headers(cached.headers),
      });
    }

    if (inFlightGets.has(url)) {
      const res = await inFlightGets.get(url)!;
      return res.clone();
    }

    const fetchPromise = (async () => {
      try {
        const response = await fetch(url, { ...opts, headers });
        if (response.ok) {
          try {
            const clone = response.clone();
            const data = await clone.json();
            const headerEntries: [string, string][] = [];
            response.headers.forEach((v, k) => headerEntries.push([k, v]));
            getCache.set(url, {
              data,
              status: response.status,
              ok: response.ok,
              headers: headerEntries,
              timestamp: Date.now(),
            });
          } catch {
            // Not JSON or streaming; ignore cache
          }
        }
        return response;
      } finally {
        inFlightGets.delete(url);
      }
    })();

    inFlightGets.set(url, fetchPromise);
    const res = await fetchPromise;
    return res.clone();
  }

  return fetch(url, {
    ...opts,
    headers,
  });
};
