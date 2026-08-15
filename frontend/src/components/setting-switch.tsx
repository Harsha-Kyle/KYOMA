import React from "react";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { useSettings } from "@/context/SettingsContext";

interface SettingsSwitchProps {
    id: string;
    label: string;
    description: string;
    className?: string;
    onClick?: (value: boolean) => void;
}

const SettingSwitch: React.FC<SettingsSwitchProps> = ({ id, label, description, className = "", onClick }) => {
    const { settings, updateSetting } = useSettings();

    return (
        <div className={`flex items-center space-x-2 w-full ${className}`}>
            <Switch
                id={id}
                checked={settings[id] || false}
                onClick={() => {
                    const newValue = !settings[id];
                    updateSetting(id, newValue);
                    onClick?.(newValue);
                }}
            />
            <Label htmlFor={id}>{label}</Label>
            <p className="text-sm text-muted-foreground">{description}</p>
        </div>
    );
};

export default SettingSwitch;