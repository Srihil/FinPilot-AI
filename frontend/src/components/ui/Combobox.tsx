import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, Check, Search } from 'lucide-react';
import { cn } from '../../utils/cn';

interface ComboboxProps {
  options: string[];
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  emptyLabel?: string;
  clearLabel?: string;
  className?: string;
}

export function Combobox({
  options,
  value,
  onChange,
  placeholder = 'Type to search…',
  emptyLabel = 'No matches',
  clearLabel = '— Clear selection',
  className,
}: ComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const portalRef = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);

  const filtered = options.filter(o =>
    !query || o.toLowerCase().includes(query.toLowerCase())
  );

  const openDropdown = useCallback(() => {
    if (inputRef.current) {
      setRect(inputRef.current.getBoundingClientRect());
      setQuery('');
    }
    setOpen(true);
  }, []);

  const select = (opt: string) => {
    onChange(opt);
    setOpen(false);
    setQuery('');
  };

  const clear = () => {
    onChange('');
    setOpen(false);
    setQuery('');
  };

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (
        portalRef.current && !portalRef.current.contains(e.target as Node) &&
        inputRef.current && !inputRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
        setQuery('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // Reposition on scroll/resize
  useEffect(() => {
    if (!open) return;
    const update = () => {
      if (inputRef.current) setRect(inputRef.current.getBoundingClientRect());
    };
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setOpen(false); setQuery(''); }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open]);

  return (
    <div className={cn('relative', className)}>
      {/* Trigger button — shows selected value */}
      <button
        type="button"
        ref={inputRef as unknown as React.RefObject<HTMLButtonElement>}
        onClick={() => (open ? setOpen(false) : openDropdown())}
        className={cn(
          'flex items-center justify-between w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm',
          'focus:outline-none focus:ring-1 focus:ring-ring transition-colors',
          'hover:border-slate-400',
          open && 'ring-1 ring-ring border-ring',
        )}
      >
        <span className={value ? 'text-slate-900' : 'text-slate-400'}>
          {value || placeholder}
        </span>
        <ChevronDown className={cn('w-4 h-4 text-slate-400 transition-transform shrink-0', open && 'rotate-180')} />
      </button>

      {/* Portal dropdown */}
      {open && rect && createPortal(
        <div
          ref={portalRef}
          style={{
            position: 'fixed',
            top: rect.bottom + 4,
            left: rect.left,
            width: rect.width,
            zIndex: 9999,
          }}
          className="bg-white border border-slate-200 rounded-xl shadow-xl overflow-hidden"
        >
          {/* Search input */}
          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-100">
            <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search…"
              className="flex-1 text-sm outline-none bg-transparent text-slate-700 placeholder:text-slate-400"
            />
          </div>

          {/* Options list */}
          <ul className="max-h-52 overflow-y-auto py-1">
            {/* Clear option */}
            {value && (
              <li>
                <button
                  type="button"
                  onMouseDown={() => clear()}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-slate-400 hover:bg-slate-50 hover:text-slate-600 italic"
                >
                  {clearLabel}
                </button>
              </li>
            )}

            {filtered.length === 0 ? (
              <li className="px-3 py-3 text-sm text-slate-400 text-center">{emptyLabel}</li>
            ) : (
              filtered.map(opt => (
                <li key={opt}>
                  <button
                    type="button"
                    onMouseDown={() => select(opt)}
                    className={cn(
                      'w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors',
                      opt === value
                        ? 'bg-indigo-50 text-indigo-700 font-medium'
                        : 'text-slate-700 hover:bg-slate-50',
                    )}
                  >
                    <Check className={cn('w-3.5 h-3.5 shrink-0', opt === value ? 'text-indigo-600' : 'invisible')} />
                    {opt}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>,
        document.body
      )}
    </div>
  );
}
