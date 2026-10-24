"""Command-Line Interface (CLI) for mc-xbox-dl."""

import argparse
import os
import platform
import sys
import tempfile
import time
from pathlib import Path
from typing import Sequence

from mc_xbox_dl import __version__
from mc_xbox_dl.auth import ensure_valid_session, login_flow
from mc_xbox_dl.config import DEFAULT_JAVA_TARGET_VERSION, DOWNLOAD_INTER_WORLD_DELAY
from mc_xbox_dl.errors import (
    AccessDeniedError,
    McXboxDlError,
    PackagingError,
    RateLimitError,
    UsageError,
    WorldNotFoundError,
)
from mc_xbox_dl.http import HttpClient
from mc_xbox_dl.i18n import set_language, t
from mc_xbox_dl.packer import (
    assemble_world,
    check_java_runtime,
    convert_bedrock_to_java,
    create_mcworld,
    ensure_chunker_jar,
    get_java_saves_dir,
    get_minecraft_worlds_dir,
    install_world_dir,
    is_minecraft_running,
    normalize_chunker_format,
    resolve_unique_filepath,
    sanitize_filename,
    validate_world_dir,
)
from mc_xbox_dl.session import delete_session, load_session
from mc_xbox_dl.storage.client import StorageClient
from mc_xbox_dl.storage.models import WorldInfo


def build_parser() -> argparse.ArgumentParser:
    """Constructs the argument parser using localized descriptions."""
    parser = argparse.ArgumentParser(
        prog="mc-xbox-dl",
        description=t("cli_prog_description"),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help=t("help_version"),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=t("help_debug"),
    )
    parser.add_argument(
        "--lang",
        choices=["en", "pt", "en-US", "pt-BR"],
        default=None,
        help=t("help_lang"),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title=t("cli_commands_title"),
        description=t("cli_commands_desc"),
    )

    # login
    login_parser = subparsers.add_parser(
        "login",
        help=t("help_login"),
    )
    login_parser.add_argument(
        "--accept-risk",
        action="store_true",
        help=t("help_accept_risk"),
    )

    # logout
    subparsers.add_parser(
        "logout",
        help=t("help_logout"),
    )

    # whoami
    subparsers.add_parser(
        "whoami",
        help=t("help_whoami"),
    )

    # list
    list_parser = subparsers.add_parser(
        "list",
        help=t("help_list"),
    )
    list_parser.add_argument(
        "--no-cache",
        action="store_true",
        help=t("help_no_cache"),
    )

    # download
    dl_parser = subparsers.add_parser(
        "download",
        help=t("help_download"),
    )
    dl_parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help=t("help_target"),
    )
    dl_parser.add_argument(
        "--all",
        action="store_true",
        help=t("help_all"),
    )
    dl_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=t("help_output"),
    )
    dl_parser.add_argument(
        "--install",
        action="store_true",
        help=t("help_install"),
    )
    dl_parser.add_argument(
        "--install-dir",
        "-install-dir",
        dest="install_dir",
        default=None,
        metavar="PATH",
        help=t("help_install_dir"),
    )
    dl_parser.add_argument(
        "--java",
        action="store_true",
        help=t("help_java"),
    )
    dl_parser.add_argument(
        "--java-version",
        dest="java_version",
        default="1.21.4",
        metavar="VERSION",
        help=t("help_java_version"),
    )
    dl_parser.add_argument(
        "--install-java",
        dest="install_java",
        action="store_true",
        help=t("help_install_java"),
    )
    dl_parser.add_argument(
        "--java-saves-dir",
        dest="java_saves_dir",
        default=None,
        metavar="PATH",
        help=t("help_java_saves_dir"),
    )
    dl_parser.add_argument(
        "--force",
        action="store_true",
        help=t("help_force"),
    )

    return parser


