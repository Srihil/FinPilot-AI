import { useState, useRef, useEffect } from 'react';

/**
 * Pass to <DialogContent onPointerDownOutside={preventDropdownDismissal}>
 * so Radix Dialog doesn't close when the user clicks inside a portal dropdown.
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
  emptyLabel = 'No options — type a value directly',
  className,
}: ComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const portalRef = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);

  // Sync display when value changes externally
  useEffect(() => {
    if (!open) setQuery(value);
  }, [value, open]);

  const filtered = options.filter(o =>
    !query || o.toLowerCase().includes(query.toLowerCase())
  );

  const openDropdown = () => {
    const wrap = inputRef.current?.closest('[data-combobox-wrap]');
    if (wrap) setRect(wrap.getBoundingClientRect());
    setOpen(true);
  };

  const select = (opt: string) => {
    onChange(opt);
    setQuery(opt);
    setOpen(false);
    inputRef.current?.focus();
  };

  const clear = (e: React.MouseEvent) => {
    e.preventDefault();
    onChange('');
    setQuery('');
    setOpen(false);
    inputRef.current?.focus();
  };

  // On blur: if the typed query is non-empty and differs from current value,
  // accept it as a free-text value so users can type godown/party names
  // even when the list hasn't been synced yet.
  const handleBlur = () => {
    setTimeout(() => {
      const trimmed = query.trim();
      if (trimmed && trimmed !== value) {
        onChange(trimmed);
        setQuery(trimmed);
      } else if (!trimmed && value) {
        // User cleared the field
        onChange('');
        setQuery('');
      } else {
        setQuery(value);
      }
      setOpen(false);
    }, 80);
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
    if (e.key === 'Escape') {
      setQuery(value);
      setOpen(false);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filtered.length >= 1) {
        select(filtered[0]);
      } else if (query.trim()) {
        // Accept free-text on Enter when no matches
        onChange(query.trim());
        setOpen(false);
      }
    } else if (e.key === 'ArrowDown' && !open) {
      openDropdown();
    }
  };

  // Reposition on scroll / resize
  useEffect(() => {
    if (!open) return;
    const update = () => {
      const wrap = inputRef.current?.closest('[data-combobox-wrap]');
      if (wrap) setRect(wrap.getBoundingClientRect());
    };
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [open]);

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

      {open && rect && createPortal(
        <div
          ref={portalRef}
          style={{
            position: 'fixed',
            top: rect.bottom + 4,
            left: rect.left,
            width: Math.max(rect.width, 180),
            zIndex: 9999,
          }}
          // Stop pointer events reaching Radix Dialog's outside-click handler
          onPointerDown={e => e.stopPropagation()}
          data-custom-dropdown-portal
          className="bg-white border border-slate-200 rounded-xl shadow-xl overflow-hidden"
        >
          <ul className="max-h-52 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-3 text-xs text-slate-400 text-center italic">{emptyLabel}</li>
            ) : (
              filtered.map(opt => (
                <li key={opt}>
                  <button
                    type="button"
                    // onMouseDown + preventDefault: prevents input blur so the
                    // dropdown stays open while we complete the selection.
                    // Using onClick alone would fail because blur fires first
                    // and closes the dropdown before click can register.
                    onMouseDown={e => {
                      e.preventDefault();
                      select(opt);
                    }}
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
