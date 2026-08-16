import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, X } from 'lucide-react';
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
  placeholder = 'Search…',
  emptyLabel = 'No matches',
  className,
}: ComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const portalRef = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);

  // Keep input display in sync when value changes from outside
  useEffect(() => {
    if (!open) setQuery(value);
  }, [value, open]);

  const filtered = options.filter(o =>
    !query || o.toLowerCase().includes(query.toLowerCase())
  );

  const openDropdown = () => {
    if (inputRef.current) {
      setRect(inputRef.current.closest('[data-combobox-wrap]')!.getBoundingClientRect());
    }
    setOpen(true);
  };

  const select = (opt: string) => {
    onChange(opt);
    setQuery(opt);
    setOpen(false);
  };

  const clear = () => {
    onChange('');
    setQuery('');
    setOpen(false);
    inputRef.current?.focus();
  };

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
    if (!open) openDropdown();
    // If user clears the input, clear the selection too
    if (!e.target.value) onChange('');
  };

  const handleFocus = () => {
    // Select all text so user can start typing immediately
    inputRef.current?.select();
    openDropdown();
  };

  const handleBlur = (e: React.FocusEvent) => {
    // Don't close if focus moves to portal dropdown
    if (portalRef.current?.contains(e.relatedTarget as Node)) return;
    // Restore display to selected value if query doesn't match exactly
    setTimeout(() => {
      setQuery(value);
      setOpen(false);
    }, 100);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { setQuery(value); setOpen(false); }
    if (e.key === 'Enter' && filtered.length === 1) { select(filtered[0]); }
    if (e.key === 'ArrowDown' && !open) openDropdown();
  };

  // Reposition on scroll/resize
  useEffect(() => {
    if (!open) return;
    const update = () => {
      const el = inputRef.current?.closest('[data-combobox-wrap]');
      if (el) setRect(el.getBoundingClientRect());
    };
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [open]);

  return (
    <div ref={wrapperRef} data-combobox-wrap className={cn('relative', className)}>
      <div className="relative flex items-center">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={handleInput}
          onFocus={handleFocus}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className={cn(
            'flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm',
            'focus:outline-none focus:ring-1 focus:ring-ring transition-colors pr-16',
            open && 'ring-1 ring-ring border-ring',
          )}
        />
        <div className="absolute right-2 flex items-center gap-0.5">
          {value && (
            <button
              type="button"
              onMouseDown={e => { e.preventDefault(); clear(); }}
              className="p-1 rounded text-slate-400 hover:text-slate-700"
              tabIndex={-1}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            type="button"
            onMouseDown={e => { e.preventDefault(); open ? setOpen(false) : openDropdown(); inputRef.current?.focus(); }}
            className="p-1 rounded text-slate-400 hover:text-slate-600"
            tabIndex={-1}
          >
            <ChevronDown className={cn('w-4 h-4 transition-transform', open && 'rotate-180')} />
          </button>
        </div>
      </div>

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
          <ul className="max-h-52 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-3 text-sm text-slate-400 text-center">{emptyLabel}</li>
            ) : (
              filtered.map(opt => (
                <li key={opt}>
                  <button
                    type="button"
                    onMouseDown={() => select(opt)}
                    className={cn(
                      'w-full text-left px-3 py-2 text-sm transition-colors',
                      opt === value
                        ? 'bg-indigo-50 text-indigo-700 font-medium'
                        : 'text-slate-700 hover:bg-slate-50',
                    )}
                  >
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
