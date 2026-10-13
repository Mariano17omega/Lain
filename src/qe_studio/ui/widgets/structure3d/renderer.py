"""QPainter renderer: numpy projection and painter's algorithm, one draw call per primitive.

Projection, radii, the bond halves and the depth sort are numpy (``core/structure3d``); only the loop that
issues the Qt calls is Python. Coordinates are logical pixels. A sphere is ordered by its center, a bond
half by the 3D middle of the half; the halves start on their sphere's surface (``geometry.half_bonds``), so
no stick is painted inside an atom (spec 43 R2).
"""

from __future__ import annotations

import time

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient

from ....core.structure3d.camera import Camera
from ....core.structure3d.elements import element_for_label
from ....core.structure3d.geometry import bond_radius, max_world_radius, species_radii
from ....core.structure3d.model import AtomRef, Structure
from ....core.structure3d.options import DisplayOptions
from ....core.structure3d.pick import TOLERANCE_PX, hit_test
from ....core.structure3d.replicate import Scene
from ...painting import ui_font
from .bonds_paint import BondShader, add_halves
from .overlay import ABC_COLORS, MIN_PICK_RADIUS, Spot, arrow_head, draw_overlays
from .render_types import FrameStats, Prims, Projection

WIRE_WIDTH = 1.6  # px, the bonds of "fio"
DOT_PX = 2.2  # px, an unbonded atom in "fio"
MIN_SPHERE_PX = {"vareta": 1.5}  # px, the smallest drawn ball (1.0 for the other styles)
GHOST_OPACITY = 0.35
DRAFT_MIN_BOND_WIDTH = 1.5  # px: thinner sticks are skipped in draft mode (not the wires of "fio")
LABEL_PX = 11  # label font at scale 1
BACKGROUND = {True: (24, 27, 33), False: (248, 248, 246)}  # by dark background
BOX = {True: (150, 160, 180, 170), False: (80, 80, 95, 200)}
BLOCK = {True: (150, 160, 180, 90), False: (80, 80, 95, 110)}