def handle_login(args: argparse.Namespace) -> int:
    """Executes the Device Code login flow and persists credentials."""
    # Consent gate: require explicit flag or interactive confirmation
    if not getattr(args, "accept_risk", False):
        try:
            from rich.console import Console

            Console().print(f"\n{t('login_consent_warning')}\n")
        except Exception:
            print(f"\n{t('login_consent_warning')}\n")

        try:
            resp = input(t("login_consent_prompt")).strip().lower()
            if resp not in ("y", "yes", "s", "sim"):
                print(t("login_consent_declined"), file=sys.stderr)
                return 1
        except (EOFError, KeyboardInterrupt):
            print(f"\n{t('login_consent_declined')}", file=sys.stderr)
            return 1

    with HttpClient(debug=args.debug) as client:
        session = login_flow(client)
        print(t("login_success"))
        gamertag = session.xbl.gamertag or t("unknown")
        xuid = session.xbl.xuid or t("unknown")
        print(t("whoami", gamertag=gamertag, xuid=xuid))
    return 0


def handle_whoami(args: argparse.Namespace) -> int:
    """Displays information for the currently active session."""
    session = load_session()
    if not session:
        print(t("not_authenticated"), file=sys.stderr)
        return 3

    gamertag = session.xbl.gamertag or t("unknown")
    xuid = session.xbl.xuid or t("unknown")
    print(t("whoami", gamertag=gamertag, xuid=xuid))
    return 0


def handle_logout(args: argparse.Namespace) -> int:
    """Deletes local session files."""
    if delete_session():
        print(t("logout_success"))
    else:
        print(t("logout_no_session"))
    return 0


def format_worlds_table(worlds: list[WorldInfo]) -> None:
    """Displays worlds in a formatted Rich table or plain text fallback."""
    title = t("table_title")
    col_idx = t("col_index")
    col_name = t("col_name")
    col_modified = t("col_modified")
    col_size = t("col_size")

    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(
            title=title,
            show_lines=False,
            header_style="bold cyan",
        )
        table.add_column(col_idx, justify="right", style="cyan", no_wrap=True)
        table.add_column(col_name, style="bold green")
        table.add_column(col_modified, justify="center", style="yellow")
        table.add_column(col_size, justify="right", style="magenta")

        for w in worlds:
            table.add_row(
                str(w.index),
                w.name,
                w.formatted_date(),
                w.formatted_size(),
            )
        Console().print(table)
    except Exception:
        # Fallback to plain aligned text
        print(f"\n{col_idx:>3}  {col_name:<35}  {col_modified:<16}  {col_size:>12}")
        print("-" * 72)
        for w in worlds:
            print(f"{w.index:>3}  {w.name:<35}  {w.formatted_date():<16}  {w.formatted_size():>12}")
        print()


def handle_list(args: argparse.Namespace) -> int:
    """Queries Xbox Cloud Connected Storage and lists all synchronized worlds."""
    with HttpClient(debug=args.debug) as client:
        session = ensure_valid_session(client)
        print(t("list_fetching"))
        storage = StorageClient(client, session)
        use_cache = not getattr(args, "no_cache", False)
        worlds = storage.list_worlds(use_cache=use_cache)

        if not worlds:
            raise WorldNotFoundError(t("list_empty"))

        format_worlds_table(worlds)
        return 0


