import React from 'react';
import { cn } from '../../lib/utils';
import { Loader2 } from 'lucide-react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  className,
  disabled,
  ...props
}: ButtonProps) {
  const baseStyles =
    'inline-flex items-center justify-center font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-[#245C46]/20 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer';

  const variantStyles = {
    primary: 'bg-[#245C46] text-white hover:bg-[#1b4736] active:bg-[#16382b]',
    secondary: 'bg-[#EBF1EA] text-[#245C46] hover:bg-[#DEE7DC] active:bg-[#D2DDD0]',
    outline: 'border border-[#E3E8E1] text-[#24312B] bg-white hover:bg-[#F7F8F4] active:bg-[#EDF0EB]',
    ghost: 'text-[#24312B] hover:bg-[#F0F3ED] active:bg-[#E5EAE2]',
    danger: 'bg-[#C65353] text-white hover:bg-[#b04545] active:bg-[#993b3b]',
  }[variant];

  const sizeStyles = {
    sm: 'text-xs px-2.5 py-1.5 gap-1.5',
    md: 'text-sm px-4 py-2 gap-2',
    lg: 'text-base px-5 py-2.5 gap-2.5',
  }[size];

  return (
    <button
      className={cn(baseStyles, variantStyles, sizeStyles, className)}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading && <Loader2 className="w-4 h-4 animate-spin text-current" />}
      {children}
    </button>
  );
}
