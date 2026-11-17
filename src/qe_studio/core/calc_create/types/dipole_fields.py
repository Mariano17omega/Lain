"""The fields of the saw-like field and its dipole correction in Slab, Supercélula and Molécula na
superfície (spec 98 R2, spec 105).

Two boxes, ``tefield`` and ``dipfield``, each writing its own key, and the four numbers of the field
(``edir``, ``emaxpos``, ``eopreg``, ``eamp``), shown while ``tefield`` is on. All start as the source
SCF has them: nothing it did not ask for is switched on. ``emaxpos`` and ``eopreg`` left empty are
computed for the structure the type built (``surface/dipole.py``; never the source SCF's: a supercell
rescales c, a molecule fills part of the vacuum) and shown filled. What the structure needs and the
boxes do not give is said under the field, and never blocks (``Work.advise``). With ``tefield`` pw.x
runs without symmetry (``PW/src/input.f90:659-663``) and, in a vc-relax that writes ``tstress``,
without stress (``:690-694``); ``dipfield`` alone is ignored (``PW/src/extfield.f90``).
"""

from __future__ import annotations

from ....i18n import _
from ...qe.input_edit import InputEditor
from ...qe.pw_input import fortran_float, fortran_int
from ..render import fortran_number
from ..scf_info import ScfInfo
from ..surface.dipole import EDIR as DEFAULT_EDIR
from ..surface.dipole import (
    MIN_MARGIN,
    DipoleWindow,
    dipole_window,
    flips_c,
    has_dipole,
    is_true,
    put_field,
    remove_field,
    short_margin,
)
from ..surface.model import Model
from ..surface.report import decimal
from .base import FieldKind, FormField, Work
from .relax import INPUT_KEY

__all__ = [
    "DIPFIELD",
    "DIPOLE_FACT",
    "EAMP",
    "EDIR",
    "EMAXPOS",
    "EOPREG",
    "NOT_WRITTEN",
    "TEFIELD",
    "apply_dipole",
    "chosen_edir",
    "corrects",
    "dipole_fields",
    "scf_has_dipole",
]

TEFIELD, DIPFIELD = "tefield", "dipfield"
EDIR, EMAXPOS, EOPREG, EAMP = "edir", "emaxpos", "eopreg", "eamp"
AXES = (1, 2, 3)
SHOWN = ((TEFIELD, (True,)),)  # the field's numbers: only with the field

DIPOLE_FACT = _("Correção de dipolo")
BOTH_KEYS = _("tefield e dipfield")
FIELD_ONLY = _("só tefield, sem correção de dipolo")
WINDOW_FACT = _(
    "{keys}: edir = {edir}, emaxpos = {emaxpos}, eopreg = {eopreg}, eamp = {eamp}; rampa de {ramp} Å a {margin} Å do átomo mais próximo (maior vácuo: {gap} Å); o pw.x roda sem simetria"
)
OFF_FACT = _("desligada")
IGNORED_FACT = _("desligada: dipfield sem tefield, que o pw.x ignora")
NOT_WRITTEN = _("não escrita: estrutura não gerada")
INVALID_FACT = _("não escrita: corrija os campos marcados")
EDIR_PROBLEM = _("edir deve ser 1, 2 ou 3")
RANGE_PROBLEM = _("{key} deve ficar entre 0 e 1 (fração da célula ao longo de edir)")
ONE_SIDE = _("um lado é diferente do outro: átomos fixos embaixo ou molécula de um lado só")
NO_SYMMETRY = _("nenhuma simetria inverte c")
POLAR_NOTE = _(
    "Slab assimétrico ao longo de c ({reason}): ele tem momento de dipolo, as imagens periódicas interagem e a energia e o potencial passam a depender do vácuo. Ative tefield e dipfield para corrigir"
)
NEEDS_TEFIELD = _(
    "dipfield só vale com tefield = .true.: sem ele o pw.x ignora a correção de dipolo. Ative tefield"
)
IDLE_NOTE = _(
    "tefield sem dipfield e com eamp = 0 não muda o potencial e só desliga a simetria do pw.x: ative dipfield para a correção de dipolo, ou informe eamp para um campo externo"
)
EAMP_NOTE = _(
    "eamp = {value} a.u. aplica um campo elétrico externo ao longo de edir (1 a.u. = 51.42 V/Å); para só corrigir o dipolo, use 0"
)
EDIR_NOTE = _(
    "edir = {edir}: o vácuo destes tipos fica ao longo de c (edir = 3); em outra direção a rampa cai dentro do material"
)
SHORT_NOTE = _(
    "A rampa do campo fica a {margin} Å do átomo mais próximo (maior vácuo: {gap} Å); abaixo de {minimum} Å a densidade alcança a rampa e as forças saem erradas: aumente o vácuo ou mova a rampa (emaxpos, eopreg)"
)
INSIDE_NOTE = _(
    "Há átomos dentro da rampa do campo (de emaxpos a emaxpos + eopreg): as forças saem erradas. Mova a rampa para o vácuo (emaxpos, eopreg)"
)
TSTRESS_NOTE = _("tstress removido: com tefield o pw.x desliga a tensão que o vc-relax usa")
VC_STRESS_NOTE = _("vc-relax com tefield: a tensão do pw.x não inclui o termo do campo")
REMOVED_NOTE = _("Chaves do campo do SCF removidas ({keys})")


