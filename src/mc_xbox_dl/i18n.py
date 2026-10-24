"""Internationalization (i18n) and localized message catalog for mc-xbox-dl."""

import json
import locale
import os
import tempfile
import warnings
from pathlib import Path
from typing import Any

from mc_xbox_dl import config

SUPPORTED_LANGUAGES = {"en", "pt"}
DEFAULT_LANGUAGE = "en"

_CURRENT_LANGUAGE = DEFAULT_LANGUAGE

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # CLI Parser & Arguments
        "cli_prog_description": (
            "CLI tool to list and download Minecraft Bedrock (Xbox) worlds saved in the cloud."
        ),
        "cli_commands_title": "commands",
        "cli_commands_desc": "Available commands:",
        "help_version": "Show program version.",
        "help_debug": "Enable debug mode, saving redacted requests and responses to disk.",
        "help_lang": "Select interface language (en or pt).",
        "help_login": "Authenticate to Microsoft/Xbox account via Device Code and save session.",
        "help_logout": "Remove local session and disconnect.",
        "help_whoami": "Display Gamertag and XUID of currently connected user.",
        "help_list": "List Minecraft Bedrock worlds saved in Xbox cloud.",
        "help_download": "Download worlds from cloud and generate corresponding .mcworld files.",
        "help_target": "World index in listing or stable identifier (omit if using --all).",
        "help_all": "Download all available cloud worlds in batch.",
        "help_output": (
            "Directory to save .mcworld files (default: current folder, or none with --install)."
        ),
        "help_install": "Install worlds directly into the PC Minecraft Bedrock worlds folder.",
        "help_install_dir": "Path to 'minecraftWorlds' directory (overrides auto-detection).",
        "help_java": (
            "Convert the downloaded world to Minecraft Java Edition format via Chunker CLI."
        ),
        "help_java_version": "Target Minecraft Java version for conversion (default: 1.21.4).",
        "help_install_java": (
            "Install converted Java world directly into local '.minecraft/saves' folder."
        ),
        "help_java_saves_dir": (
            "Path to Minecraft Java 'saves' directory (overrides auto-detection)."
        ),
        "help_force": "Overwrite existing files without asking for confirmation.",
        "help_accept_risk": (
            "Acknowledge and accept that this tool uses unofficial API flows at your own risk."
        ),
        "help_no_cache": "Bypass local world listing cache and query Xbox cloud directly.",
        # Authentication / Session
        "login_consent_warning": (
            "[bold yellow]LEGAL AND ACCOUNT NOTICE:[/bold yellow]\n"
            "This tool is an unofficial open-source utility for personal world backups.\n"
            "It authenticates using Minecraft client identifiers to communicate with Xbox Live.\n"
            "Use of unofficial API endpoints carries inherent risk, including potential account\n"
            "restrictions or suspension under Microsoft Services Agreement terms.\n"
            "This software is provided 'as is' without warranty. You use it at your own risk."
        ),
        "login_consent_prompt": "Do you accept this risk and wish to proceed? (y/N): ",
        "login_consent_declined": "Authentication cancelled. Risk terms were not accepted.",
        "login_start": "Starting authentication via Device Code...",
        "login_prompt": "\nTo authenticate, visit: {url}\nEnter code: {code}\n",
        "login_waiting": "Waiting for login approval in the browser...",
        "login_success": "Login successful! Session saved locally.",
        "logout_success": "Session ended successfully.",
        "logout_no_session": "No active session found.",
        "whoami": "Logged in as: {gamertag} (XUID: {xuid})",
        "not_authenticated": "You are not authenticated. Run 'mc-xbox-dl login' to authenticate.",
        "session_expired": (
            "Your session has expired and could not be renewed. "
            "Please run 'mc-xbox-dl login' again."
        ),
        "unknown": "Unknown",
        # World Listing & Table
        "list_fetching": "Fetching worlds saved in the Xbox cloud...",
        "list_empty": (
            "No worlds found in the cloud. Only worlds synced from console or PC appear here."
        ),
        "table_title": "Worlds saved in Xbox cloud (Minecraft Bedrock)",
        "col_index": "#",
        "col_name": "Name",
        "col_modified": "Modified at",
        "col_size": "Size",
        # Download & Packaging
        "target_or_all_required": (
            "Specify the world index/identifier to download or use the '--all' option."
        ),
        "world_not_found": (
            "World '{target}' not found in the listing. Run 'mc-xbox-dl list' to see valid indices."
        ),
        "download_start": "Starting download of world #{index}: '{name}'...",
        "download_progress_files": "Downloading files...",
        "download_progress_fallback": "\rDownloading file {idx}/{total}...",
        "download_success": "World saved successfully at: {path} ({size})",
        "download_cancelled": "Download cancelled by user. Temporary files removed.",
        "file_exists": (
            "File '{path}' already exists. Use --force to overwrite without confirmation."
        ),
        "installed_directly": "World installed directly into Minecraft Bedrock: {path}",
        "installed_java_directly": "Java world installed into Minecraft Java saves: {path}",
        "installed_ready": "Done: world #{index} '{name}' is ready in Minecraft!",
        "minecraft_running_warning": (
            "Warning: Minecraft Bedrock is currently running.\n"
            "Installed worlds will only appear in your world list after closing and "
            "reopening Minecraft!"
        ),
        "debug_saved": "Redacted diagnostic information saved at: {path}",
        # Chunker / Java Conversion
        "chunker_downloading": "Downloading Chunker CLI ({name}) from GitHub Releases...",
        "chunker_download_progress": "Downloading chunker-cli.jar...",
        "chunker_download_fallback": "\rDownloading chunker-cli.jar ({downloaded}/{total} KB)...",
        "chunker_downloaded": "Chunker CLI saved at: {path}",
        "conversion_start": (
            "Converting world '{name}' to Minecraft Java ({version}) via Chunker CLI..."
        ),
        "conversion_success": "Java world converted and saved at: {path}",
        "err_java_not_found": (
            "Java 17+ was not found in your system PATH. "
            "Install OpenJDK 17 or newer (https://adoptium.net) to use --java conversion."
        ),
        "err_java_version_too_low": (
            "Detected Java {version}, but Chunker CLI requires Java 17 or newer. "
            "Please upgrade your Java runtime."
        ),
        "err_chunker_failed": "Chunker CLI conversion failed: {details}",
        "err_java_saves_not_found": (
            "Could not locate a local '.minecraft' directory for Java Edition. "
            "Launch Minecraft Java at least once or specify --java-saves-dir <PATH>."
        ),
        # Batch Download
        "download_all_start": "Starting batch download of {total} worlds to: {dir}",
        "download_all_start_install": (
            "Starting batch download of {total} worlds to Minecraft Bedrock ({dir})"
        ),
        "download_all_start_java": (
            "Starting batch download and Java conversion of {total} worlds to: {dir}"
        ),
        "download_all_saving_copies": "Saving .mcworld copies to: {dir}",
        "download_all_skipped": (
            "[{current}/{total}] World #{index} '{name}' already exists on disk. Skipping..."
        ),
        "download_all_skipped_install": (
            "[{current}/{total}] World #{index} '{name}' is already installed in Minecraft. "
            "Skipping..."
        ),
        "download_all_skipped_java": (
            "[{current}/{total}] Java world #{index} '{name}' already exists. Skipping..."
        ),
        "download_all_current": "\n[{current}/{total}] Downloading world #{index}: '{name}'...",
        "download_all_error": "Error downloading world #{index} '{name}': {error}",
        # Batch Summary Panel
        "summary_title": "Batch Download Summary",
        "summary_total": "Total worlds analyzed:",
        "summary_success": "✓ Successfully downloaded:",
        "summary_skipped": "↷ Already existing (skipped):",
        "summary_failures": "✗ Failures:",
        "summary_installed_loc": "Installed in Minecraft:",
        "summary_java_loc": "Java Edition worlds:",
        "summary_mcworld_loc": "Location of .mcworld files:",
        "summary_running_notice": (
            "Notice: Minecraft Bedrock is currently running.\n"
            "Close and restart Minecraft to refresh your world list!"
        ),
        "summary_failures_detail": "Failure details:",
        # Errors & CLI Output
        "err_prefix": "Error: {msg}",
        "err_unexpected": "Unexpected error: {msg}",
        "err_cancelled": "\nOperation cancelled by user.",
        "err_fail_fast_auth": (
            "Access denied by Xbox Live (HTTP {code}). "
            "Halting batch operations immediately to protect account."
        ),
        "err_rate_limited": (
            "Xbox Live rate limit encountered (HTTP 429). "
            "Halting batch operations immediately to prevent account throttling."
        ),
        # Profiles / Locator
        "multiple_profiles_found": "Multiple Minecraft Bedrock user profiles detected:",
        "multiple_profiles_choice": "Select target profile [1-{max_choice}] (default: 1):",
        "multiple_profiles_auto": (
            "Multiple profiles found. Automatically selected most recent: {path}"
        ),
        "col_profile_type": "Type",
        "col_profile_user": "User / Package",
        "col_profile_path": "Path",
        "err_minecraft_not_found": (
            "Could not locate a valid Minecraft Bedrock installation on this PC (scanned GDK "
            "and UWP paths). Use --install-dir to specify it manually."
        ),
        "err_not_windows_install": (
            "Direct world installation (--install) is only supported on Windows operating systems."
        ),
        "linux_install_notice_title": "Direct Installation Unavailable on Linux",
        "linux_install_notice_body": (
            "[bold]Automatic world installation (--install) is only supported on Windows "
            "(Minecraft Bedrock for Windows).[/bold]\n"
            "The [cyan].mcworld[/cyan] package will be saved to your output directory instead.\n\n"
            "If you use a Bedrock launcher on Linux (e.g., [bold]mcpelauncher[/bold]), worlds "
            "are typically located at:\n"
            "  • [green]Flatpak:[/green] "
            "~/.var/app/io.mrarm.mcpelauncher/data/mcpelauncher/games/com.mojang/"
            "minecraftWorlds/\n"
            "  • [green]Native:[/green]  "
            "~/.local/share/mcpelauncher/games/com.mojang/minecraftWorlds/\n\n"
            "You can extract the [cyan].mcworld[/cyan] package or specify "
            "[bold]--install-dir <PATH>[/bold] to target your launcher's world folder."
        ),
        # XSTS Error Messages
        "xerr_2148916233": (
            "This Microsoft account does not have an Xbox Live profile. "
            "Visit https://xbox.com to create one."
        ),
        "xerr_2148916235": "This account is suspended or banned from Xbox Live.",
        "xerr_2148916236": "This account requires age verification or proof of majority.",
        "xerr_2148916237": "This account has reached its family screen time limit.",
        "xerr_2148916238": (
            "Child account must be added to a Microsoft family by a parent or guardian."
        ),
    },
    "pt": {
        # CLI Parser & Arguments
        "cli_prog_description": (
            "CLI para listar e baixar mundos de Minecraft Bedrock (Xbox) salvos na nuvem."
        ),
        "cli_commands_title": "comandos",
        "cli_commands_desc": "Comandos disponíveis:",
        "help_version": "Exibe a versão do programa.",
        "help_debug": (
            "Ativa o modo de depuração gravando requisições e respostas redigidas em disco."
        ),
        "help_lang": "Seleciona o idioma da interface (pt ou en).",
        "help_login": "Autentica na conta Microsoft/Xbox via Device Code e salva a sessão.",
        "help_logout": "Remove a sessão local e encerra a conexão.",
        "help_whoami": "Exibe a Gamertag e XUID do usuário atualmente conectado.",
        "help_list": "Lista os mundos de Minecraft Bedrock salvos na nuvem do Xbox.",
        "help_download": "Baixa mundos da nuvem e gera os arquivos .mcworld correspondentes.",
        "help_target": (
            "Índice do mundo na listagem ou identificador estável (omitir se usar --all)."
        ),
        "help_all": "Baixa todos os mundos disponíveis na nuvem em lote.",
        "help_output": (
            "Diretório para salvar arquivos .mcworld (padrão: pasta atual, "
            "ou nenhum com --install)."
        ),
        "help_install": "Instala os mundos diretamente na pasta do Minecraft Bedrock no PC.",
        "help_install_dir": (
            "Caminho da pasta 'minecraftWorlds' (sobrescreve a detecção automática)."
        ),
        "help_java": (
            "Converte o mundo baixado para o formato Minecraft Java Edition via Chunker CLI."
        ),
        "help_java_version": "Versão alvo do Minecraft Java para a conversão (padrão: 1.21.4).",
        "help_install_java": (
            "Instala o mundo Java convertido diretamente na pasta '.minecraft/saves' local."
        ),
        "help_java_saves_dir": (
            "Caminho da pasta 'saves' do Minecraft Java (sobrescreve a detecção automática)."
        ),
        "help_force": "Sobrescreve arquivos existentes sem solicitar confirmação.",
        "help_accept_risk": (
            "Declara ciência e aceita que esta ferramenta utiliza fluxos não oficiais "
            "por sua própria conta e risco."
        ),
        "help_no_cache": (
            "Ignora o cache local de listagem de mundos e consulta a nuvem do Xbox diretamente."
        ),
        # Authentication / Session
        "login_consent_warning": (
            "[bold yellow]AVISO LEGAL E DE SEGURANÇA DA CONTA:[/bold yellow]\n"
            "Esta é uma ferramenta não oficial de código aberto para backup pessoal de mundos.\n"
            "Ela se autentica utilizando identificadores de cliente do Minecraft para acessar "
            "a Xbox Live.\n"
            "O uso de APIs não documentadas envolve riscos contratuais, incluindo possíveis\n"
            "restrições ou suspensão da conta Microsoft/Xbox nos termos do Contrato de Serviços "
            "da Microsoft.\n"
            "O software é fornecido 'no estado em que se encontra', sem garantias. "
            "O uso é por sua conta e risco."
        ),
        "login_consent_prompt": "Você aceita esses riscos e deseja prosseguir com o login? (s/N): ",
        "login_consent_declined": "Autenticação cancelada. Os termos de risco não foram aceitos.",
        "login_start": "Iniciando autenticação via Device Code...",
        "login_prompt": "\nPara autenticar, acesse: {url}\nDigite o código: {code}\n",
        "login_waiting": "Aguardando aprovação do login no navegador...",
        "login_success": "Login realizado com sucesso! Sessão salva localmente.",
        "logout_success": "Sessão encerrada com sucesso.",
        "logout_no_session": "Nenhuma sessão ativa encontrada.",
        "whoami": "Conectado como: {gamertag} (XUID: {xuid})",
        "not_authenticated": (
            "Você não está autenticado. Execute 'mc-xbox-dl login' para conectar sua conta."
        ),
        "session_expired": (
            "Sua sessão expirou e não pôde ser renovada. "
            "Por favor, execute 'mc-xbox-dl login' novamente."
        ),
        "unknown": "Desconhecido",
        # World Listing & Table
        "list_fetching": "Consultando mundos salvos na nuvem do Xbox...",
        "list_empty": (
            "Nenhum mundo encontrado na nuvem. Apenas mundos sincronizados no console ou "
            "PC aparecem aqui."
        ),
        "table_title": "Mundos salvos na nuvem do Xbox (Minecraft Bedrock)",
        "col_index": "#",
        "col_name": "Nome",
        "col_modified": "Modificado em",
        "col_size": "Tamanho",
        # Download & Packaging
        "target_or_all_required": (
            "Especifique o índice/identificador do mundo a baixar ou use a opção '--all'."
        ),
        "world_not_found": (
            "Mundo '{target}' não encontrado na listagem. Use 'mc-xbox-dl list' para ver "
            "os índices válidos."
        ),
        "download_start": "Iniciando download do mundo #{index}: '{name}'...",
        "download_progress_files": "Baixando arquivos...",
        "download_progress_fallback": "\rBaixando arquivo {idx}/{total}...",
        "download_success": "Mundo salvo com sucesso em: {path} ({size})",
        "download_cancelled": "Download cancelado pelo usuário. Arquivos temporários removidos.",
        "file_exists": (
            "O arquivo '{path}' já existe. Use --force para sobrescrever sem confirmação."
        ),
        "installed_directly": "Mundo instalado diretamente no Minecraft Bedrock: {path}",
        "installed_java_directly": "Mundo Java instalado em '.minecraft/saves': {path}",
        "installed_ready": "Concluído: mundo #{index} '{name}' pronto no Minecraft!",
        "minecraft_running_warning": (
            "Aviso: O Minecraft Bedrock está aberto em execução no momento.\n"
            "Os mundos instalados só aparecerão na sua lista de jogos após fechar e "
            "reabrir o Minecraft!"
        ),
        "debug_saved": "Informações de diagnóstico redigidas salvas em: {path}",
        # Chunker / Java Conversion
        "chunker_downloading": "Baixando o Chunker CLI ({name}) do GitHub Releases...",
        "chunker_download_progress": "Baixando chunker-cli.jar...",
        "chunker_download_fallback": "\rBaixando chunker-cli.jar ({downloaded}/{total} KB)...",
        "chunker_downloaded": "Chunker CLI salvo em: {path}",
        "conversion_start": (
            "Convertendo mundo '{name}' para Minecraft Java ({version}) via Chunker CLI..."
        ),
        "conversion_success": "Mundo Java convertido e salvo em: {path}",
        "err_java_not_found": (
            "O Java 17+ não foi encontrado no PATH do sistema. "
            "Instale o OpenJDK 17 ou superior (https://adoptium.net) para usar --java."
        ),
        "err_java_version_too_low": (
            "Java {version} detectado, mas o Chunker CLI exige Java 17 ou superior. "
            "Atualize sua instalação do Java."
        ),
        "err_chunker_failed": "Falha na conversão pelo Chunker CLI: {details}",
        "err_java_saves_not_found": (
            "Não foi possível localizar a pasta '.minecraft' do Minecraft Java Edition. "
            "Abra o Minecraft Java ao menos uma vez ou informe --java-saves-dir <CAMINHO>."
        ),
        # Batch Download
        "download_all_start": "Iniciando download em lote de {total} mundos para: {dir}",
        "download_all_start_install": (
            "Iniciando download em lote de {total} mundos para o Minecraft Bedrock ({dir})"
        ),
        "download_all_start_java": (
            "Iniciando download em lote e conversão Java de {total} mundos para: {dir}"
        ),
        "download_all_saving_copies": "Salvando cópias .mcworld em: {dir}",
        "download_all_skipped": (
            "[{current}/{total}] Mundo #{index} '{name}' já existe em disco. Pulando..."
        ),
        "download_all_skipped_install": (
            "[{current}/{total}] Mundo #{index} '{name}' já está instalado no Minecraft. Pulando..."
        ),
        "download_all_skipped_java": (
            "[{current}/{total}] Mundo Java #{index} '{name}' já existe. Pulando..."
        ),
        "download_all_current": "\n[{current}/{total}] Baixando mundo #{index}: '{name}'...",
        "download_all_error": "Erro ao baixar mundo #{index} '{name}': {error}",
        # Batch Summary Panel
        "summary_title": "Resumo do Download em Lote",
        "summary_total": "Total de mundos analisados:",
        "summary_success": "✓ Baixados com sucesso:",
        "summary_skipped": "↷ Já existentes (pulados):",
        "summary_failures": "✗ Falhas:",
        "summary_installed_loc": "Instalados no Minecraft:",
        "summary_java_loc": "Mundos Java Edition:",
        "summary_mcworld_loc": "Local dos arquivos .mcworld:",
        "summary_running_notice": (
            "Aviso: O Minecraft Bedrock está aberto em execução.\n"
            "Feche e abra o Minecraft novamente para atualizar a lista de mundos!"
        ),
        "summary_failures_detail": "Detalhe das falhas:",
        # Errors & CLI Output
        "err_prefix": "Erro: {msg}",
        "err_unexpected": "Erro inesperado: {msg}",
        "err_cancelled": "\nOperação cancelada pelo usuário.",
        "err_fail_fast_auth": (
            "Acesso negado pela Xbox Live (HTTP {code}). "
            "Interrompendo lote imediatamente para proteger a integridade da conta."
        ),
        "err_rate_limited": (
            "Limite de requisições da Xbox Live atingido (HTTP 429). "
            "Interrompendo lote imediatamente para evitar bloqueios ou sanções."
        ),
        # Profiles / Locator
        "multiple_profiles_found": "Múltiplos perfis de usuário do Minecraft Bedrock detectados:",
        "multiple_profiles_choice": "Selecione o perfil de destino [1-{max_choice}] (padrão: 1):",
        "multiple_profiles_auto": (
            "Múltiplos perfis encontrados. Selecionado automaticamente o mais recente: {path}"
        ),
        "col_profile_type": "Tipo",
        "col_profile_user": "Usuário / Pacote",
        "col_profile_path": "Caminho",
        "err_minecraft_not_found": (
            "Não foi possível localizar uma instalação válida do Minecraft Bedrock neste PC "
            "(caminhos GDK e UWP escaneados). Use --install-dir para especificar manualmente."
        ),
        "err_not_windows_install": (
            "A instalação direta de mundos (--install) é suportada apenas no sistema Windows."
        ),
        "linux_install_notice_title": "Instalação Direta Indisponível no Linux",
        "linux_install_notice_body": (
            "[bold]A auto-instalação de mundos (--install) está disponível apenas no Windows "
            "(Minecraft Bedrock para Windows).[/bold]\n"
            "O pacote [cyan].mcworld[/cyan] será salvo normalmente no diretório de saída.\n\n"
            "Caso utilize um launcher de Bedrock no Linux (como o [bold]mcpelauncher[/bold]), "
            "os mundos costumam ficar em:\n"
            "  • [green]Flatpak:[/green] "
            "~/.var/app/io.mrarm.mcpelauncher/data/mcpelauncher/games/com.mojang/"
            "minecraftWorlds/\n"
            "  • [green]Nativo:[/green]  "
            "~/.local/share/mcpelauncher/games/com.mojang/minecraftWorlds/\n\n"
            "Você pode extrair o arquivo [cyan].mcworld[/cyan] ou usar "
            "[bold]--install-dir <CAMINHO>[/bold] para apontar diretamente para a pasta."
        ),
        # XSTS Error Messages
        "xerr_2148916233": (
            "Esta conta Microsoft não possui um perfil Xbox Live. Acesse https://xbox.com "
            "para criá-lo."
        ),
        "xerr_2148916235": "Esta conta está suspensa ou banida da Xbox Live.",
        "xerr_2148916236": "Esta conta requer prova de maioridade ou verificação de conta.",
        "xerr_2148916237": "Esta conta atingiu o limite de tempo de uso familiar.",
        "xerr_2148916238": (
            "Conta de menor de idade precisa ser adicionada a uma família Microsoft por "
            "um responsável."
        ),
    },
}


