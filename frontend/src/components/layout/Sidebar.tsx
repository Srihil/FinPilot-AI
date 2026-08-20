import { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, MessageSquare, Upload, BarChart3, FileBarChart,
  ScrollText, Settings, Zap, Wand2, ChevronRight,
  ChevronDown, X, BookOpen, FolderOpen, FileText, Package, Scale,
  Warehouse, Tag, ArrowLeftRight,
  Receipt,
} from 'lucide-react';
import { cn } from '../../utils/cn';
import { useAuth } from '../../auth/AuthContext';
import { getInitials } from '../../utils/format';
import { Avatar, AvatarFallback } from '../ui/avatar';
import { FinPilotLogo } from '../ui/FinPilotLogo';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

type NavItem =
  | { type: 'link'; label: string; icon: React.ElementType; path: string }
  | { type: 'section'; label: string; icon: React.ElementType; children: { label: string; path: string; icon?: React.ElementType }[] };

const navStructure: NavItem[] = [
  {
    type: 'link',
    label: 'Dashboard',
    icon: LayoutDashboard,
    path: '/dashboard',
  },
  {
    type: 'section',
    label: 'AI',
    icon: Wand2,
    children: [
      { label: 'Assistant', path: '/assistant', icon: MessageSquare },
      { label: 'Create with AI', path: '/ai-create', icon: Wand2 },
    ],
  },
  {
    type: 'section',
    label: 'Accounting',
    icon: BookOpen,
    children: [
      { label: 'Ledgers', path: '/accounting/ledgers', icon: BookOpen },
      { label: 'Account Groups', path: '/accounting/groups', icon: FolderOpen },
      { label: 'Voucher Types', path: '/accounting/voucher-types', icon: Receipt },
      { label: 'All Vouchers', path: '/accounting/vouchers', icon: FileText },
      { label: 'Sales', path: '/accounting/vouchers/sales', icon: FileText },
      { label: 'Purchase', path: '/accounting/vouchers/purchase', icon: FileText },
      { label: 'Receipt', path: '/accounting/vouchers/receipt', icon: FileText },
      { label: 'Payment', path: '/accounting/vouchers/payment', icon: FileText },
      { label: 'Journal', path: '/accounting/vouchers/journal', icon: FileText },
      { label: 'Contra', path: '/accounting/vouchers/contra', icon: FileText },
      { label: 'Credit Note', path: '/accounting/vouchers/credit_note', icon: FileText },
      { label: 'Debit Note', path: '/accounting/vouchers/debit_note', icon: FileText },
    ],
  },
  {
    type: 'section',
    label: 'Inventory',
    icon: Package,
    children: [
      { label: 'Stock Items', path: '/inventory/stock-items', icon: Package },
      { label: 'Stock Groups', path: '/inventory/stock-groups', icon: FolderOpen },
      { label: 'Stock Categories', path: '/inventory/stock-categories', icon: Tag },
      { label: 'Units', path: '/inventory/units', icon: Scale },
      { label: 'Godowns', path: '/inventory/godowns', icon: Warehouse },
      { label: 'Stock Journal', path: '/inventory/stock-transactions', icon: ArrowLeftRight },
    ],
  },
  { type: 'link', label: 'Reports', icon: FileBarChart, path: '/reports' },
  { type: 'link', label: 'Analytics', icon: BarChart3, path: '/analytics' },
  { type: 'link', label: 'Bulk Upload', icon: Upload, path: '/uploads' },
  { type: 'link', label: 'Audit Logs', icon: ScrollText, path: '/audit-logs' },
  {
    type: 'section',
    label: 'TallyPrime',
    icon: Zap,
    children: [
      { label: 'Sync Center', path: '/tally', icon: Zap },
    ],
  },
  { type: 'link', label: 'Settings', icon: Settings, path: '/settings' },
];

function NavSection({
  item,
  onClose,
}: {
  item: Extract<NavItem, { type: 'section' }>;
  onClose: () => void;
}) {
  const location = useLocation();
  const isChildActive = item.children.some(c => location.pathname.startsWith(c.path));
  const [open, setOpen] = useState(isChildActive);
  const Icon = item.icon;

  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        className={cn(
          'flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150',
          isChildActive
            ? 'bg-slate-800 text-white'
            : 'text-slate-400 hover:bg-slate-800 hover:text-white',
        )}
      >
        <Icon className={cn('w-4 h-4 shrink-0', isChildActive ? 'text-indigo-400' : 'text-slate-500')} />
        <span className="flex-1 text-left">{item.label}</span>
        {open ? (
          <ChevronDown className="w-3 h-3 text-slate-500" />
        ) : (
          <ChevronRight className="w-3 h-3 text-slate-500" />
        )}
      </button>

      {open && (
        <div className="ml-4 mt-0.5 border-l border-slate-700/50 pl-3 space-y-0.5">
          {item.children.map(child => {
            const ChildIcon = child.icon;
            const isActive = location.pathname === child.path;
            return (
              <NavLink
                key={child.path}
                to={child.path}
                onClick={() => { if (window.innerWidth < 1024) onClose(); }}
                className={cn(
                  'flex items-center gap-2.5 px-2.5 py-2 rounded-md text-xs font-medium transition-all duration-150',
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-400 hover:bg-slate-700 hover:text-white',
                )}
              >
                {ChildIcon && <ChildIcon className="w-3.5 h-3.5 shrink-0" />}
                <span>{child.label}</span>
              </NavLink>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { user } = useAuth();
  const location = useLocation();

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-64 flex flex-col bg-slate-900 text-white transition-transform duration-300 lg:relative lg:translate-x-0 lg:z-auto',
          isOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        {/* Logo */}
        <div className="flex items-center justify-between h-16 px-6 border-b border-slate-700/50 shrink-0">
          <div className="flex items-center gap-2">
            <FinPilotLogo size={32} />
            <span className="text-lg font-bold text-white">FinPilot AI</span>
          </div>
          <button
            onClick={onClose}
            className="lg:hidden text-slate-400 hover:text-white p-1"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-3 px-3 space-y-0.5 scrollbar-hide">
          {navStructure.map((item, idx) => {
            if (item.type === 'link') {
              const Icon = item.icon;
              const isActive = location.pathname === item.path;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  onClick={() => { if (window.innerWidth < 1024) onClose(); }}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 group',
                    isActive
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-slate-400 hover:bg-slate-800 hover:text-white',
                  )}
                >
                  <Icon className={cn('w-4 h-4 shrink-0', isActive ? 'text-white' : 'text-slate-500 group-hover:text-white')} />
                  <span className="flex-1">{item.label}</span>
                  {isActive && <ChevronRight className="w-3 h-3 text-white/70" />}
                </NavLink>
              );
            }

            return <NavSection key={`section-${idx}`} item={item} onClose={onClose} />;
          })}
        </nav>

        {/* User footer */}
        <div className="p-4 border-t border-slate-700/50 shrink-0">
          <div className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-slate-800 transition-colors cursor-pointer">
            <Avatar className="w-8 h-8">
              <AvatarFallback className="text-xs bg-indigo-600 text-white">
                {getInitials(user?.full_name || 'U')}
              </AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">{user?.full_name}</p>
              <p className="text-xs text-slate-400 truncate">{user?.company_name}</p>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