def _scf_edir(scf: ScfInfo) -> int:
    number = fortran_int(scf.value("system", EDIR) or "")
    return number if number in AXES else DEFAULT_EDIR


def _scf_eamp(scf: ScfInfo) -> float:
    return fortran_float(scf.value("system", EAMP) or "") or 0.0


def dipole_fields(scf: ScfInfo) -> list[FormField]:
    """The two boxes (shown in the ``padrao`` mode too: the choice a whole chain shares) and the
    field's four numbers, all of the input's tab and all starting as ``scf`` has them."""
    field_on = is_true(scf.value("control", TEFIELD))

    def box(field_id: str, label: str, default: bool, tooltip: str) -> FormField:
        return FormField(
            field_id, label, "bool", default, group=INPUT_KEY, standard=True, tooltip=tooltip
        )

    def number(
        field_id: str, label: str, kind: FieldKind, default: float | None, tooltip: str
    ) -> FormField:
        auto = default is None
        return FormField(
            field_id,
            label,
            kind,
            default,
            group=INPUT_KEY,
            tooltip=tooltip,
            shown_when=SHOWN,
            auto=auto,
            hint=_("vazio = automático") if auto else "",
        )

    return [
        box(
            TEFIELD,
            _("Campo em dente de serra (tefield)"),
            field_on,
            _(
                "Potencial em dente de serra ao longo de edir (tefield): é o que a correção de dipolo usa. Com ele o pw.x não usa simetria e, num vc-relax, a tensão não inclui o termo do campo. Nasce como no SCF de origem"
            ),
        ),
        box(
            DIPFIELD,
            _("Correção de dipolo (dipfield)"),
            is_true(scf.value("control", DIPFIELD)),
            _(
                "Correção de dipolo de Bengtsson (dipfield): cancela o campo que o dipolo de um slab assimétrico cria entre as imagens periódicas. Só vale com tefield. O complexo e a superfície limpa de uma adsorção precisam da mesma escolha. Nasce como no SCF de origem"
            ),
        ),
        number(
            EDIR,
            _("Direção do campo (edir)"),
            "int",
            _scf_edir(scf) if field_on else DEFAULT_EDIR,
            _(
                "Vetor da rede recíproca ao longo do qual o campo é aplicado (1, 2 ou 3). O vácuo destes tipos fica ao longo de c: 3"
            ),
        ),
        number(
            EMAXPOS,
            _("Início da rampa (emaxpos)"),
            "float",
            None,
            _(
                "Fração da célula, ao longo de edir, onde a rampa do potencial começa (entre 0 e 1). Vazio: a rampa fica no meio do maior vácuo da estrutura gerada"
            ),
        ),
        number(
            EOPREG,
            _("Largura da rampa (eopreg)"),
            "float",
            None,
            _(
                "Fração da célula que a rampa ocupa (entre 0 e 1). Vazio: 0.1, o padrão do pw.x, ou um terço do vácuo quando ele é menor"
            ),
        ),
        number(
            EAMP,
            _("Amplitude do campo (eamp, a.u.)"),
            "float",
            _scf_eamp(scf) if field_on else 0.0,
            _(
                "Amplitude do campo elétrico externo, em unidades atômicas de Hartree (1 a.u. = 51.42 V/Å). Só para a correção de dipolo: 0"
            ),
        ),
    ]


def scf_has_dipole(scf: ScfInfo) -> bool:
    return has_dipole(scf.value)


def corrects(work: Work) -> bool:
    """Whether the boxes ask for the dipole correction: both on."""
    return bool(work.values.get(TEFIELD)) and bool(work.values.get(DIPFIELD))


