import { useState, useRef, useEffect } from 'react';
import { Menu, ChevronDown, LogOut, User, Settings, Search, X } from 'lucide-react';
import { ActivityTriggerButton } from '../ui/TallyActivityDrawer';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { getInitials } from '../../utils/format';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '../ui/dropdown-menu';
import { Avatar, AvatarFallback } from '../ui/avatar';

interface TopBarProps {
  onMenuClick: () => void;
  onActivityClick: () => void;
}

const pageTitles: Record<string, string> = {
  '/dashboard':  'Dashboard',
  '/assistant':  'AI Assistant',
  '/ai-create':  'Create with AI',
  '/management': 'Management',
  '/uploads':    'Bulk Uploads',
  '/analytics':  'Analytics',
  '/reports':    'Reports',
  '/audit-logs': 'Audit Logs',
  '/tally':      'TallyPrime',
  '/settings':   'Settings',
};

function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    navigate(`/management?search=${encodeURIComponent(query.trim())}`);
    setQuery('');
    setOpen(false);
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen(o => !o);
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="hidden sm:flex items-center gap-2 px-3 py-1.5 text-sm text-slate-400 bg-slate-100 rounded-lg hover:bg-slate-200 transition-colors"
      >
        <Search className="w-3.5 h-3.5" />
        <span>Search…</span>
        <kbd className="ml-1 text-xs font-mono bg-white border border-slate-200 rounded px-1">⌘K</kbd>
      </button>
    );
  }

  return (
    <form onSubmit={handleSearch} className="flex items-center gap-2">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
        <input
          ref={inputRef}
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search customers, vendors, ledgers…"
          className="pl-9 pr-3 py-1.5 text-sm border border-indigo-300 rounded-lg outline-none focus:ring-2 focus:ring-indigo-200 w-64 bg-white"
        />
      </div>
      <button type="button" onClick={() => { setOpen(false); setQuery(''); }} className="p-1 text-slate-400 hover:text-slate-600">
        <X className="w-4 h-4" />
      </button>
    </form>
  );
}

export function TopBar({ onMenuClick, onActivityClick }: TopBarProps) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const pageTitle = pageTitles[location.pathname] || 'FinPilot AI';

  return (
    <header className="h-16 border-b border-slate-200 bg-white flex items-center justify-between px-4 lg:px-6 shrink-0">
      <div className="flex items-center gap-4">
        <button
          onClick={onMenuClick}
          className="lg:hidden p-2 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-md transition-colors"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{pageTitle}</h1>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <GlobalSearch />
        <ActivityTriggerButton onClick={onActivityClick} />
        {/* User menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-slate-100 transition-colors">
              <Avatar className="w-8 h-8">
                <AvatarFallback className="text-xs bg-indigo-600 text-white">
                  {getInitials(user?.full_name || 'U')}
                </AvatarFallback>
              </Avatar>
              <div className="hidden sm:block text-left">
                <p className="text-sm font-medium text-slate-900">{user?.full_name}</p>
                <p className="text-xs text-slate-500">{user?.role}</p>
              </div>
              <ChevronDown className="w-4 h-4 text-slate-400 hidden sm:block" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <div>
                <p className="font-medium">{user?.full_name}</p>
                <p className="text-xs text-slate-500 font-normal">{user?.email}</p>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate('/settings')}>
              <User className="mr-2 h-4 w-4" />
              Profile
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate('/settings')}>
              <Settings className="mr-2 h-4 w-4" />
              Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout} className="text-red-600 focus:text-red-700 focus:bg-red-50">
              <LogOut className="mr-2 h-4 w-4" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
