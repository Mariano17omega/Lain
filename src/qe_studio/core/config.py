"""Loading and validation of ``config.yaml`` (PRD §6).

The app has no settings window: everything operational comes from this file. Unknown keys
are rejected so typos surface as errors instead of silently falling back to defaults.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal, cast

import yaml
from matplotlib.colors import is_color_like
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

from .fontscale import MAX_SCALE, MIN_SCALE

ENV_CONFIG = "QE_STUDIO_CONFIG"
CONFIG_NAME = "config.yaml"


def _check_color(value: str) -> str:
    if not is_color_like(value):
        raise ValueError(f"cor inválida: {value!r}")
    return value


Color = Annotated[str, AfterValidator(_check_color)]
Orbital = Literal["s", "p", "d", "f"]
ExportFormat = Literal["png", "svg", "pdf"]

DEFAULT_EXCLUDES = [
    "tmp/",
    "*.save/",
    "*.amn",
    "*.mmn",
    "UNK*",
    "*.unk*",
    "*.wfc*",
    "*.mix*",
    "*.hub*",
    "*.igk*",
    "core",
    "core.[0-9]*",
]
DEFAULT_PUSH_EXCLUDES = ["plots/", "*.plot"]
DEFAULT_ORBITAL_COLORS: dict[str, str] = {
    "s": "#fbbf24",
    "p": "#06b6d4",
    "d": "#a855f7",
    "f": "#ec4899",
}


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PathsConfig(_Section):
    local_root: Path = Path("~/qe_simulations")
    remote_root: str = ""

    @field_validator("local_root")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return Path(os.path.expandvars(str(value))).expanduser()

    @field_validator("remote_root")
    @classmethod
    def _strip_slash(cls, value: str) -> str:
        value = value.strip()
        return value.rstrip("/") if value not in ("", "/") else value


class ClusterConfig(_Section):
    host: str = ""
    port: int = Field(default=22, ge=1, le=65535)
    user: str = ""
    auth: Literal["key", "password"] = "key"
    key_path: Path | None = None
    password_env: str | None = "QE_STUDIO_SSH_PASSWORD"
    password: SecretStr | None = None
    connect_timeout: int = Field(default=10, gt=0, le=300)
    status_poll_seconds: int = Field(default=300, ge=30)

    @field_validator("key_path")
    @classmethod
    def _expand(cls, value: Path | None) -> Path | None:
        return None if value is None else Path(os.path.expandvars(str(value))).expanduser()

    @property
    def configured(self) -> bool:
        return bool(self.host.strip() and self.user.strip())

    def resolve_password(self, environ: Mapping[str, str] | None = None) -> str | None:
        """Password from ``password_env`` (preferred) or the inline ``password``."""
        environ = os.environ if environ is None else environ
        if self.password_env and environ.get(self.password_env):
            return environ[self.password_env]
        return self.password.get_secret_value() if self.password else None


class SyncConfig(_Section):
    exclude: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    rsync_binary: str = "rsync"
    ssh_binary: str = "ssh"
    # Show the plan and wait for "Baixar" before transferring (spec 17 R2.5); false transfers
    # directly (automation, tests). Updates still ask file by file either way. A push always asks.
    confirm_plan: bool = True
    # Never sent to the cluster, on top of ``exclude`` (spec 27 R5): figures and plot settings.
    push_exclude: list[str] = Field(default_factory=lambda: list(DEFAULT_PUSH_EXCLUDES))


class ExportConfig(_Section):
    formats: list[ExportFormat] = Field(default_factory=lambda: ["png", "svg", "pdf"])
    dpi: int = Field(default=300, ge=72, le=2400)

    @field_validator("formats")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("informe ao menos um formato")
        return list(dict.fromkeys(value))


class BandColors(_Section):
    valence: Color = "#2563eb"
    conduction: Color = "#00d2ff"


class PlotConfig(_Section):
    energy_min: float = -5.0
    energy_max: float = 5.0
    shift_to_fermi: bool = True
    figure_size: tuple[float, float] = (6.0, 4.5)
    line_width: float = Field(default=1.2, gt=0, le=10)
    band_colors: BandColors = Field(default_factory=BandColors)
    fermi_color: Color = "#f43f5e"
    background: Color = "#ffffff"
    orbital_colors: dict[Orbital, Color] = Field(
        default_factory=lambda: cast(dict[Orbital, Color], dict(DEFAULT_ORBITAL_COLORS))
    )
    export: ExportConfig = Field(default_factory=ExportConfig)

    @field_validator("figure_size")
    @classmethod
    def _positive_size(cls, value: tuple[float, float]) -> tuple[float, float]:
        if min(value) <= 0 or max(value) > 50:
            raise ValueError("largura e altura devem estar entre 0 e 50 polegadas")
        return value

    @field_validator("orbital_colors")
    @classmethod
    def _fill_orbitals(cls, value: dict[str, str]) -> dict[str, str]:
        return {**DEFAULT_ORBITAL_COLORS, **value}

    @model_validator(mode="after")
    def _energy_window(self) -> PlotConfig:
        if self.energy_min >= self.energy_max:
            raise ValueError("energy_min deve ser menor que energy_max")
        return self


class UiConfig(_Section):
    theme: Literal["dark", "light", "system"] = "dark"  # system: follow the OS color scheme
    # Scales every font and the heights that hold text; paddings and icons stay (spec 19 R2).
    font_scale: float = Field(default=1.0, ge=MIN_SCALE, le=MAX_SCALE)
    hidden_dirs: list[str] = Field(default_factory=lambda: ["tmp", "*.save"])
    # F5 rereads every file, even those whose (mtime, size) did not change (spec 14 R4.2).
    paranoid_refresh: bool = False


DEFAULT_ENV_LINES = [
    "export I_MPI_SHM=bdw_avx2",
    ". /opt/intel/oneapi/mkl/latest/env/vars.sh",
    ". /opt/intel/oneapi/mpi/latest/env/vars.sh",
]


class JobsConfig(_Section):
    """The cluster side of the ``.qsub`` scripts "Criar cálculo" writes (spec 25 R6.3). The
    defaults are the reference scripts' (``Documentation/Referencia_de_scripts_QSUB``)."""

    qe_bin: str = "/opt/espresso-7.1/bin"  # on the cluster (POSIX), like remote_root
    mpi_command: str = "/opt/intel/oneapi/mpi/latest/bin/mpiexec -bootstrap ssh"
    parallel_env: str = "physica"  # #$ -pe <parallel_env> NP
    omp_threads: int = Field(default=1, ge=1)
    env_lines: list[str] = Field(default_factory=lambda: list(DEFAULT_ENV_LINES))
    cores: int = Field(default=64, ge=1)  # default of the NP field

    @field_validator("qe_bin")
    @classmethod
    def _strip_slash(cls, value: str) -> str:
        value = value.strip()
        return value.rstrip("/") if value not in ("", "/") else value

    @field_validator("parallel_env", "mpi_command")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("não pode ficar vazio")
        return value.strip()