def chosen_edir(work: Work) -> int | None:
    """The direction of the field (None: not 1, 2 or 3)."""
    edir = work.values.get(EDIR)
    return edir if edir in AXES else None


def _window(work: Work, model: Model | None) -> tuple[DipoleWindow, int] | str:
    """The ramp for the fields and the structure written, with its direction; or why there is none
    (the fact of ``geracao.md``), the fields at fault marked."""
    values = work.values
    edir = chosen_edir(work)
    if edir is None:
        work.problem(EDIR, EDIR_PROBLEM)
    typed = {key: values.get(key) for key in (EMAXPOS, EOPREG)}
    for key, value in typed.items():
        if value is not None and not 0.0 < value < 1.0:
            work.problem(key, RANGE_PROBLEM.format(key=key))
    if edir is None or any(key in work.problems for key in typed):
        return INVALID_FACT
    if model is None:
        return NOT_WRITTEN
    window = dipole_window(model.cell, model.frac, edir - 1, typed[EMAXPOS], typed[EOPREG])
    for key, computed in ((EMAXPOS, window.emaxpos), (EOPREG, window.eopreg)):
        if typed[key] is None:
            work.auto[key] = computed
    return window, edir


def _window_notes(work: Work, window: DipoleWindow, edir: int, eamp: float, dip: bool) -> None:
    if not dip and not eamp:
        work.advise(TEFIELD, IDLE_NOTE)
    if eamp:
        work.advise(EAMP, EAMP_NOTE.format(value=fortran_number(eamp)))
    if edir != DEFAULT_EDIR:
        work.advise(EDIR, EDIR_NOTE.format(edir=edir))
    if window.margin <= 0.0:
        work.advise(EMAXPOS, INSIDE_NOTE)
    elif short_margin(window):
        work.advise(
            EMAXPOS,
            SHORT_NOTE.format(
                margin=decimal(window.margin),
                gap=decimal(window.gap),
                minimum=decimal(MIN_MARGIN, 1),
            ),
        )


def apply_dipole(
    work: Work,
    editor: InputEditor,
    model: Model | None,
    facts: list[tuple[str, str]],
    *,
    vc: bool = False,
    polar: bool = False,
) -> DipoleWindow | None:
    """Write or take out the field and its correction as the boxes say; ``model`` is the structure
    written (None: not built), ``vc`` a vc-relax, ``polar`` that the slab has a dipole whatever its
    symmetry (one side fixed, a molecule on top). Returns the window written."""
    values = work.values
    tefield, dipfield = bool(values.get(TEFIELD)), bool(values.get(DIPFIELD))
    if dipfield and not tefield:
        work.advise(TEFIELD, NEEDS_TEFIELD)
    elif not dipfield and (
        polar or (model is not None and not flips_c(model.cell, model.frac, model.labels))
    ):
        work.advise(DIPFIELD, POLAR_NOTE.format(reason=ONE_SIDE if polar else NO_SYMMETRY))
    if not tefield:
        removed = remove_field(editor, dipfield=not dipfield)
        if dipfield and not is_true(editor.get("control", DIPFIELD)):
            editor.set("control", DIPFIELD, ".true.")
        if removed:
            work.notes.append(REMOVED_NOTE.format(keys=", ".join(removed)))
        facts.append((DIPOLE_FACT, IGNORED_FACT if dipfield else OFF_FACT))
        return None
    found = _window(work, model)
    if isinstance(found, str):
        facts.append((DIPOLE_FACT, found))
        return None
    window, edir = found
    eamp = values.get(EAMP) or 0.0
    removed = put_field(editor, window, edir=edir, eamp=eamp, dipfield=dipfield)
    if removed:
        work.notes.append(REMOVED_NOTE.format(keys=", ".join(removed)))
    _window_notes(work, window, edir, eamp, dipfield)
    if vc:
        if editor.remove("control", "tstress"):
            work.notes.append(TSTRESS_NOTE)
        work.notes.append(VC_STRESS_NOTE)
    fact = WINDOW_FACT.format(
        keys=BOTH_KEYS if dipfield else FIELD_ONLY,
        edir=edir,
        emaxpos=f"{window.emaxpos:.4f}",
        eopreg=f"{window.eopreg:.4f}",
        eamp=fortran_number(eamp),
        ramp=decimal(window.ramp),
        margin=decimal(window.margin),
        gap=decimal(window.gap),
    )
    facts.append((DIPOLE_FACT, fact))
    return window
