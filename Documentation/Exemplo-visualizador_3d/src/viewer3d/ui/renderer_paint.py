"""QPainter renderer: numpy projection and painter's algorithm, one draw call per primitive.

All geometry (projection, radii, depth sorting) is vectorised with numpy; only the final loop
that issues the Qt draw calls is Python. Coordinates are logical pixels (Qt scales them to the
device).
"""

from __future__ import annotations

import time

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QRadialGradient

from viewer3d.core.camera import Camera
from viewer3d.core.elements import element_for_label
from viewer3d.core.pick import TOLERANCE_PX, hit_test
from viewer3d.core.replicate import Scene
from viewer3d.core.structure import AtomRef, Structure
from viewer3d.ui.options import DisplayOptions
from viewer3d.ui.render_types import FrameStats, Prims, Projection
from viewer3d.ui.renderer_overlay import ABC_COLORS, MIN_PICK_RADIUS, arrow_head, draw_overlays

BALL_FACTOR = 0.45  # sphere radius as a fraction of the covalent radius
BOND_RADIUS = {"bola-vareta": 0.10, "vareta": 0.20, "fio": 0.0}  # Å
WIRE_WIDTH = 1.6  # px
GHOST_OPACITY = 0.35
DRAFT_MIN_BOND_WIDTH = 1.5  # px: thinner bonds are skipped in draft mode (not in wire style)

K_SPHERE, K_HALF, K_EDGE, K_ARROW = 0, 1, 2, 3  # primitive kinds
_CORNERS = np.array([(i, j, k) for i in (0, 1) for j in (0, 1) for k in (0, 1)])
_EDGES = np.array(
    [
        (a, b)
        for a in range(8)
        for b in range(a + 1, 8)
        if int(np.abs(_CORNERS[a] - _CORNERS[b]).sum()) == 1
    ]
)


def _mix(rgb: np.ndarray, other: float, amount: float) -> QColor:
    out = rgb * (1 - amount) + other * amount
    return QColor(int(out[0]), int(out[1]), int(out[2]))