def download_single_world(
    storage: StorageClient,
    world: WorldInfo,
    output_file: Path | None = None,
    force: bool = False,
    show_progress: bool = True,
    install: bool = False,
    install_dir: Path | None = None,
    java: bool = False,
    java_output_dir: Path | None = None,
    java_version: str = DEFAULT_JAVA_TARGET_VERSION,
    chunker_jar: Path | None = None,
    install_java: bool = False,
) -> tuple[Path | None, Path | None]:
    """
    Downloads atoms for a world, reconstructs its structure, validates integrity,
    and optionally installs directly into Minecraft Bedrock, converts to Java Edition,
    and/or exports as .mcworld.
    Returns (mcworld_path, installed_path).
    """
    manifest = storage.get_world_manifest(world.world_id)
    atom_paths = list(manifest.values())
    if not atom_paths:
        raise PackagingError(f"World manifest for '{world.name}' contains no atoms.")

    atoms_data: list[bytes] = []
    if show_progress:
        try:
            from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

            with Progress(
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total} files)"),
                TimeRemainingColumn(),
            ) as progress:
                task_id = progress.add_task(t("download_progress_files"), total=len(atom_paths))
                for atom_path in atom_paths:
                    atoms_data.append(storage.download_atom(atom_path))
                    progress.advance(task_id)
        except Exception:
            total = len(atom_paths)
            for idx, atom_path in enumerate(atom_paths, start=1):
                fallback_msg = t("download_progress_fallback", idx=idx, total=total)
                print(fallback_msg, end="", flush=True)
                atoms_data.append(storage.download_atom(atom_path))
            print()
    else:
        for atom_path in atom_paths:
            atoms_data.append(storage.download_atom(atom_path))

    installed_path: Path | None = None
    mcworld_path: Path | None = None

    with tempfile.TemporaryDirectory(prefix="mc_xbox_dl_") as temp_dir_str:
        temp_world_dir = Path(temp_dir_str)
        assemble_world(atoms_data, temp_world_dir)

        is_valid, error_msg = validate_world_dir(temp_world_dir)
        if not is_valid:
            raise PackagingError(f"World validation failed: {error_msg}")

        # Install directly into game worlds directory if requested
        if install and install_dir is not None:
            installed_path = install_world_dir(
                temp_world_dir,
                install_dir,
                world.name,
                world_id=world.world_id,
                force=force,
            )
            print(t("installed_directly", path=installed_path))

        # Convert to Minecraft Java Edition via Chunker CLI if requested
        if java and java_output_dir is not None:
            print(t("conversion_start", name=world.name, version=java_version))
            java_dest_path = convert_bedrock_to_java(
                bedrock_world_dir=temp_world_dir,
                output_java_dir=java_output_dir,
                target_format=java_version,
                chunker_jar=chunker_jar,
                force=force,
                http_client=getattr(storage, "client", None),
            )
            if install_java:
                print(t("installed_java_directly", path=java_dest_path))
            else:
                print(t("conversion_success", path=java_dest_path))
            if installed_path is None:
                installed_path = java_dest_path

        # Generate backup .mcworld package if output_file was requested
        if output_file is not None:
            mcworld_path = create_mcworld(temp_world_dir, output_file, force=force)

    return mcworld_path, installed_path


def print_batch_summary(
    total: int,
    successes: list[tuple[WorldInfo, Path | None]],
    skipped: list[tuple[WorldInfo, Path]],
    failures: list[tuple[WorldInfo, str]],
    output_dir: Path | None = None,
    install_dir: Path | None = None,
    java_dir: Path | None = None,
) -> None:
    """Displays a stylized or plain text summary after batch world download completes."""
    try:
        from rich.console import Console
        from rich.panel import Panel

        summary_lines = [
            f"[bold]{t('summary_total')}[/bold] {total}",
            f"[bold green]{t('summary_success')}[/bold green]     {len(successes)}",
            f"[bold yellow]{t('summary_skipped')}[/bold yellow]  {len(skipped)}",
            f"[bold red]{t('summary_failures')}[/bold red]                 {len(failures)}",
        ]
        if install_dir:
            summary_lines.append(
                f"[bold green]{t('summary_installed_loc')}[/bold green]    {install_dir}"
            )
        if java_dir:
            summary_lines.append(
                f"[bold green]{t('summary_java_loc')}[/bold green]         {java_dir}"
            )
        if output_dir:
            summary_lines.append(f"[bold cyan]{t('summary_mcworld_loc')}[/bold cyan] {output_dir}")

        if install_dir and is_minecraft_running():
            summary_lines.append(f"\n[bold yellow]{t('summary_running_notice')}[/bold yellow]")

        if failures:
            summary_lines.append(f"\n[bold red]{t('summary_failures_detail')}[/bold red]")
            for w, err in failures:
                summary_lines.append(f" - #{w.index} '{w.name}': {err}")

        Console().print(Panel("\n".join(summary_lines), title=t("summary_title"), expand=False))
    except Exception:
        print("\n" + "=" * 55)
        print(f"  {t('summary_title')}:")
        print(f"  {t('summary_total'):<26} {total}")
        print(f"  {t('summary_success'):<26} {len(successes)}")
        print(f"  {t('summary_skipped'):<26} {len(skipped)}")
        print(f"  {t('summary_failures'):<26} {len(failures)}")
        if install_dir:
            print(f"  {t('summary_installed_loc'):<26} {install_dir}")
        if java_dir:
            print(f"  {t('summary_java_loc'):<26} {java_dir}")
        if output_dir:
            print(f"  {t('summary_mcworld_loc'):<26} {output_dir}")
        if install_dir and is_minecraft_running():
            print(f"\n  {t('summary_running_notice')}")
        if failures:
            print(f"\n  {t('summary_failures_detail')}")
            for w, err in failures:
                print(f"   - #{w.index} '{w.name}': {err}")
        print("=" * 55 + "\n")


