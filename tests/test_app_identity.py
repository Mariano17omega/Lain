import pytest
from PyQt6.QtGui import QGuiApplication

from qe_studio.ui.app_identity import (
    APPLICATION_NAME,
    DESKTOP_FILE_NAME,
    ORGANIZATION_NAME,
    app_icon,
    configure_application,
)

SIZES = {16, 32, 48, 64, 128, 256}


@pytest.fixture
def restore_identity(qapp):
    """configure_application changes process-wide Qt state: put it back after the test."""
    saved = (
        qapp.applicationName(),
        qapp.organizationName(),
        qapp.applicationVersion(),
        QGuiApplication.desktopFileName(),
        qapp.windowIcon(),
    )
    yield
    name, organization, version, desktop, icon = saved
    qapp.setApplicationName(name)
    qapp.setOrganizationName(organization)
    qapp.setApplicationVersion(version)
    QGuiApplication.setDesktopFileName(desktop)
    qapp.setWindowIcon(icon)


def test_application_has_a_window_icon_and_desktop_file_name(qapp, restore_identity):
    configure_application(qapp)
    assert not qapp.windowIcon().isNull()
    assert QGuiApplication.desktopFileName() == "lain"
    assert {s.width() for s in qapp.windowIcon().availableSizes()} >= SIZES


def test_internal_identifiers_keep_the_old_product_name(qapp, restore_identity):
    """Renaming them would orphan existing QSettings and config directories (CLAUDE.md)."""
    configure_application(qapp)
    assert (qapp.applicationName(), qapp.organizationName()) == ("QE Studio", "qe-studio")
    assert (APPLICATION_NAME, ORGANIZATION_NAME, DESKTOP_FILE_NAME) == (
        "QE Studio",
        "qe-studio",
        "lain",
    )


def test_icon_renders_at_every_size(qapp):
    icon = app_icon()
    for size in sorted(SIZES):
        image = icon.pixmap(size).toImage()
        assert (image.width(), image.height()) == (size, size)
        assert image.pixelColor(size // 2, size // 2).alpha() == 255  # opaque body
        assert image.pixelColor(0, 0).alpha() == 0  # rounded corner stays transparent