K_SPHERE, K_HALF, K_WIRE, K_EDGE, K_ARROW = 0, 1, 2, 3, 4  # primitive kinds
SPHERE_STYLES = ("bola-vareta", "vareta", "espaco-cheio")  # every atom is a ball
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
        self._wire_pens: dict[int, QPen] = {}
        self._shader = BondShader()
        self._halves: list[
            list[float]
        ] = []  # per drawn half: 4 corners (x, y), light and shade edges
        self.stats = FrameStats()
        self._scene_id: int | None = None
        self._refs: tuple[AtomRef, ...] = ()
        self._ref_index: dict[AtomRef, int] = {}
        self._pick_xy = np.zeros((0, 2))
        self._pick_radii = np.zeros(0)
        self._pick_order = np.zeros(0, dtype=int)

    # -- structure-dependent tables and painter resources ------------------------------------------
    def set_structure(self, structure: Structure) -> None:
        elements = [element_for_label(s.label) for s in structure.species]
        self._r_cov = np.array([e.r_cov for e in elements])
        self._r_vdw = np.array([e.r_vdw for e in elements])
        self._base_rgb = np.array([e.color for e in elements]).reshape(-1, 3) * 255.0
        self._symbols = [
            e.symbol if e.known else s.label
            for e, s in zip(elements, structure.species, strict=True)
        ]
        self._color_key = None
        self._scene_id = None

    def species_rgb(self, species: int) -> tuple[int, int, int]:
        """The element color of a species (0..255), the one "Restaurar cores" goes back to."""
        r, g, b = (round(float(c)) for c in self._base_rgb[species])
        return r, g, b

    def _use_colors(self, options: DisplayOptions) -> None:
        key = tuple(sorted(options.species_colors.items()))
        if key == self._color_key:
            return
        rgb = self._base_rgb.copy()
        for index, color in options.species_colors.items():
            if index < len(rgb):
                rgb[index] = color
        self._rgb, self._color_key = rgb, key
        for cache in (self._gradient, self._flat, self._outline, self._wire_pens):
            cache.clear()
        self._shader.set_colors(rgb)

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

    def _wire_pen(self, species: int) -> QPen:
        pen = self._wire_pens.get(species)
        if pen is None:
            pen = QPen(_mix(self._rgb[species], 0, 0.0), WIRE_WIDTH)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            self._wire_pens[species] = pen
        return pen

    def world_radii(self, options: DisplayOptions) -> np.ndarray:
        """The drawn radius of each species, Å."""
        return species_radii(options.style, self._r_cov, self._r_vdw, options.radius_scale)

    def max_world_radius(self, options: DisplayOptions) -> float:
        """Largest drawn atom radius (Å), used to pad the framing."""
        if len(self._r_cov) == 0:
            return 0.0
        return max_world_radius(options.style, self._r_cov, self._r_vdw, options.radius_scale)

    # -- frame -------------------------------------------------------------------------------------
    def render(
        self,
        painter: QPainter,
        size: tuple[float, float],
        scene: Scene,
        camera: Camera,
        options: DisplayOptions,
        current: AtomRef | None = None,
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

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, not draft)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, not draft)
        painter.fillRect(QRectF(0, 0, size[0], size[1]), QColor(*BACKGROUND[options.dark]))
        self._draw(painter, prims, options, draft)
        self._overlays(painter, size, scene, camera, options, proj, current, hover, draft)
        self._update_pick(scene, proj)

        order, kind, ghost = prims["order"], prims["kind"], prims["ghost"]
        spheres = kind[order] == K_SPHERE if len(order) else np.zeros(0, bool)
        ghosts = ghost[order].astype(bool) if len(order) else np.zeros(0, bool)
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
        world = self.world_radii(options)[scene.species]
        radius = world * camera.zoom * scale
        return Projection(xy, depth, scale, visible, radius, options.style in SPHERE_STYLES)

    def _primitives(self, scene, camera, options, size, proj, draft):
        style, n_real = options.style, scene.n_real
        xy, depth, visible = proj.xy, proj.depth, proj.visible
        prims = Prims()

        a = b = np.zeros(0, dtype=int)
        keep = None
        if options.show_bonds and style != "espaco-cheio" and len(scene.bond_a):
            keep = visible[scene.bond_a] & visible[scene.bond_b]
            a, b = scene.bond_a[keep], scene.bond_b[keep]
        degree = np.bincount(np.concatenate([a, b]), minlength=len(xy))

        # atoms: balls, or a dot for the unbonded atoms of "fio"; a ghost only ends a drawn bond
        idx = np.nonzero(visible if proj.has_spheres else visible & (degree == 0))[0]
        idx = idx[(idx < n_real) | (degree[idx] > 0)]
        if proj.has_spheres:
            sphere_px = np.maximum(proj.radius_px[idx], MIN_SPHERE_PX.get(style, 1.0))
        else:
            sphere_px = np.full(len(idx), DOT_PX)
        prims.add(
            K_SPHERE, xy[idx], xy[idx], depth[idx], sphere_px, scene.species[idx], idx >= n_real
        )

        self._halves = []
        if len(a) and style == "fio":  # lines from center to middle, uncut
            mid = (xy[a] + xy[b]) / 2
            mid_depth = (depth[a] + depth[b]) / 2
            for end in (a, b):
                prims.add(
                    K_WIRE,
                    xy[end],
                    mid,
                    (depth[end] + mid_depth) / 2,
                    WIRE_WIDTH,
                    scene.species[end],
                    end >= n_real,
                )
        elif len(a):
            radii = self.world_radii(options)[scene.species]
            rho = bond_radius(options.style)
            min_width = DRAFT_MIN_BOND_WIDTH if draft else 0.0
            self._halves = add_halves(
                prims, K_HALF, scene, camera, size, radii, rho, keep, min_width
            )

        # cell box (and the repeated block, dimmer) and the a, b, c arrows
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

    # -- drawing -----------------------------------------------------------------------------------
    def _draw(self, painter: QPainter, prims, options: DisplayOptions, draft: bool) -> None:
        dark = options.dark
        box_pen, block_pen = QPen(QColor(*BOX[dark]), 1.0), QPen(QColor(*BLOCK[dark]), 1.0)
        no_pen = QPen(Qt.PenStyle.NoPen)
        order = prims["order"].tolist()
        x1, y1 = prims["x1"].tolist(), prims["y1"].tolist()
        x2, y2 = prims["x2"].tolist(), prims["y2"].tolist()
        size, spec = prims["size"].tolist(), prims["spec"].tolist()
        kind, ghost, aux = prims["kind"].tolist(), prims["ghost"].tolist(), prims["aux"].tolist()
        halves = self._halves
        shaded = not draft and options.style in SPHERE_STYLES
        shader = self._shader
        set_pen, set_brush, set_origin = painter.setPen, painter.setBrush, painter.setBrushOrigin
        draw_ellipse, draw_line, draw_quad = (
            painter.drawEllipse,
            painter.drawLine,
            painter.drawConvexPolygon,
        )
        zero = QPointF(0.0, 0.0)
        opacity, at_zero = 1.0, True  # the brush origin: spheres move it, gradients need (0, 0)
        for p in order:
            want = GHOST_OPACITY if ghost[p] else 1.0
            if want != opacity:
                painter.setOpacity(want)
                opacity = want
            k = kind[p]
            if k == K_SPHERE:
                s, r, center = spec[p], size[p], QPointF(x1[p], y1[p])
                if shaded:
                    quant = max(2, round(r * 2))
                    r = quant / 2.0
                    set_brush(self._sphere_brush(s, quant))
                    set_pen(self._outline_pen(s))
                    set_origin(center)
                    at_zero = False
                else:
                    set_brush(self._flat_brush(s))
                    set_pen(no_pen)
                draw_ellipse(center, r, r)
            elif k == K_HALF:
                h = halves[aux[p]]
                set_pen(no_pen)
                if shaded:
                    if not at_zero:
                        set_origin(zero)
                        at_zero = True
                    gradient = shader.gradient(spec[p])
                    gradient.setStart(h[8], h[9])
                    gradient.setFinalStop(h[10], h[11])
                    set_brush(gradient)
                else:
                    set_brush(shader.flat(spec[p]))
                draw_quad(
                    QPointF(h[0], h[1]),
                    QPointF(h[2], h[3]),
                    QPointF(h[4], h[5]),
                    QPointF(h[6], h[7]),
                )
            elif k == K_WIRE:
                set_pen(self._wire_pen(spec[p]))
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
        painter.setBrushOrigin(zero)

    def _overlays(self, painter, size, scene, camera, options, proj, current, hover, draft):
        n_real = scene.n_real
        xy, radius_px, visible = proj.xy, proj.radius_px, proj.visible
        labels: list[tuple[float, float, str]] = []
        if options.labels != "nenhum" and not draft:
            symbol = options.labels in ("simbolo", "ambos")
            number = options.labels in ("indice", "ambos")
            for i in np.nonzero(visible[:n_real])[0].tolist():
                text = self._symbols[scene.species[i]] if symbol else ""
                text += str(self._refs[i].index + 1) if number else ""
                offset = max(float(radius_px[i]), 3.0)
                labels.append((float(xy[i, 0]) + offset + 1, float(xy[i, 1]) - offset, text))
        hover_spot = None
        if hover is not None and hover != current:
            hover_spot = self._locate(hover, scene, camera, options, proj, size)
        current_spot = None
        if current is not None:
            current_spot = self._locate(current, scene, camera, options, proj, size)
        font = ui_font(LABEL_PX)
        draw_overlays(painter, font, size, camera, scene, options, labels, hover_spot, current_spot)

    def _locate(self, ref, scene, camera, options, proj, size) -> Spot | None:
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
        world = self.world_radii(options)[scene.species[ref.index]]
        return float(xy[0, 0]), float(xy[0, 1]), float(world * camera.zoom * scale[0])

    # -- picking -----------------------------------------------------------------------------------
    def _update_pick(self, scene: Scene, proj: Projection) -> None:
        n_real = scene.n_real
        if proj.has_spheres:
            radii = np.maximum(proj.radius_px[:n_real], MIN_PICK_RADIUS)
        else:
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
        """Last-frame screen position of a drawn atom copy."""
        index = self._ref_index.get(ref)
        if index is None or index >= len(self._pick_xy):
            return None
        x, y = self._pick_xy[index]
        return (float(x), float(y)) if np.isfinite(x) else None
