import React from 'react';
import { Input } from './input';

interface TimePickerProps {
  value: string;
  onChange: (value: string) => void;
  label?: string;
}

export const TimePicker: React.FC<TimePickerProps> = ({ value, onChange, label }) => {
  const [hours, minutes] = value.split(':');

  const handleHoursChange = (newHours: string) => {
    const h = Math.max(0, Math.min(23, parseInt(newHours) || 0));
    onChange(`${h.toString().padStart(2, '0')}:${minutes}`);
  };

  const handleMinutesChange = (newMinutes: string) => {
    const m = Math.max(0, Math.min(59, parseInt(newMinutes) || 0));
    onChange(`${hours}:${m.toString().padStart(2, '0')}`);
  };

  return (
    <div className="space-y-2">
      {label && <label className="text-sm font-medium">{label}</label>}
      <div className="flex items-center gap-2">
        <Input
          type="number"
          min="0"
          max="23"
          value={hours}
          onChange={(e) => handleHoursChange(e.target.value)}
          className="w-20 text-center"
          placeholder="HH"
        />
        <span className="text-xl font-bold">:</span>
        <Input
          type="number"
          min="0"
          max="59"
          value={minutes}
          onChange={(e) => handleMinutesChange(e.target.value)}
          className="w-20 text-center"
          placeholder="MM"
        />
      </div>
    </div>
  );
};
