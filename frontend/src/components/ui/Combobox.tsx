import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, X } from 'lucide-react';
import { cn } from '../../utils/cn';

/**
 * Pass to <DialogContent onPointerDownOutside={preventDropdownDismissal}>
 * so Radix Dialog does not close when the user clicks inside a Combobox portal.
 */
export function preventDropdownDismissal(e: {
  preventDefault(): void;
  detail?: { originalEvent?: { target?: EventTarget | null } };
  target?: EventTarget | null;
}) {
  const target = (
    (e.detail as { originalEvent?: { target?: Element | null } } | undefined)?.originalEvent?.target ??
    (e as { target?: Element | null }).target
  ) as Element | null;
  if (target?.closest?.('[data-custom-dropdown-portal]')) {
    e.preventDefault();
  }
}

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
  const portalRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);

  // Sync display when value changes externally
  useEffect(() => {
    if (!open) setQuery(value);
  }, [value, open]);

  const filtered = options.filter(o =>
    !query || o.toLowerCase().includes(query.toLowerCase())
  );

  function computePos() {
    const wrap = inputRef.current?.closest('[data-combobox-wrap]');
    if (!wrap) return null;
    const r = wrap.getBoundingClientRect();
    const dropdownH = Math.min(filtered.length * 40 + 8, 220);
    const spaceBelow = window.innerHeight - r.bottom - 8;
    const top = spaceBelow >= dropdownH
      ? r.bottom + 4
      : r.top - dropdownH - 4;
    return { top, left: r.left, width: r.width };
  }

  const openDropdown = () => {
    setPos(computePos());
    setOpen(true);
  };

  function select(opt: string) {
    onChange(opt);
    setQuery(opt);
    setOpen(false);
  }

  const clear = (e: React.MouseEvent) => {
    e.preventDefault();
    onChange('');
    setQuery('');
    setOpen(false);
    inputRef.current?.focus();
  };

  const handleBlur = () => {
    setTimeout(() => {
      setQuery(value);
      setOpen(false);
    }, 150);
  };

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
    if (!open) openDropdown();
    if (!e.target.value) onChange('');
  };

  const handleFocus = () => {
    inputRef.current?.select();
    openDropdown();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { setQuery(value); setOpen(false); }
    if (e.key === 'Enter' && filtered.length >= 1) select(filtered[0]);
    if (e.key === 'ArrowDown' && !open) openDropdown();
  };

  // Reposition on scroll / resize
  useEffect(() => {
    if (!open) return;
    const update = () => setPos(computePos());
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, filtered.length]);

  return (
    <div data-combobox-wrap className={cn('relative', className)}>
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
            'focus:outline-none focus:ring-1 focus:ring-ring transition-colors',
            value ? 'pr-16' : 'pr-9',
            open && 'ring-1 ring-ring border-ring',
          )}
        />
        <div className="absolute right-2 flex items-center gap-0.5">
          {value && (
            <button
              type="button"
              onMouseDown={clear}
              className="p-1 rounded text-slate-400 hover:text-slate-700"
              tabIndex={-1}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            type="button"
            onMouseDown={e => {
              e.preventDefault();
              open ? setOpen(false) : openDropdown();
              inputRef.current?.focus();
            }}
            className="p-1 rounded text-slate-400 hover:text-slate-600"
            tabIndex={-1}
          >
            <ChevronDown className={cn('w-4 h-4 transition-transform', open && 'rotate-180')} />
          </button>
        </div>
      </div>

      {open && pos && createPortal(
        <div
          ref={portalRef}
          data-custom-dropdown-portal
          style={{
            position: 'fixed',
            top: pos.top,
            left: pos.left,
            width: Math.max(pos.width, 180),
            zIndex: 9999,
          }}
          className="bg-white border border-slate-200 rounded-xl shadow-xl"
        >
          <ul className="max-h-52 overflow-y-auto py-1 overscroll-contain">
            {filtered.length === 0 ? (
              <li className="px-3 py-3 text-sm text-slate-400 text-center">{emptyLabel}</li>
            ) : (
              filtered.map(opt => (
                <li key={opt}>
                  <button
                    type="button"
                    // Prevent focus loss (keeps input focused so blur handler doesn't close dropdown)
                    onMouseDown={e => e.preventDefault()}
                    // Use onClick (fires after mouseup) — reliable in all contexts
                    onClick={() => select(opt)}
                    className={cn(
                      'w-full text-left px-3 py-2 text-sm transition-colors cursor-pointer',
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
