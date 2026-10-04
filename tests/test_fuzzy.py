"""core/fuzzy (spec 18 R2.3): subsequence match without case or accents, ranked."""

from hypothesis import given
from hypothesis import strategies as st

from qe_studio.core.fuzzy import Candidate, fold, parse_query, rank, score

ACTION, FOLDER, TAB = "Ações", "Pastas", "Abas"


def cands(*rows):
    return [Candidate(f"{c}:{t}", c, t) for c, t in rows]


def texts(found):
    return [c.text for c in found]


def test_fold_drops_case_and_accents():
    assert fold("Gráfico Ação ÇÃ") == "grafico acao ca"


def test_parse_query_splits_the_scope_prefix():
    assert parse_query(">ger") == (ACTION, "ger")
    assert parse_query("  /rel ") == (FOLDER, "rel")
    assert parse_query("@ bands") == (TAB, "bands")
    assert parse_query("gerar") == (None, "gerar")
    assert parse_query("") == (None, "")


def test_no_match_without_the_letters_in_order():
    assert score("zzz", "Gerar gráfico") is None
    assert score("regar", "Gerar gráfico") is None  # r-e-g-a-r is not in that order
    assert score("grafico", "Gerar gráfico") is not None


def test_prefix_beats_word_start_beats_subsequence():
    prefix = score("ger", "Gerar gráfico")
    word = score("graf", "Gerar gráfico")
    subsequence = score("gfc", "Gerar gráfico")
    assert prefix and word and subsequence
    assert prefix > word > subsequence


def test_a_word_inside_a_path_counts_as_a_word_start():
    assert score("rel", "01_relax") > score("rel", "04_pdos/orbitals_rel")  # earlier wins
    assert score("rel", "01_relax") > score("rlx", "01_relax")


def test_rank_orders_by_score_then_recency_then_text():
    found = rank("g", cands((ACTION, "Gerar gráfico"), (ACTION, "Exportar gráfico")))
    assert texts(found) == ["Gerar gráfico", "Exportar gráfico"]
    tie = cands((FOLDER, "alpha"), (FOLDER, "alphb"))
    assert texts(rank("alph", tie)) == ["alpha", "alphb"]
    recent = {tie[1].key: 5}
    assert texts(rank("alph", tie, recent)) == ["alphb", "alpha"]


def test_a_scope_prefix_restricts_the_category():
    pool = cands((ACTION, "Gerar gráfico"), (FOLDER, "01_relax"), (TAB, "scf.out"))
    assert texts(rank(">", pool)) == ["Gerar gráfico"]
    assert texts(rank("/rel", pool)) == ["01_relax"]
    assert texts(rank("@scf", pool)) == ["scf.out"]
    assert set(texts(rank("c", pool))) == {"Gerar gráfico", "scf.out"}  # no prefix: all scopes


def test_empty_query_keeps_the_order_and_the_limit():
    pool = cands(*[(FOLDER, f"f{i}") for i in range(80)])
    assert rank("", pool, limit=50) == pool[:50]


@given(st.text(max_size=12), st.text(max_size=30))
def test_score_never_raises_and_matches_only_subsequences(query, text):
    value = score(query, text)
    letters = [c for c in fold(query).strip() if c != " "]
    hay = iter(fold(text))
    is_subsequence = all(letter in hay for letter in letters)  # consumes the iterator in order
    if value is not None:
        assert is_subsequence or not letters or fold(text).startswith(fold(query).strip())
    else:
        assert not is_subsequence


@given(st.lists(st.text(max_size=10), max_size=20), st.text(max_size=6))
def test_rank_returns_a_bounded_subset(names, query):
    pool = [Candidate(f"k{i}", FOLDER, name) for i, name in enumerate(names)]
    found = rank(query, pool, limit=7)
    assert len(found) <= 7
    assert all(c in pool for c in found)
