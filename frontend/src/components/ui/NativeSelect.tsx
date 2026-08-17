import { cn } from '../../utils/cn';

interface NativeSelectProps {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

const cls = [
  'w-full rounded-md border border-input bg-background',
  'px-3 py-2 text-sm shadow-sm',
  'focus:outline-none focus:ring-1 focus:ring-ring',
  'disabled:opacity-50 disabled:cursor-not-allowed',
].join(' ');

export function NativeSelect({
  value, onChange, options, placeholder = '— Select —', className, disabled,
}: NativeSelectProps) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      disabled={disabled}
      className={cn(cls, className)}
    >
      <option value="">{placeholder}</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}