def print_linux_install_notice() -> None:
    """Displays a friendly Rich panel explaining Linux manual installation paths."""
    title = t("linux_install_notice_title")
    body = t("linux_install_notice_body")
    try:
        from rich.console import Console
        from rich.panel import Panel

        panel = Panel(
            body,
            title=f"[bold yellow]{title}[/bold yellow]",
            border_style="yellow",
            expand=False,
        )
        Console().print(panel)
    except Exception:
        print(f"\n[{title}]\n{body}\n")


def handle_download_all(
    storage: StorageClient,
    worlds: list[WorldInfo],
    output_dir: Path | None,
    force: bool,
    install: bool = False,
    install_dir: Path | None = None,
    java: bool = False,
    java_dir: Path | None = None,
    java_version: str = DEFAULT_JAVA_TARGET_VERSION,
    chunker_jar: Path | None = None,
    install_java: bool = False,
) -> int:
    """Downloads all cloud worlds in batch with fault tolerance and resume support."""
    total_worlds = len(worlds)
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
    if java and java_dir:
        java_dir.mkdir(parents=True, exist_ok=True)

    if install and install_dir is not None:
        if output_dir is not None:
            print(
                f"{t('download_all_start_install', total=total_worlds, dir=install_dir)}\n"
                f"{t('download_all_saving_copies', dir=output_dir)}"
            )
        else:
            print(t("download_all_start_install", total=total_worlds, dir=install_dir))
    elif java and java_dir is not None:
        print(t("download_all_start_java", total=total_worlds, dir=java_dir))
    else:
        print(t("download_all_start", total=total_worlds, dir=output_dir))

    successes: list[tuple[WorldInfo, Path | None]] = []
    skipped: list[tuple[WorldInfo, Path]] = []
    failures: list[tuple[WorldInfo, str]] = []

    written_paths: set[Path] = set()

    for idx, world in enumerate(worlds, start=1):
        safe_name = sanitize_filename(world.name)
        java_folder_name = safe_name if install_java else f"{safe_name} (Java)"
        target_java_path = (java_dir / java_folder_name) if (java and java_dir) else None

        # Resume/skip check if not force
        if not force:
            if install and install_dir is not None and (install_dir / safe_name).exists():
                if not java or (target_java_path is not None and target_java_path.exists()):
                    print(
                        t(
                            "download_all_skipped_install",
                            current=idx,
                            total=total_worlds,
                            index=world.index,
                            name=world.name,
                        )
                    )
                    skipped.append((world, install_dir / safe_name))
                    continue
            elif (
                not install and java and target_java_path is not None and target_java_path.exists()
            ):
                print(
                    t(
                        "download_all_skipped_java",
                        current=idx,
                        total=total_worlds,
                        index=world.index,
                        name=world.name,
                    )
                )
                skipped.append((world, target_java_path))
                continue
            elif output_dir is not None and (output_dir / f"{safe_name}.mcworld").exists():
                print(
                    t(
                        "download_all_skipped",
                        current=idx,
                        total=total_worlds,
                        index=world.index,
                        name=world.name,
                    )
                )
                skipped.append((world, output_dir / f"{safe_name}.mcworld"))
                continue

        target_mcworld_path: Path | None = None
        if output_dir is not None:
            target_mcworld_path = output_dir / f"{safe_name}.mcworld"
            if target_mcworld_path in written_paths or target_mcworld_path.exists():
                target_mcworld_path = resolve_unique_filepath(output_dir, safe_name)

        print(
            t(
                "download_all_current",
                current=idx,
                total=total_worlds,
                index=world.index,
                name=world.name,
            )
        )

        try:
            out_file, installed_out = download_single_world(
                storage,
                world,
                output_file=target_mcworld_path,
                force=True,
                show_progress=True,
                install=install,
                install_dir=install_dir,
                java=java,
                java_output_dir=target_java_path,
                java_version=java_version,
                chunker_jar=chunker_jar,
                install_java=install_java,
            )
            if out_file:
                written_paths.add(out_file)
            successes.append((world, out_file or installed_out))

            # Rate limiting / pacing between consecutive worlds
            if idx < total_worlds and DOWNLOAD_INTER_WORLD_DELAY > 0:
                time.sleep(DOWNLOAD_INTER_WORLD_DELAY)
        except (AccessDeniedError, RateLimitError) as fatal_exc:
            failures.append((world, str(fatal_exc)))
            print(
                t("download_all_error", index=world.index, name=world.name, error=fatal_exc),
                file=sys.stderr,
            )
            if isinstance(fatal_exc, RateLimitError):
                print(f"\n{t('err_rate_limited')}", file=sys.stderr)
            else:
                print(f"\n{t('err_fail_fast_auth', code='401/403')}", file=sys.stderr)
            # Fail-fast abort: break immediately without attempting more worlds
            break
        except Exception as exc:
            failures.append((world, str(exc)))
            print(
                t("download_all_error", index=world.index, name=world.name, error=exc),
                file=sys.stderr,
            )

    print_batch_summary(
        total_worlds,
        successes,
        skipped,
        failures,
        output_dir=output_dir,
        install_dir=install_dir,
        java_dir=java_dir if java else None,
    )
    return 0 if not failures else 1


