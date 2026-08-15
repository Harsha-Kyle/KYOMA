import React, { useEffect } from "react";
import { Label } from "@/components/ui/label";
import { useSettings } from "@/context/SettingsContext";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

interface SettingsDropdownProps {
    id: string;
    defaultValue: string;
    label?: string;
    description?: string;
    className?: string;
    options: { [key: string]: string };
    onValueChange: (value: string) => void;
}

const SettingDropdown: React.FC<SettingsDropdownProps> = ({ id, defaultValue, label, description, className, options, onValueChange }) => {
    const { settings, updateSetting } = useSettings();

    useEffect(() => {
        // Initialize setting with default value if it doesn't exist
        if (settings[id] === undefined) {
            updateSetting(id, defaultValue);
        }
    }, []);

    const currentValue = settings[id] !== undefined ? settings[id] : defaultValue;

    useEffect(() => {
        onValueChange(currentValue)
    }, [currentValue])

    return (
        <div className={`flex items-start space-y-2 flex-col w-full ${className}`}>
            <Select value={currentValue} onValueChange={(value) => {
                updateSetting(id, value)
                onValueChange(value)
            }}>
                <Label htmlFor={id}>{label}</Label>
                <SelectTrigger className="w-full">
                    <SelectValue placeholder={label} />
                </SelectTrigger>
                <SelectContent>
                    {Object.entries(options).map(([key, value]) => (
                        <SelectItem key={key} value={key}>{value}</SelectItem>
                    ))}
                </SelectContent>
            </Select>
            <p className="text-sm text-muted-foreground">{description}</p>
        </div>
    );
};

export default SettingDropdown;