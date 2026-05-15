import { useEffect, useMemo, useState } from "react";
import { Users } from "lucide-react";
import { Select, SelectOption } from "@nous-research/ui/ui/components/select";
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
  const [currentProfile, setCurrentProfile] = useState("current");

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
          setCurrentProfile(active?.name || "current");
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
    const currentLabel = currentProfile === "current" ? "Current" : `Current: ${currentProfile}`;
    const items = [{ value: CURRENT_VALUE, label: currentLabel }];
    for (const profile of profiles) {
      if (seen.has(profile.name)) continue;
      seen.add(profile.name);
      items.push({ value: profile.name, label: profile.name });
    }
    return items;
  }, [currentProfile, profiles]);

  return (
    <div
      className={cn(
        "relative min-w-[10rem] shrink-0",
        "[&>div>button]:h-8 [&>div>button]:pl-8 [&>div>button]:pr-2",
        "[&>div>button]:font-mono-ui [&>div>button]:text-xs",
        className,
      )}
      aria-label="Profile"
      role="group"
    >
      <Users className="pointer-events-none absolute left-2.5 top-1/2 z-10 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <Select value={value || CURRENT_VALUE} onValueChange={onChange}>
        {options.map((option) => (
          <SelectOption key={option.value} value={option.value}>
            {option.label}
          </SelectOption>
        ))}
      </Select>
    </div>
  );
}