def handle_download(args: argparse.Namespace) -> int:
    """Dispatches download requests for single worlds or entire collections."""
    if not args.all and not args.target:
        raise UsageError(t("target_or_all_required"))

    with HttpClient(debug=args.debug) as client:
        session = ensure_valid_session(client)
        storage = StorageClient(client, session)

        worlds = storage.list_worlds()
        if not worlds:
            raise WorldNotFoundError(t("list_empty"))

        if getattr(args, "install_dir", None):
            args.install = True

        if getattr(args, "java_saves_dir", None):
            args.install_java = True
            args.java = True
        elif getattr(args, "install_java", False):
            args.java = True

        # Linux compatibility: direct automatic installation is supported on Windows only
        if (
            platform.system() == "Linux"
            and args.install
            and not getattr(args, "install_dir", None)
            and not os.getenv("MC_WORLDS_DIR")
        ):
            print_linux_install_notice()
            args.install = False

        install_dir = (
            get_minecraft_worlds_dir(
                install_dir=args.install_dir,
                interactive=sys.stdin.isatty(),
            )
            if args.install
            else None
        )

        java_enabled: bool = bool(getattr(args, "java", False))
        install_java: bool = bool(getattr(args, "install_java", False))
        java_version = normalize_chunker_format(
            getattr(args, "java_version", None) or DEFAULT_JAVA_TARGET_VERSION
        )
        chunker_jar: Path | None = None
        java_dir: Path | None = None

        if java_enabled:
            check_java_runtime()
            chunker_jar = ensure_chunker_jar(client)
            if install_java:
                java_dir = get_java_saves_dir(custom_dir=getattr(args, "java_saves_dir", None))
                output_dir = Path(args.output).resolve() if args.output else None
            else:
                java_dir = Path(args.output).resolve() if args.output else Path(".").resolve()
                output_dir = None
        else:
            output_dir = (
                Path(args.output).resolve()
                if args.output
                else (None if args.install else Path(".").resolve())
            )

        if args.all:
            return handle_download_all(
                storage,
                worlds,
                output_dir,
                force=args.force,
                install=args.install,
                install_dir=install_dir,
                java=java_enabled,
                java_dir=java_dir,
                java_version=java_version,
                chunker_jar=chunker_jar,
                install_java=install_java,
            )

        # Single world download by index or name/id
        target = args.target.strip()
        selected_world: WorldInfo | None = None
        if target.isdigit():
            idx = int(target)
            for w in worlds:
                if w.index == idx:
                    selected_world = w
                    break
        else:
            for w in worlds:
                if w.world_id == target or w.name.lower() == target.lower():
                    selected_world = w
                    break

        if not selected_world:
            raise WorldNotFoundError(t("world_not_found", target=target))

        safe_name = sanitize_filename(selected_world.name)
        output_file = (output_dir / f"{safe_name}.mcworld") if output_dir else None

        if output_file and output_file.exists() and not args.force:
            raise UsageError(t("file_exists", path=output_file))

        java_output_dir: Path | None = None
        if java_enabled and java_dir is not None:
            java_folder_name = safe_name if install_java else f"{safe_name} (Java)"
            java_output_dir = java_dir / java_folder_name

        print(t("download_start", index=selected_world.index, name=selected_world.name))

        out_file, installed_dir = download_single_world(
            storage,
            selected_world,
            output_file=output_file,
            force=args.force,
            show_progress=True,
            install=args.install,
            install_dir=install_dir,
            java=java_enabled,
            java_output_dir=java_output_dir,
            java_version=java_version,
            chunker_jar=chunker_jar,
            install_java=install_java,
        )

        size_display = selected_world.formatted_size()
        if out_file and out_file.exists():
            actual_size = out_file.stat().st_size
            size_display = (
                f"{actual_size / (1024 * 1024):.1f} MB"
                if actual_size >= 1024 * 1024
                else f"{actual_size / 1024:.1f} KB"
            )
            print(t("download_success", path=out_file, size=size_display))
        elif installed_dir:
            print(t("installed_ready", index=selected_world.index, name=selected_world.name))

        if installed_dir and is_minecraft_running():
            print(f"\n{t('minecraft_running_warning')}")
        return 0


