"""Regression tests for install.sh Python environment sanitization.

When install.sh is launched from another Python-driven tool session, inherited
PYTHONPATH/PYTHONHOME can shadow the freshly installed checkout. The installer
must sanitize those vars both during installation and at runtime launch.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"


def _install_sh_text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


def test_install_script_unsets_pythonpath_and_pythonhome_early() -> None:
    text = _install_sh_text()

    # During install, inherited Python env must be sanitized before pip/venv use.
    assert 'unset PYTHONPATH' in text
    assert 'unset PYTHONHOME' in text


def test_hermes_launcher_wrapper_clears_python_env_before_exec() -> None:
    text = _install_sh_text()

    # Wrapper should clear env and forward args untouched to the venv entrypoint.
    assert 'cat > "$command_link_path" <<EOF' in text
    assert 'unset PYTHONPATH' in text
    assert 'unset PYTHONHOME' in text
    assert 'exec "$HERMES_BIN" "\\$@"' in text


def test_hermes_launcher_replaces_broken_symlink_before_write() -> None:
    text = _install_sh_text()
    setup_path_body = text.split("setup_path() {", 1)[1].split("\n}", 1)[0]

    # A deleted ~/.hermes can leave ~/.local/bin/hermes as a broken symlink.
    # Redirection follows symlinks, so remove the old path before writing.
    assert '[ -e "$command_link_path" ] || [ -L "$command_link_path" ]' in setup_path_body
    assert 'rm -f "$command_link_path"' in setup_path_body
    assert setup_path_body.index('rm -f "$command_link_path"') < setup_path_body.index(
        'cat > "$command_link_path" <<EOF'
    )
