import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Users } from "lucide-react";
import { api, type ProfileInfo } from "@/lib/api";
import { cn } from "@/lib/utils";

const CURRENT_VALUE = "current";

interface ProfileSelectorProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

function normalizePath(value?: string | null): string {
  return (value || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}

export function ProfileSelector({ value, onChange, className }: ProfileSelectorProps) {
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [activeProfile, setActiveProfile] = useState("default");
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      Promise.allSettled([api.getProfiles(), api.getStatus()]).then(([profilesResult, statusResult]) => {
        if (cancelled) return;
        const nextProfiles =
          profilesResult.status === "fulfilled" ? profilesResult.value.profiles : [];
        setProfiles(nextProfiles);
        if (statusResult.status === "fulfilled") {
          const activeHome = normalizePath(statusResult.value.hermes_home);
          const active = nextProfiles.find((profile) => normalizePath(profile.path) === activeHome);
          setActiveProfile(active?.name || "default");
        }
      });
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, []);

  const options = useMemo(() => {
    const seen = new Set<string>();
    const items: { value: string; label: string }[] = [];
    for (const profile of profiles) {
      if (seen.has(profile.name)) continue;
      seen.add(profile.name);
      items.push({ value: profile.name, label: profile.name });
    }
    if (items.length === 0) {
      items.push({ value: activeProfile, label: activeProfile });
    }
    return items;
  }, [activeProfile, profiles]);

  const selectedValue = value && value !== CURRENT_VALUE ? value : activeProfile;
  const selectedLabel = options.find((option) => option.value === selectedValue)?.label ?? selectedValue;

  const updateMenuPosition = () => {
    const rect = buttonRef.current?.getBoundingClientRect();
    if (!rect) return;
    setMenuStyle({
      left: rect.left,
      top: rect.bottom + 2,
      width: rect.width,
    });
  };

  useEffect(() => {
    if (!open) return;
    updateMenuPosition();
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (buttonRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, true);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("scroll", updateMenuPosition, true);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div
      className={cn(
        "relative h-8 w-[8.75rem] shrink-0 text-xs text-muted-foreground",
        className,
      )}
    >
      <button
        ref={buttonRef}
        type="button"
        className="relative flex h-full w-full items-center border border-border bg-background/40 pl-8 pr-6 text-left font-mono-ui text-xs text-foreground outline-none hover:border-primary/70 focus:border-primary"
        aria-label="Profile"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => {
          if (!open) updateMenuPosition();
          setOpen((next) => !next);
        }}
      >
        <Users className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate">{selectedLabel}</span>
        <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
      </button>
      {open &&
        createPortal(
          <div
            ref={menuRef}
            className="fixed z-50 border border-border bg-background/20 backdrop-blur-sm"
            role="listbox"
            style={menuStyle}
          >
            {options.map((option) => (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={option.value === selectedValue}
                className={cn(
                  "flex h-8 w-full items-center gap-2 bg-transparent px-3 text-left font-mono-ui text-xs",
                  "text-foreground hover:bg-foreground/10",
                  option.value === selectedValue && "font-bold",
                )}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
              >
                <span className="w-3 text-center">{option.value === selectedValue ? "✓" : ""}</span>
                <span className="min-w-0 flex-1 truncate">{option.label}</span>
              </button>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}
