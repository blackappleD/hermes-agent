"""Profile gateway bootstrap helpers.

Hermes profiles have isolated ``HERMES_HOME`` directories and therefore
isolated gateway PID files, event projection stores, and Linz/NATS consumers.
This module starts missing profile gateways as detached children when a flow
needs all profiles to be actively listening.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from hermes_cli._subprocess_compat import windows_detach_popen_kwargs
from hermes_cli.gateway import get_python_path
from hermes_cli.profiles import ProfileInfo, get_active_profile_name, list_profiles


class _PopenFactory(Protocol):
    def __call__(self, args: list[str], **kwargs) -> subprocess.Popen: ...


@dataclass(frozen=True)
class ProfileGatewayLaunchResult:
    profile: str
    path: Path
    status: str
    pid: int | None = None
    error: str = ""


def _gateway_args_for_profile(profile: ProfileInfo) -> list[str]:
    return [
        get_python_path(),
        "-m",
        "hermes_cli.main",
        "--profile",
        profile.name,
        "gateway",
        "run",
        "--replace",
        "--quiet",
    ]


def _is_current_profile(profile: ProfileInfo) -> bool:
    try:
        if profile.name == get_active_profile_name():
            return True
    except Exception:
        pass
    current_home = os.environ.get("HERMES_HOME")
    if not current_home:
        return False
    try:
        return Path(current_home).resolve() == profile.path.resolve()
    except (OSError, ValueError):
        return str(Path(current_home)) == str(profile.path)


def start_profile_gateways(
    *,
    profiles: Iterable[ProfileInfo] | None = None,
    popen_factory: _PopenFactory = subprocess.Popen,
    exclude_current_profile: bool = False,
) -> list[ProfileGatewayLaunchResult]:
    """Start detached gateways for profiles that are not already running.

    Failures are returned as structured results instead of being raised.  A
    caller can still proceed when one profile is unavailable, while other
    profiles continue listening and writing their event projection stores.
    """
    try:
        profile_list = list(profiles) if profiles is not None else list_profiles()
    except Exception as exc:
        return [
            ProfileGatewayLaunchResult(
                profile="*",
                path=Path(""),
                status="failed",
                error=f"could not list profiles: {exc}",
            )
        ]

    results: list[ProfileGatewayLaunchResult] = []
    for profile in profile_list:
        if exclude_current_profile and _is_current_profile(profile):
            results.append(
                ProfileGatewayLaunchResult(
                    profile=profile.name,
                    path=profile.path,
                    status="skipped_current",
                )
            )
            continue

        if profile.gateway_running:
            results.append(
                ProfileGatewayLaunchResult(
                    profile=profile.name,
                    path=profile.path,
                    status="already_running",
                )
            )
            continue

        env = os.environ.copy()
        env["HERMES_HOME"] = str(profile.path)
        env["HERMES_GATEWAY_DETACHED"] = "1"

        try:
            process = popen_factory(
                _gateway_args_for_profile(profile),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                env=env,
                **windows_detach_popen_kwargs(),
            )
        except Exception as exc:
            results.append(
                ProfileGatewayLaunchResult(
                    profile=profile.name,
                    path=profile.path,
                    status="failed",
                    error=str(exc),
                )
            )
            continue

        results.append(
            ProfileGatewayLaunchResult(
                profile=profile.name,
                path=profile.path,
                status="started",
                pid=getattr(process, "pid", None),
            )
        )

    return results


def print_profile_gateway_launch_results(
    results: Iterable[ProfileGatewayLaunchResult],
    *,
    heading: str = "Starting profile gateways...",
    include_skipped: bool = False,
) -> None:
    """Print a compact, user-facing launch summary."""
    rows = list(results)
    if not include_skipped:
        rows = [row for row in rows if row.status != "skipped_current"]
    if not rows:
        return

    started = [row for row in rows if row.status == "started"]
    already = [row for row in rows if row.status == "already_running"]
    failed = [row for row in rows if row.status == "failed"]
    skipped = [row for row in rows if row.status == "skipped_current"]

    print(heading)
    for row in started:
        suffix = f" (PID {row.pid})" if row.pid else ""
        print(f"  started {row.profile}{suffix}")
    for row in already:
        print(f"  already running {row.profile}")
    for row in skipped:
        print(f"  skipped current profile {row.profile}")
    for row in failed:
        detail = f": {row.error}" if row.error else ""
        print(f"  failed {row.profile}{detail}")