def normalize_language_code(lang_code: str | None) -> str:
    """Normalizes input language code to 'pt' or 'en' (default fallback: 'en')."""
    if not lang_code:
        return DEFAULT_LANGUAGE
    code = lang_code.strip().lower().replace("_", "-")
    if code.startswith("pt"):
        return "pt"
    return "en"


def detect_system_language() -> str:
    """
    Detects the operating system language using environment variables and Python's locale module.
    Defaults to 'en' unless Portuguese is identified.
    """
    for env_var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.getenv(env_var)
        if val:
            return normalize_language_code(val)

    try:
        loc = locale.getlocale()[0]
        if loc:
            return normalize_language_code(loc)
    except Exception:
        pass

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            def_loc = locale.getdefaultlocale()[0]
        if def_loc:
            return normalize_language_code(def_loc)
    except Exception:
        pass

    return DEFAULT_LANGUAGE


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """
    Loads persistent user settings from disk.
    Returns an empty dictionary if the file does not exist or cannot be parsed.
    """
    target = path or config.get_settings_file()
    if not target.exists():
        return {}
    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_settings(settings: dict[str, Any], path: Path | None = None) -> None:
    """
    Atomically writes user settings to disk (temporary file + os.replace).
    """
    target = path or config.get_settings_file()
    target_dir = target.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_dir,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            json.dump(settings, tmp_file, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp_file.name)
        os.replace(tmp_path, target)
    except Exception:
        # Avoid crashing application if settings cannot be written
        pass


