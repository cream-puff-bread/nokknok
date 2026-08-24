import type { ButtonHTMLAttributes } from 'react';

// contracts/ui-system.md 컴포넌트 클래스 — 기본 버튼 / 보조 버튼.
const VARIANT_CLASS = {
  primary:
    'bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:bg-gray-300 ' +
    'rounded-lg px-4 py-2 text-white text-sm font-medium transition-colors',
  secondary:
    'bg-white hover:bg-gray-50 border border-gray-300 ' +
    'rounded-lg px-4 py-2 text-gray-700 text-sm font-medium transition-colors',
} as const;

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof VARIANT_CLASS;
}

export function Button({ variant = 'primary', className = '', ...rest }: ButtonProps) {
  return <button className={`${VARIANT_CLASS[variant]} ${className}`} {...rest} />;
}