def extract_lang_arg(args: list[str]) -> tuple[str | None, list[str]]:
    """
    Extracts --lang or --lang=VALUE from argument list regardless of its position,
    returning the extracted language and the cleaned argument list.
    """
    lang = None
    cleaned = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--lang":
            if i + 1 < len(args):
                lang = args[i + 1]
                i += 2
                continue
        elif arg.startswith("--lang="):
            lang = arg.split("=", 1)[1]
            i += 1
            continue
        cleaned.append(arg)
        i += 1
    return lang, cleaned


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point."""
    raw_args = list(argv if argv is not None else sys.argv[1:])

    # 1. Extract --lang and configure active language
    lang_arg, cleaned_args = extract_lang_arg(raw_args)
    set_language(lang_arg, persist=(lang_arg is not None))

    parser = build_parser()

    # Empty arguments check: print help and exit with code 2
    if not cleaned_args:
        parser.print_help()
        return 2

    try:
        args = parser.parse_args(cleaned_args)
        args.lang = lang_arg

        if not args.command:
            parser.print_help()
            return 2

        if args.command == "login":
            return handle_login(args)
        elif args.command == "whoami":
            return handle_whoami(args)
        elif args.command == "logout":
            return handle_logout(args)
        elif args.command == "list":
            return handle_list(args)
        elif args.command == "download":
            return handle_download(args)
        else:
            parser.print_help()
            return 2

    except UsageError as exc:
        print(t("err_prefix", msg=exc), file=sys.stderr)
        return exc.exit_code
    except McXboxDlError as exc:
        print(t("err_prefix", msg=exc), file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print(t("err_cancelled"), file=sys.stderr)
        return 1
    except Exception as exc:
        print(t("err_unexpected", msg=exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
