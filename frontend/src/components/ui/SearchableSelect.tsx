import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, Search, Check } from 'lucide-react';
import { cn } from '../../utils/cn';

interface SearchableSelectProps {
  options: string[];
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  className?: string;
}

/**
 * Searchable dropdown that combines the reliable UX of a native <select>
 * (click trigger → list appears) with a search/filter input so users can
 * type to narrow long option lists.
 *
 * Works inside Radix Dialogs: the dropdown is portal-rendered with
 * data-custom-dropdown-portal so the parent Dialog can exclude these clicks
 * from its outside-click dismissal handler.
 */
export function SearchableSelect({
  options,
  value,
  onChange,
  placeholder = '— Select —',
  searchPlaceholder = 'Search…',
  className,
}: SearchableSelectProps) {
  const [open, setOpen]     = useState(false);
  const [search, setSearch] = useState('');
  const triggerRef          = useRef<HTMLButtonElement>(null);
  const panelRef            = useRef<HTMLDivElement>(null);
  const searchInputRef      = useRef<HTMLInputElement>(null);
  const [rect, setRect]     = useState<DOMRect | null>(null);

  const filtered = options.filter(o =>
    !search || o.toLowerCase().includes(search.toLowerCase())
  );

  function openPanel() {
    const r = triggerRef.current?.getBoundingClientRect();
    if (r) setRect(r);
    setOpen(true);
    setSearch('');
    // Focus search input after panel renders
    requestAnimationFrame(() => searchInputRef.current?.focus());
  }

  function closePanel() {
    setOpen(false);
    setSearch('');
  }

  function select(opt: string) {
    onChange(opt);
    closePanel();
    triggerRef.current?.focus();
  }

  // Close when clicking outside the panel
  useEffect(() => {
    if (!open) return;
    const handle = (e: MouseEvent) => {
      if (!panelRef.current?.contains(e.target as Node)) {
        closePanel();
      }
    };
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [open]);

  // Reposition on scroll / resize
  useEffect(() => {
    if (!open) return;
    const update = () => {
      const r = triggerRef.current?.getBoundingClientRect();
      if (r) setRect(r);
    };
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [open]);

  return (
    <div className={cn('relative', className)}>
      {/* ── Trigger ─────────────────────────────────────────────────────── */}
      <button
        ref={triggerRef}
        type="button"
        onClick={openPanel}
        className={cn(
          'w-full flex items-center justify-between px-3 py-2 text-sm',
          'rounded-md border border-input bg-background shadow-sm',
          'focus:outline-none focus:ring-1 focus:ring-ring',
          'hover:bg-slate-50 transition-colors text-left',
          open && 'ring-1 ring-ring border-ring',
        )}
      >
        <span className={cn('truncate', value ? 'text-slate-900' : 'text-slate-400')}>
          {value || placeholder}
        </span>
        <ChevronDown className={cn('w-4 h-4 text-slate-400 shrink-0 ml-2 transition-transform', open && 'rotate-180')} />
      </button>

      {/* ── Dropdown panel (portal) ──────────────────────────────────────── */}
      {open && rect && createPortal(
        <div
          ref={panelRef}
          data-custom-dropdown-portal
          style={{
            position: 'fixed',
            top: rect.bottom + 4,
            left: rect.left,
            width: Math.max(rect.width, 200),
            zIndex: 9999,
          }}
          // Stop propagation so Radix Dialog's outside-click handler doesn't
          // fire and close the parent Dialog when the user clicks here.
          onPointerDown={e => e.stopPropagation()}
          className="bg-white border border-slate-200 rounded-xl shadow-2xl overflow-hidden"
        >
          {/* Search input */}
          <div className="p-2 border-b border-slate-100">
            <div className="relative">
              <Search className="absolute left-2.5 top-2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
              <input
                ref={searchInputRef}
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder={searchPlaceholder}
                onMouseDown={e => e.stopPropagation()}
                onKeyDown={e => {
                  if (e.key === 'Escape') closePanel();
                  if (e.key === 'Enter' && filtered.length === 1) select(filtered[0]);
                }}
                className="w-full pl-8 pr-3 py-1.5 text-sm border border-slate-200 rounded-lg
                  focus:outline-none focus:ring-1 focus:ring-indigo-400 bg-slate-50"
              />
            </div>
          </div>

          {/* Option list */}
          <ul className="max-h-52 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-3 text-sm text-slate-400 text-center italic">
                {options.length === 0 ? 'Loading…' : 'No matches'}
              </li>
            ) : (
              filtered.map(opt => (
                <li key={opt}>
                  <button
                    type="button"
                    onMouseDown={e => {
                      e.preventDefault(); // keep input focused, don't blur trigger
                      select(opt);
                    }}
                    className={cn(
                      'w-full flex items-center justify-between px-3 py-2.5 text-sm transition-colors',
                      opt === value
                        ? 'bg-indigo-600 text-white font-medium'
                        : 'text-slate-700 hover:bg-slate-50',
                    )}
                  >
                    <span>{opt}</span>
                    {opt === value && <Check className="w-3.5 h-3.5 shrink-0" />}
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

/**
 * Pass this to <DialogContent onPointerDownOutside={...}> so Radix Dialog
 * doesn't close itself when the user clicks inside a SearchableSelect or
 * Combobox portal dropdown.
 */
export function preventDropdownDismissal(e: { preventDefault(): void; target?: EventTarget | null; detail?: { originalEvent?: { target?: EventTarget | null } } }) {
  const target = (
    (e.detail as { originalEvent?: { target?: Element | null } } | undefined)?.originalEvent?.target ??
    (e as { target?: Element | null }).target
  ) as Element | null;
  if (target?.closest?.('[data-custom-dropdown-portal]')) {
    e.preventDefault();
  }
}