def get_saved_language(path: Path | None = None) -> str | None:
    """Returns the saved preferred language code from settings, or None if not set."""
    settings = load_settings(path)
    lang = settings.get("language")
    if lang and isinstance(lang, str):
        return normalize_language_code(lang)
    return None


def save_language_preference(lang_code: str, path: Path | None = None) -> None:
    """Saves the user's preferred language to disk."""
    settings = load_settings(path)
    settings["language"] = normalize_language_code(lang_code)
    save_settings(settings, path)


def set_language(
    lang_code: str | None = None,
    persist: bool = False,
    settings_file: Path | None = None,
) -> str:
    """
    Sets the active application language.
    - If lang_code is provided: normalizes and sets it. If persist=True, saves it to disk.
    - If lang_code is None: checks for a saved preference on disk.
      If no saved preference exists, detects from the operating system.
      Falls back to 'en'.
    Returns the normalized language code ('en' or 'pt').
    """
    global _CURRENT_LANGUAGE
    if lang_code is not None:
        normalized = normalize_language_code(lang_code)
        _CURRENT_LANGUAGE = normalized
        if persist:
            save_language_preference(normalized, path=settings_file)
    else:
        saved = get_saved_language(path=settings_file)
        if saved:
            _CURRENT_LANGUAGE = saved
        else:
            _CURRENT_LANGUAGE = detect_system_language()
    return _CURRENT_LANGUAGE


def get_language() -> str:
    """Returns the currently active language code ('en' or 'pt')."""
    return _CURRENT_LANGUAGE


def t(key: str, **kwargs: Any) -> str:
    """
    Translates a message key into the active language, formatting with kwargs if provided.
    Falls back to English if the key is missing in the active language.
    If the key is missing entirely, returns the key itself.
    """
    lang = get_language()
    lang_dict = MESSAGES.get(lang, MESSAGES[DEFAULT_LANGUAGE])
    msg = lang_dict.get(key)
    if msg is None:
        msg = MESSAGES[DEFAULT_LANGUAGE].get(key, key)
    if kwargs:
        try:
            return msg.format(**kwargs)
        except Exception:
            return msg
    return msg
