import { ShieldCheck, AlertCircle, AlertTriangle } from 'lucide-react';
import { cn } from '../../lib/utils';

interface RiskBadgeProps {
  risk: string | undefined;
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
  className?: string;
}

export function RiskBadge({ risk, size = 'md', showIcon = true, className }: RiskBadgeProps) {
  const normalized = (risk || 'Low').trim().toLowerCase();

  let styles = 'bg-[#ECFDF5] text-[#059669] border-[#A7F3D0]';
  let Icon = ShieldCheck;
  let label = 'Low Risk';

  if (normalized === 'medium') {
    styles = 'bg-[#FFFBEB] text-[#D97706] border-[#FDE68A]';
    Icon = AlertCircle;
    label = 'Medium Risk';
  } else if (normalized === 'high') {
    styles = 'bg-[#FFF1F2] text-[#E11D48] border-[#FECDD3]';
    Icon = AlertTriangle;
    label = 'High Risk';
  }

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5 gap-1',
    md: 'text-xs font-medium px-2.5 py-1 gap-1.5',
    lg: 'text-sm font-semibold px-3 py-1.5 gap-2',
  }[size];

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border shadow-2xs font-medium',
        styles,
        sizeClasses,
        className
      )}
    >
      {showIcon && <Icon className={size === 'lg' ? 'w-4 h-4' : 'w-3.5 h-3.5'} />}
      <span>{label}</span>
    </span>
  );
}
