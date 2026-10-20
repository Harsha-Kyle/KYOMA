/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { createContext, useContext, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-client";

import { ttsManager } from "@/lib/ttsManager";

declare global {
  interface Window {
    __kyoma_settings_cache?: Record<string, any>;
    __kyoma_sessions_cache?: any[];
    __kyoma_models_cache?: any;
  }
}

interface SettingsContextType {
    settings: Record<string, any>;
    updateSetting: (key: string, value: any) => Promise<void>;
    loading: boolean;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export const SettingsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    // If the loading screen pre-fetched settings, use them immediately (no loading flash)
    const [settings, setSettings] = useState<Record<string, any>>(() => {
        const cached = window.__kyoma_settings_cache ?? {};
        if (cached['tts.provider']) {
            ttsManager.syncProviderFromCache(cached['tts.provider']);
        }
        return cached;
    });
    const [loading, setLoading] = useState(!window.__kyoma_settings_cache);

    useEffect(() => {
        if (window.__kyoma_settings_cache) {
            // Already have data from loading screen pre-fetch — skip re-fetch
            const cached = window.__kyoma_settings_cache;
            setSettings(cached);
            if (cached['tts.provider']) {
                ttsManager.syncProviderFromCache(cached['tts.provider']);
            }
            setLoading(false);
            return;
        }
        const fetchSettings = async () => {
            try {
                const response = await apiFetch('/api/settings');
                const data = await response.json();
                if (response.ok && data.settings) {
                    setSettings(data.settings);
                    window.__kyoma_settings_cache = data.settings;
                    if (data.settings['tts.provider']) {
                        ttsManager.syncProviderFromCache(data.settings['tts.provider']);
                    }
                } else {
                    console.error("Failed to fetch settings:", data.error);
                }
            } catch (error) {
                console.error("Error fetching settings:", error);
            } finally {
                setLoading(false);
            }
        };
        fetchSettings();
    }, []);

    const updateSetting = async (key: string, value: any) => {
        try {
            setSettings((prev) => ({ ...prev, [key]: value }));
            const response = await apiFetch('/api/settings/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings: { [key]: value } }),
            });
            const data = await response.json();
            if (response.ok) {
                // Update cache too
                if (window.__kyoma_settings_cache) {
                    window.__kyoma_settings_cache[key] = value;
                }
                console.log("Settings updated successfully:", data.message);
            } else {
                console.error("Failed to update settings:", data.error);
            }
        } catch (error) {
            console.error("Error updating settings:", error);
        }
    };

    return (
        <SettingsContext.Provider value={{ settings, updateSetting, loading }}>
            {children}
        </SettingsContext.Provider>
    );
};

export const useSettings = (): SettingsContextType => {
    const context = useContext(SettingsContext);
    if (!context) {
        throw new Error("useSettings must be used within a SettingsProvider");
    }
    return context;
};