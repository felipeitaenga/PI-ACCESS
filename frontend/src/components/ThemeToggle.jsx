import { useEffect } from "react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { Moon, Sun } from "lucide-react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  useEffect(() => {
    if (!theme) setTheme("dark");
  }, [theme, setTheme]);
  return (
    <Button
      variant="ghost"
      size="icon"
      data-testid="theme-toggle-button"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="text-slate-400 hover:text-slate-100"
    >
      {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
    </Button>
  );
}
