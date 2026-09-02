import { useTheme } from './ThemeProvider';

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label="다크·라이트 모드 전환"
      className="shrink-0 rounded-full border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-3 py-1.5 text-xs font-medium text-gray-600 dark:text-white/70 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
    >
      {theme === 'dark' ? '라이트 모드' : '다크 모드'}
    </button>
  );
}