class PaintRenderer:
    def __init__(self) -> None:
        self._r_cov = np.zeros(0)
        self._r_vdw = np.zeros(0)
        self._base_rgb = np.zeros((0, 3))
        self._rgb = np.zeros((0, 3))
        self._symbols: list[str] = []
        self._color_key: object = None
        self._gradient: dict[tuple[int, int], QBrush] = {}
        self._flat: dict[int, QBrush] = {}
        self._outline: dict[int, QPen] = {}
        self._bond_pens: dict[tuple[int, int], QPen] = {}
        self._font = QFont()
        self._font.setPointSizeF(9.0)
        self.stats = FrameStats()
        self._scene_id: int | None = None
        self._refs: tuple[AtomRef, ...] = ()
        self._ref_index: dict[AtomRef, int] = {}
        self._pick_xy = np.zeros((0, 2))
        self._pick_radii = np.zeros(0)
        self._pick_order = np.zeros(0, dtype=int)

    # --- structure-dependent tables and painter resources -------------------------------
    def set_structure(self, structure: Structure) -> None:
        elements = [element_for_label(s.label) for s in structure.species]
        self._r_cov = np.array([e.r_cov for e in elements])
        self._r_vdw = np.array([e.r_vdw for e in elements])
        self._base_rgb = np.array([e.color for e in elements]) * 255.0
        self._symbols = [e.symbol for e in elements]
        self._color_key = None
        self._scene_id = None

    def _use_colors(self, options: DisplayOptions) -> None:
        key = tuple(sorted(options.species_colors.items()))
        if key == self._color_key:
            return
        rgb = self._base_rgb.copy()
        for index, color in options.species_colors.items():
            if index < len(rgb):
                rgb[index] = color
        self._rgb, self._color_key = rgb, key
        for cache in (self._gradient, self._flat, self._outline, self._bond_pens):
            cache.clear()

    def _sphere_brush(self, species: int, quant: int) -> QBrush:
        brush = self._gradient.get((species, quant))
        if brush is None:
            rgb, r = self._rgb[species], quant / 2.0
            grad = QRadialGradient(
                QPointF(-0.30 * r, -0.35 * r), 1.35 * r, QPointF(-0.38 * r, -0.42 * r)
            )
            grad.setColorAt(0.0, _mix(rgb, 255, 0.75))
            grad.setColorAt(0.35, _mix(rgb, 255, 0.10))
            grad.setColorAt(1.0, _mix(rgb, 0, 0.60))
            brush = self._gradient[(species, quant)] = QBrush(grad)
        return brush

    def _flat_brush(self, species: int) -> QBrush:
        brush = self._flat.get(species)
        if brush is None:
            brush = self._flat[species] = QBrush(_mix(self._rgb[species], 0, 0.0))
        return brush

    def _outline_pen(self, species: int) -> QPen:
        pen = self._outline.get(species)
        if pen is None:
            pen = self._outline[species] = QPen(_mix(self._rgb[species], 0, 0.72), 0.9)
        return pen

    def _bond_pen(self, species: int, quant: int) -> QPen:
        pen = self._bond_pens.get((species, quant))
        if pen is None:
            pen = QPen(_mix(self._rgb[species], 0, 0.0), quant / 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            self._bond_pens[(species, quant)] = pen
        return pen

    # --- frame --------------------------------------------------------------------------
    def render(
        self,
        painter: QPainter,
        size: tuple[float, float],
        scene: Scene,
        camera: Camera,
        options: DisplayOptions,
        selection: tuple[AtomRef, ...] | list[AtomRef] = (),
        hover: AtomRef | None = None,
        draft: bool = False,
    ) -> FrameStats:
        started = time.perf_counter()
        if self._scene_id != id(scene):
            self._refs = scene.refs
            self._ref_index = {ref: i for i, ref in enumerate(scene.refs)}
            self._scene_id = id(scene)
        self._use_colors(options)
        camera.perspective = options.perspective
        proj = self._project(scene, camera, options, size)
        prims, n_bonds = self._primitives(scene, camera, options, size, proj, draft)

        dark = options.dark
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, not draft)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, not draft)
        painter.fillRect(
            QRectF(0, 0, size[0], size[1]), QColor(24, 27, 33) if dark else QColor(248, 248, 246)
        )
        self._draw(painter, prims, options, draft)
        self._overlays(painter, size, scene, camera, options, proj, selection, hover, draft)
        self._update_pick(scene, proj)

        order, kind, ghost = prims["order"], prims["kind"], prims["ghost"]
        spheres = kind[order] == K_SPHERE if len(order) else np.zeros(0, bool)
        ghosts = ghost[order] if len(order) else np.zeros(0, bool)
        self.stats = FrameStats(
            atoms=int((spheres & ~ghosts).sum()),
            ghosts=int((spheres & ghosts).sum()),
            bonds=n_bonds,
            primitives=len(order),
            ms=(time.perf_counter() - started) * 1000.0,
            draft=draft,
        )
        return self.stats

    def _project(self, scene, camera, options, size) -> Projection:
        xy, depth, scale = camera.project(scene.positions, size)
        visible = np.isfinite(xy[:, 0])
        if options.species_hidden:
            visible &= ~np.isin(scene.species, list(options.species_hidden))
        if options.style == "espaco-cheio":
            world = self._r_vdw[scene.species]
        else:
            world = self._r_cov[scene.species] * BALL_FACTOR
        radius = world * options.radius_scale * camera.zoom * scale
        has_spheres = options.style in ("bola-vareta", "espaco-cheio")
        return Projection(xy, depth, scale, visible, radius, has_spheres)

    def _primitives(self, scene, camera, options, size, proj, draft):
        style, n_real = options.style, scene.n_real
        xy, depth, scale, visible = proj.xy, proj.depth, proj.scale, proj.visible
        prims = Prims()

        a = b = np.zeros(0, dtype=int)
        if options.show_bonds and style != "espaco-cheio" and len(scene.bond_a):
            keep = visible[scene.bond_a] & visible[scene.bond_b]
            a, b = scene.bond_a[keep], scene.bond_b[keep]
        degree = np.bincount(np.concatenate([a, b]), minlength=len(xy))

        # atoms: spheres, or just a dot for unbonded atoms in the stick/wire styles
        idx = np.nonzero(visible if proj.has_spheres else visible & (degree == 0))[0]
        # a ghost only exists to be the far end of a drawn bond
        used = degree > 0
        idx = idx[(idx < n_real) | used[idx]]
        if proj.has_spheres:
            sphere_px = np.maximum(proj.radius_px[idx], 1.0)
        elif style == "vareta":
            sphere_px = np.maximum(BOND_RADIUS["vareta"] * 1.3 * camera.zoom * scale[idx], 1.5)
        else:
            sphere_px = np.full(len(idx), 2.2)
        prims.add(
            K_SPHERE, xy[idx], xy[idx], depth[idx], sphere_px, scene.species[idx], idx >= n_real
        )

        # bonds, split at the middle: each half takes the colour of its own atom
        if len(a):
            mid = (xy[a] + xy[b]) / 2
            mid_depth = (depth[a] + depth[b]) / 2
            if style == "fio":
                width = np.full(len(a), WIRE_WIDTH)
            else:
                width = 2 * BOND_RADIUS[style] * camera.zoom * (scale[a] + scale[b]) / 2
                width = np.maximum(width, 1.0)
            drawn = width >= DRAFT_MIN_BOND_WIDTH if draft and style != "fio" else slice(None)
            for end in (a, b):
                prims.add(
                    K_HALF,
                    xy[end][drawn],
                    mid[drawn],
                    ((depth[end] + mid_depth) / 2)[drawn],
                    width[drawn],
                    scene.species[end][drawn],
                    (end >= n_real)[drawn],
                )

        # cell box (and the repeated block, dimmer) and a, b, c arrows
        if options.show_cell:
            boxes = [(scene.cell, 1.0)]
            if scene.reps != (1, 1, 1):
                boxes.append((scene.block, 0.5))
            for vectors, strength in boxes:
                cxy, cdepth, _ = camera.project(scene.box_corners(vectors), size)
                i, j = _EDGES[:, 0], _EDGES[:, 1]
                prims.add(K_EDGE, cxy[i], cxy[j], (cdepth[i] + cdepth[j]) / 2, strength, -1)
        if options.show_axes:
            pts = np.vstack([np.zeros((1, 3)), scene.cell])
            axy, adepth, _ = camera.project(pts, size)
            prims.add(
                K_ARROW,
                np.repeat(axy[:1], 3, axis=0),
                axy[1:],
                (adepth[0] + adepth[1:]) / 2,
                1.8,
                np.arange(3),
            )
        return prims.finish(), len(a)

    # --- drawing ------------------------------------------------------------------------
    def _draw(self, painter: QPainter, prims, options: DisplayOptions, draft: bool) -> None:
        dark = options.dark
        box_pen = QPen(QColor(150, 160, 180, 170) if dark else QColor(80, 80, 95, 200), 1.0)
        block_pen = QPen(QColor(150, 160, 180, 90) if dark else QColor(80, 80, 95, 110), 1.0)
        no_pen = QPen(Qt.PenStyle.NoPen)
        order = prims["order"].tolist()
        x1, y1 = prims["x1"].tolist(), prims["y1"].tolist()
        x2, y2 = prims["x2"].tolist(), prims["y2"].tolist()
        size, spec = prims["size"].tolist(), prims["spec"].tolist()
        kind, ghost = prims["kind"].tolist(), prims["ghost"].tolist()
        gradient = not draft and options.style in ("bola-vareta", "espaco-cheio")
        set_pen, set_brush, set_origin = painter.setPen, painter.setBrush, painter.setBrushOrigin
        draw_ellipse, draw_line = painter.drawEllipse, painter.drawLine
        opacity = 1.0
        for p in order:
            want = GHOST_OPACITY if ghost[p] else 1.0
            if want != opacity:
                painter.setOpacity(want)
                opacity = want
            k = kind[p]
            if k == K_SPHERE:
                s, r, center = spec[p], size[p], QPointF(x1[p], y1[p])
                if gradient:
                    quant = max(2, round(r * 2))
                    r = quant / 2.0
                    set_brush(self._sphere_brush(s, quant))
                    set_pen(self._outline_pen(s))
                    set_origin(center)
                else:
                    set_brush(self._flat_brush(s))
                    set_pen(no_pen)
                draw_ellipse(center, r, r)
            elif k == K_HALF:
                set_pen(self._bond_pen(spec[p], max(1, round(size[p] * 2))))
                draw_line(QLineF(x1[p], y1[p], x2[p], y2[p]))
            elif k == K_EDGE:
                set_pen(box_pen if size[p] >= 1.0 else block_pen)
                draw_line(QLineF(x1[p], y1[p], x2[p], y2[p]))
            else:
                pen = QPen(QColor(*ABC_COLORS[spec[p]]), size[p])
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                set_pen(pen)
                draw_line(QLineF(x1[p], y1[p], x2[p], y2[p]))
                arrow_head(painter, x1[p], y1[p], x2[p], y2[p])
        painter.setOpacity(1.0)
        painter.setBrushOrigin(QPointF(0.0, 0.0))

    def _overlays(self, painter, size, scene, camera, options, proj, selection, hover, draft):
        n_real = scene.n_real
        xy, radius_px, visible = proj.xy, proj.radius_px, proj.visible
        labels: list[tuple[float, float, str]] = []
        if options.labels != "nenhum" and not draft:
            symbol = options.labels in ("simbolo", "ambos")
            index = options.labels in ("indice", "ambos")
            for i in np.nonzero(visible[:n_real])[0].tolist():
                text = self._symbols[scene.species[i]] if symbol else ""
                text += str(self._refs[i].index + 1) if index else ""
                offset = max(float(radius_px[i]), 3.0)
                labels.append((float(xy[i, 0]) + offset + 1, float(xy[i, 1]) - offset, text))
        hover_spot = None
        if hover is not None and hover not in selection:
            hover_spot = self._locate(hover, scene, camera, options, proj, size)
        selected = [
            (number, spot)
            for number, ref in enumerate(selection, start=1)
            if (spot := self._locate(ref, scene, camera, options, proj, size)) is not None
        ]
        draw_overlays(
            painter, self._font, size, camera, scene, options, labels, hover_spot, selected
        )

    def _locate(self, ref, scene, camera, options, proj, size):
        """(x, y, radius_px) of any atom copy; None when hidden or behind the eye."""
        if ref.index >= len(scene.frac) or scene.species[ref.index] in options.species_hidden:
            return None
        i = self._ref_index.get(ref)
        if i is not None:
            if not proj.visible[i]:
                return None
            return float(proj.xy[i, 0]), float(proj.xy[i, 1]), float(proj.radius_px[i])
        xy, _, scale = camera.project(scene.position(ref)[None, :], size)
        if not np.isfinite(xy).all():
            return None
        species = scene.species[ref.index]
        world = (
            self._r_vdw[species]
            if options.style == "espaco-cheio"
            else (self._r_cov[species] * BALL_FACTOR)
        )
        return (
            float(xy[0, 0]),
            float(xy[0, 1]),
            float(world * options.radius_scale * camera.zoom * scale[0]),
        )

    def max_world_radius(self, options: DisplayOptions) -> float:
        """Largest drawn atom radius (Å), used to pad the framing."""
        if len(self._r_cov) == 0:
            return 0.0
        if options.style == "espaco-cheio":
            radius = float(self._r_vdw.max())
        elif options.style == "bola-vareta":
            radius = float(self._r_cov.max()) * BALL_FACTOR
        else:
            radius = 0.3
        return radius * options.radius_scale

    # --- picking ------------------------------------------------------------------------
    def _update_pick(self, scene: Scene, proj: Projection) -> None:
        n_real = scene.n_real
        radii = np.maximum(proj.radius_px[:n_real], MIN_PICK_RADIUS)
        if not proj.has_spheres:
            radii = np.full(n_real, MIN_PICK_RADIUS)
        real = np.nonzero(proj.visible[:n_real])[0]
        self._pick_xy = proj.xy[:n_real]
        self._pick_radii = radii
        self._pick_order = real[np.argsort(proj.depth[real], kind="stable")]  # nearest first

    def pick(self, click: tuple[float, float], tolerance: float = TOLERANCE_PX) -> AtomRef | None:
        """Atom copy under a click, from the last frame's projection."""
        index = hit_test(click, self._pick_xy, self._pick_radii, self._pick_order, tolerance)
        return None if index is None else self._refs[index]

    def screen_position(self, ref: AtomRef) -> tuple[float, float] | None:
        """Last-frame screen position of a real atom copy."""
        index = self._ref_index.get(ref)
        if index is None or index >= len(self._pick_xy):
            return None
        x, y = self._pick_xy[index]
        return (float(x), float(y)) if np.isfinite(x) else None
