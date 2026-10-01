from pathlib import Path

import pytest

from qe_studio.core.config import (
    ENV_CONFIG,
    AppConfig,
    ConfigError,
    find_config,
    load_config,
    parse_config,
)

ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_are_valid():
    config = AppConfig()
    assert config.plot.energy_min < config.plot.energy_max
    assert config.plot.export.formats == ["png", "svg", "pdf"]
    assert "*.save/" in config.sync.exclude
    assert not config.sync_enabled


def test_example_config_validates(tmp_path):
    loaded = load_config(ROOT / "config.example.yaml", environ={}, cwd=tmp_path)
    config = loaded.config
    assert config.cluster.host == "10.220.200.1"
    assert config.sync_enabled
    assert config.plot.orbital_colors["d"] == "#a855f7"
    assert config.paths.local_root == Path("~/qe_simulations").expanduser()


def test_search_order(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    cwd_cfg = write(tmp_path / "config.yaml", "{}")
    env_cfg = write(tmp_path / "env.yaml", "{}")
    cli_cfg = write(tmp_path / "cli.yaml", "{}")

    assert find_config(cli_cfg, {ENV_CONFIG: str(env_cfg)}, tmp_path) == cli_cfg
    assert find_config(None, {ENV_CONFIG: str(env_cfg)}, tmp_path) == env_cfg
    assert find_config(None, {}, tmp_path) == cwd_cfg

    cwd_cfg.unlink()
    user_cfg = tmp_path / "xdg" / "qe-studio" / "config.yaml"
    user_cfg.parent.mkdir(parents=True)
    write(user_cfg, "{}")
    assert find_config(None, {}, tmp_path) == user_cfg

    user_cfg.unlink()
    assert find_config(None, {}, tmp_path) is None


def test_explicit_missing_path_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="--config"):
        find_config(tmp_path / "nope.yaml", {}, tmp_path)
    with pytest.raises(ConfigError, match=ENV_CONFIG):
        find_config(None, {ENV_CONFIG: str(tmp_path / "nope.yaml")}, tmp_path)


def test_missing_config_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    loaded = load_config(None, environ={}, cwd=tmp_path)
    assert loaded.path is None
    assert loaded.config == AppConfig()
    assert any("não encontrado" in w for w in loaded.warnings)
    assert any("sincronização desativada" in w for w in loaded.warnings)


def test_empty_file_uses_defaults(tmp_path):
    loaded = load_config(write(tmp_path / "c.yaml", ""), environ={}, cwd=tmp_path)
    assert loaded.config == AppConfig()


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("plot: {energy_min: 3, energy_max: 1}", "energy_min deve ser menor"),
        ("plot: {fermi_color: notacolor}", "plot.fermi_color"),
        ("plot: {background: notacolor}", "plot.background"),
        ("plot: {export: {formats: [jpg]}}", "plot.export.formats"),
        ("plot: {export: {formats: []}}", "ao menos um formato"),
        ("plot: {figure_size: [0, 4]}", "plot.figure_size"),
        ("cluster: {auth: kerberos}", "cluster.auth"),
        ("cluster: {port: 70000}", "cluster.port"),
        ("paths: {local_rot: /x}", "paths.local_rot: chave desconhecida"),
        ("- a\n- b", "mapeamento YAML"),
        ("plot: [unclosed", "YAML inválido"),
    ],
)
def test_invalid_configs(tmp_path, text, fragment):
    with pytest.raises(ConfigError) as info:
        load_config(write(tmp_path / "bad.yaml", text), environ={}, cwd=tmp_path)
    assert fragment in str(info.value)


def test_partial_orbital_colors_keep_defaults():
    config = parse_config({"plot": {"orbital_colors": {"s": "red"}}})
    assert config.plot.orbital_colors["s"] == "red"
    assert config.plot.orbital_colors["p"] == "#06b6d4"


def test_paths_are_expanded(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMS", str(tmp_path))
    config = parse_config(
        {
            "paths": {"local_root": "$SIMS/runs", "remote_root": "/scratch/me/runs/"},
            "cluster": {"key_path": "~/.ssh/id_x"},
        }
    )
    assert config.paths.local_root == tmp_path / "runs"
    assert config.paths.remote_root == "/scratch/me/runs"
    assert config.cluster.key_path == Path.home() / ".ssh" / "id_x"


def test_password_resolution():
    cluster = parse_config(
        {"cluster": {"auth": "password", "password_env": "PW", "password": "inline"}}
    ).cluster
    assert cluster.resolve_password({"PW": "from-env"}) == "from-env"
    assert cluster.resolve_password({}) == "inline"
    assert "inline" not in repr(cluster)


def test_warnings(tmp_path):
    text = f"""
paths: {{local_root: {tmp_path / "missing"}, remote_root: /r}}
cluster: {{host: h, user: u, auth: password, password_env: NOPE_PW, password: x}}
"""
    loaded = load_config(write(tmp_path / "c.yaml", text), environ={}, cwd=tmp_path)
    joined = "\n".join(loaded.warnings)
    assert "Pasta local não encontrada" in joined
    assert "texto puro" in joined
    assert loaded.config.sync_enabled


REMOVED_THEME_WARNING = (
    "plot.export.theme foi removido e é ignorado: apague a linha do config.yaml."
)


def test_removed_export_theme_loads_with_a_warning(tmp_path):
    def warnings(text):
        loaded = load_config(write(tmp_path / "c.yaml", text), environ={}, cwd=tmp_path)
        return [w for w in loaded.warnings if "plot.export.theme" in w]

    assert warnings("plot: {export: {theme: current}}") == [REMOVED_THEME_WARNING]
    assert warnings("plot: {export: {theme: purple}}") == [REMOVED_THEME_WARNING]  # value unchecked
    assert warnings("plot: {export: {dpi: 600}}") == []
    assert warnings("plot: {background: '#000000'}") == []
    assert parse_config({"plot": {"background": "#000000"}}).plot.background == "#000000"
    assert not hasattr(parse_config({}).plot.export, "theme")


def test_removed_key_is_stripped_not_mutated():
    data = {"plot": {"export": {"theme": "dark", "dpi": 600}}}
    collected: list[str] = []
    config = parse_config(data, warnings=collected)
    assert config.plot.export.dpi == 600
    assert collected == [REMOVED_THEME_WARNING]
    assert data == {"plot": {"export": {"theme": "dark", "dpi": 600}}}  # caller's dict untouched
    parse_config(data)  # the warnings argument is optional


@pytest.mark.parametrize(
    "data",
    [
        {"plot": {"export": {"bogus": 1}}},
        {"plot": {"export": {"theme": "dark", "bogus": 1}}},
        {"plot": {"bogus": 1}},
        {"bogus": 1},
    ],
)
def test_other_unknown_keys_are_still_errors(data):
    with pytest.raises(ConfigError, match="chave desconhecida"):
        parse_config(data)


@pytest.mark.parametrize("data", [{"plot": 3}, {"plot": {"export": "png"}}])
def test_removed_key_with_wrong_parent_type_is_left_to_validation(data):
    with pytest.raises(ConfigError):
        parse_config(data)
