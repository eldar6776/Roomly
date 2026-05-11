import React from 'react';
import ReactDatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';

interface DatePickerProps {
  value: string;
  onChange: (value: string) => void;
  min?: string;
  label?: string;
}

export const DatePicker: React.FC<DatePickerProps> = ({ value, onChange, min, label }) => {
  // Convert string value (YYYY-MM-DD) to Date object
  const dateValue = value ? new Date(value + 'T00:00:00') : new Date();
  
  // Convert min string to Date object if provided
  const minDate = min ? new Date(min + 'T00:00:00') : undefined;

  const handleChange = (date: Date | null) => {
    if (date) {
      // Convert Date back to YYYY-MM-DD string
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      onChange(`${year}-${month}-${day}`);
    }
  };

  return (
    <div className="space-y-2">
      {label && <label className="text-sm font-medium">{label}</label>}
      <ReactDatePicker
        selected={dateValue}
        onChange={handleChange}
        minDate={minDate}
        dateFormat="dd.MM.yyyy"
        className="w-full px-3 py-2 bg-background border border-input rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        calendarClassName="bg-background border border-input shadow-lg"
        wrapperClassName="w-full"
        showPopperArrow={false}
      />
    </div>
  );
};