class AppConfig(_Section):
    paths: PathsConfig = Field(default_factory=PathsConfig)
    cluster: ClusterConfig = Field(default_factory=ClusterConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    plot: PlotConfig = Field(default_factory=PlotConfig)
    ui: UiConfig = Field(default_factory=UiConfig)
    jobs: JobsConfig = Field(default_factory=JobsConfig)

    @property
    def sync_enabled(self) -> bool:
        return self.cluster.configured and bool(self.paths.remote_root)


class ConfigError(Exception):
    """Config file missing (when explicitly requested), unreadable or invalid."""

    def __init__(self, path: Path | None, problems: list[str]):
        self.path = path
        self.problems = problems
        where = f" ({path})" if path else ""
        super().__init__(f"Configuração inválida{where}:\n" + "\n".join(problems))


@dataclass
class LoadedConfig:
    config: AppConfig
    path: Path | None
    warnings: list[str] = field(default_factory=list)
    # True only when the lookup found no config.yaml at all (spec 18 R5: the welcome state). A
    # LoadedConfig built in code with ``path=None`` (tests, scripts) is not a first run.
    first_run: bool = False


def user_config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "qe-studio" / CONFIG_NAME


def find_config(
    cli_path: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Path | None:
    """First existing config in search order; explicit paths must exist."""
    environ = os.environ if environ is None else environ
    for explicit, origin in ((cli_path, "--config"), (environ.get(ENV_CONFIG), ENV_CONFIG)):
        if explicit:
            path = Path(explicit).expanduser()
            if not path.is_file():
                raise ConfigError(path, [f"arquivo indicado por {origin} não encontrado"])
            return path
    for candidate in ((cwd or Path.cwd()) / CONFIG_NAME, user_config_path()):
        if candidate.is_file():
            return candidate
    return None


def _format_validation(exc: ValidationError) -> list[str]:
    problems = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "(raiz)"
        msg = err["msg"].removeprefix("Value error, ")
        if err["type"] == "extra_forbidden":
            msg = "chave desconhecida"
        problems.append(f"• {loc}: {msg}")
    return problems


# Keys that no longer exist: dropped before validation (with a warning) so old files still load.
REMOVED_KEYS = (("plot", "export", "theme"),)


def _drop_removed_keys(data: dict, warnings: list[str]) -> dict:
    """Copy of ``data`` without ``REMOVED_KEYS``; each one found adds a warning."""
    for keys in REMOVED_KEYS:
        parents = [data]
        for key in keys[:-1]:
            parent = parents[-1].get(key)
            if not isinstance(parent, dict):  # wrong type: pydantic reports it
                break
            parents.append(parent)
        else:
            if keys[-1] in parents[-1]:
                data = _without(data, keys)
                name = ".".join(keys)
                warnings.append(f"{name} foi removido e é ignorado: apague a linha do config.yaml.")
    return data


def _without(data: dict, keys: tuple[str, ...]) -> dict:
    head, *rest = keys
    if not rest:
        return {k: v for k, v in data.items() if k != head}
    return {k: (_without(v, tuple(rest)) if k == head else v) for k, v in data.items()}


def parse_config(
    data: object, path: Path | None = None, warnings: list[str] | None = None
) -> AppConfig:
    """Validate ``data``. Warnings about removed keys are appended to ``warnings`` if given."""
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(path, ["o arquivo deve conter um mapeamento YAML (chave: valor)"])
    data = _drop_removed_keys(data, [] if warnings is None else warnings)
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(path, _format_validation(exc)) from exc


def _warnings(config: AppConfig) -> list[str]:
    warnings = []
    if not config.paths.local_root.is_dir():
        warnings.append(f"Pasta local não encontrada: {config.paths.local_root}")
    cluster = config.cluster
    if cluster.password is not None:
        warnings.append(
            "Senha em texto puro no config.yaml; prefira password_env ou autenticação por chave."
        )
    if config.sync_enabled:
        if cluster.auth == "key" and cluster.key_path and not cluster.key_path.is_file():
            warnings.append(f"Chave SSH não encontrada: {cluster.key_path}")
        if cluster.auth == "password" and cluster.resolve_password() is None:
            warnings.append(
                f"auth: password, mas a variável {cluster.password_env or '(password_env)'} "
                "não está definida."
            )
    else:
        warnings.append(
            "Cluster não configurado (host/user/remote_root): sincronização desativada."
        )
    return warnings


def load_config(
    cli_path: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> LoadedConfig:
    path = find_config(cli_path, environ, cwd)
    if path is None:
        config = AppConfig()
        return LoadedConfig(
            config,
            None,
            ["config.yaml não encontrado; usando valores padrão.", *_warnings(config)],
            first_run=True,
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(path, [f"não foi possível ler o arquivo: {exc}"]) from exc
    except yaml.YAMLError as exc:
        raise ConfigError(path, [f"YAML inválido: {exc}"]) from exc
    removed: list[str] = []
    config = parse_config(data, path, removed)
    return LoadedConfig(config, path, [*removed, *_warnings(config)])
