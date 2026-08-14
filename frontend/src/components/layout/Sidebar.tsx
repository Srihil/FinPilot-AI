import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, MessageSquare, FileText, Users, Building2,
  Package, Upload, BarChart3, FileBarChart, CheckSquare,
  ScrollText, Settings, Zap, X, TrendingUp, ChevronRight,
} from 'lucide-react';
import { cn } from '../../utils/cn';
import { useAuth } from '../../auth/AuthContext';
import { getInitials } from '../../utils/format';
import { Avatar, AvatarFallback } from '../ui/avatar';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

const navItems = [
  { label: 'Dashboard', icon: LayoutDashboard, path: '/dashboard' },
  { label: 'AI Assistant', icon: MessageSquare, path: '/assistant' },
  { label: 'Transactions', icon: FileText, path: '/transactions' },
  { label: 'Customers', icon: Users, path: '/customers' },
  { label: 'Vendors', icon: Building2, path: '/vendors' },
  { label: 'Inventory', icon: Package, path: '/inventory' },
  { label: 'Uploads', icon: Upload, path: '/uploads' },
  { label: 'Analytics', icon: BarChart3, path: '/analytics' },
  { label: 'Reports', icon: FileBarChart, path: '/reports' },
  { label: 'Approvals', icon: CheckSquare, path: '/approvals' },
  { label: 'Audit Logs', icon: ScrollText, path: '/audit-logs' },
  { label: 'TallyPrime', icon: Zap, path: '/tally' },
  { label: 'Settings', icon: Settings, path: '/settings' },
];

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
          "fixed inset-y-0 left-0 z-50 w-64 flex flex-col bg-slate-900 text-white transition-transform duration-300 lg:relative lg:translate-x-0 lg:z-auto",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Logo */}
        <div className="flex items-center justify-between h-16 px-6 border-b border-slate-700/50">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
              <TrendingUp className="w-4 h-4 text-white" />
            </div>
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
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-0.5 scrollbar-hide">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => { if (window.innerWidth < 1024) onClose(); }}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 group",
                  isActive
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:bg-slate-800 hover:text-white"
                )}
              >
                <Icon className={cn("w-4 h-4 shrink-0", isActive ? "text-white" : "text-slate-500 group-hover:text-white")} />
                <span className="flex-1">{item.label}</span>
                {isActive && <ChevronRight className="w-3 h-3 text-white/70" />}
              </NavLink>
            );
          })}
        </nav>

        {/* User footer */}
        <div className="p-4 border-t border-slate-700/50">
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
