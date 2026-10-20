import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  UtensilsCrossed,
  LayoutDashboard,
  BrainCircuit,
  History,
  Activity,
  Database,
  Menu,
  X,
  Sparkles,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { HealthStatus } from '../../types';

interface NavbarProps {
  health?: HealthStatus;
  isLoadingHealth?: boolean;
}

export function Navbar({ health, isLoadingHealth }: NavbarProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navLinks = [
    { name: 'Dashboard', path: '/', icon: LayoutDashboard },
    { name: 'Prediction Sandbox', path: '/predict', icon: BrainCircuit },
    { name: 'Prediction History', path: '/history', icon: History },
    { name: 'Model Insights', path: '/models', icon: Activity },
    { name: 'Data Explorer', path: '/data', icon: Database },
  ];

  const isOnline = health?.status === 'healthy';

  return (
    <header className="sticky top-0 z-50 bg-white/95 backdrop-blur-md border-b border-[#E3E8E1]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Logo */}
          <NavLink to="/" className="flex items-center gap-3 group">
            <div className="w-10 h-10 rounded-xl bg-[#245C46] flex items-center justify-center text-white shadow-xs group-hover:bg-[#1b4736] transition-colors">
              <UtensilsCrossed className="w-5 h-5 text-[#E6B566]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-lg text-[#24312B] tracking-tight">SmartCanteen</span>
                <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-[#EBF1EA] text-[#245C46] rounded-md uppercase tracking-wider">
                  AI
                </span>
              </div>
              <p className="text-[11px] text-[#737D76] -mt-0.5 hidden sm:block">Sustainable University Dining</p>
            </div>
          </NavLink>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => {
              const Icon = link.icon;
              return (
                <NavLink
                  key={link.path}
                  to={link.path}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg transition-colors',
                      isActive
                        ? 'bg-[#EBF1EA] text-[#245C46] font-semibold'
                        : 'text-[#737D76] hover:text-[#24312B] hover:bg-[#F7F8F4]'
                    )
                  }
                >
                  <Icon className="w-4 h-4" />
                  <span>{link.name}</span>
                </NavLink>
              );
            })}
          </nav>

          {/* Status Badge & Actions */}
          <div className="hidden sm:flex items-center gap-3">
            <div
              className={cn(
                'flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border',
                isLoadingHealth
                  ? 'bg-gray-50 border-gray-200 text-gray-500'
                  : isOnline
                  ? 'bg-[#ECFDF5] border-[#A7F3D0] text-[#059669]'
                  : 'bg-[#FFF1F2] border-[#FECDD3] text-[#E11D48]'
              )}
            >
              <span
                className={cn(
                  'w-2 h-2 rounded-full',
                  isOnline ? 'bg-[#059669] animate-pulse' : 'bg-[#E11D48]'
                )}
              />
              <span>
                {isLoadingHealth
                  ? 'Connecting...'
                  : isOnline
                  ? `API Ready (${health?.record_count ?? 2600} records)`
                  : 'Backend Offline'}
              </span>
            </div>
          </div>

          {/* Mobile menu button */}
          <div className="flex md:hidden items-center">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-lg text-[#737D76] hover:text-[#24312B] hover:bg-[#F0F3ED] focus:outline-none"
              aria-label="Toggle Navigation Menu"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden border-b border-[#E3E8E1] bg-white px-4 pt-2 pb-4 space-y-1 shadow-lg">
          {navLinks.map((link) => {
            const Icon = link.icon;
            return (
              <NavLink
                key={link.path}
                to={link.path}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3.5 py-2.5 text-sm font-medium rounded-lg transition-colors',
                    isActive
                      ? 'bg-[#EBF1EA] text-[#245C46] font-semibold'
                      : 'text-[#737D76] hover:text-[#24312B] hover:bg-[#F7F8F4]'
                  )
                }
              >
                <Icon className="w-4 h-4" />
                <span>{link.name}</span>
              </NavLink>
            );
          })}

          <div className="pt-3 border-t border-[#F0F3ED] flex items-center justify-between text-xs text-[#737D76]">
            <span>System Status:</span>
            <span className={cn('font-medium', isOnline ? 'text-[#059669]' : 'text-[#E11D48]')}>
              {isOnline ? 'API Connected' : 'Offline'}
            </span>
          </div>
        </div>
      )}
    </header>
  );
}
