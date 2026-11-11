"""Family-rooted pedigrees: the children of one couple share box 1."""

import datetime

import pytest

from kincade.charts import (
    _birth_estimates,
    family_children,
    plan_charts,
    plan_family_charts,
)
from kincade.model import Date, Day, Event, Family, ParentLink, Person, Tree
from kincade.pdf import Options, family_layout, page_geom, render_family


def ev(year: int) -> Event:
    return Event(date=Date(form="exact", start=Day(year=year)))


def make_tree(kids: int = 3) -> Tree:
    t = Tree()
    for pid in ("gf1", "gm1", "gf2", "gm2", "dad", "mom", "step"):
        t.people[pid] = Person(pid, pid)
    t.families["Fd"] = Family("Fd", "gf1", "gm1", children=["dad"])
    t.families["Fm"] = Family("Fm", "gf2", "gm2", children=["mom"])
    t.people["dad"].parents = [ParentLink("Fd")]
    t.people["mom"].parents = [ParentLink("Fm")]
    ids = [f"c{i}" for i in range(kids)]
    for i, cid in enumerate(ids):
        t.people[cid] = Person(cid, f"Child{i}", "Hansen", birth=ev(1990 + i))
        t.people[cid].parents = [ParentLink("F")]
    t.families["F"] = Family("F", "dad", "mom", children=ids)
    return t


def test_family_chart_slots():
    chart = plan_family_charts(make_tree(), "F")[0]
    assert chart.family == "F" and chart.children == ("c0", "c1", "c2")
    assert chart.slots[1] is None
    assert [chart.slots[p] for p in (2, 3, 4, 5, 6, 7)] == [
        "dad",
        "mom",
        "gf1",
        "gm1",
        "gf2",
        "gm2",
    ]


def test_person_charts_unchanged():
    chart = plan_charts(make_tree(), "c0")[0]
    assert chart.family is None and chart.children == ()


def test_generations_counts_children_as_one():
    chart = plan_family_charts(make_tree(), "F", generations=2)[0]
    assert {p for p, v in chart.slots.items() if v} == {2, 3}
    assert len(plan_family_charts(make_tree(), "F", generations=1)) == 1


def test_child_drawn_under_another_family_is_left_out():
    t = make_tree()
    t.families["Fx"] = Family("Fx", "step", "mom", children=["c0"])
    # c0 is a birth child of both families; the first listed wins the tie
    t.people["c0"].parents = [ParentLink("Fx"), ParentLink("F")]
    assert family_children(t, "F") == ["c1", "c2"]


def test_step_parent_is_not_drawn():
    t = make_tree(1)
    t.people["c0"].parents = [ParentLink("F", father="step")]
    chart = plan_family_charts(t, "F")[0]
    assert chart.slots[2] is None and chart.slots[3] == "mom"


def test_no_children_is_an_error():
    t = make_tree(0)
    with pytest.raises(ValueError):
        plan_family_charts(t, "F")
    with pytest.raises(KeyError):
        plan_family_charts(t, "nope")


def test_parents_estimated_from_youngest_child():
    t = make_tree(3)
    estimates = _birth_estimates(t, plan_family_charts(t, "F"), 2026)
    # youngest child born 1992 -> parents at most 1967, grandparents 1942
    assert estimates["dad"] == estimates["mom"] == 1967
    assert estimates["gf1"] == 1942
    assert estimates["c2"] == 1992


def test_render_family_and_index():
    t = make_tree(5)
    r = render_family(t, "F", Options(today=datetime.date(2026, 1, 1)))
    assert r.startswith(b"%PDF")


@pytest.mark.parametrize("large", [False, True])
def test_layout_capacity(large):
    geom = page_geom("letter", large)
    family_layout(geom, 1)
    with pytest.raises(ValueError, match="holds at most"):
        family_layout(geom, 200)


def test_too_many_children_message_points_to_large_print():
    with pytest.raises(ValueError, match="large print holds more"):
        render_family(make_tree(40), "F")


# ---------------------------------------------------------------- the command line

import kincade.cli  # noqa: E402

from conftest import ged  # noqa: E402

FAMILY_GED = ged(
    "0 HEAD",
    "0 @I1@ INDI", "1 NAME Ola /HANSEN/", "1 BIRT", "2 DATE 1880", "1 FAMC @F1@",
    "0 @I2@ INDI", "1 NAME Kari /HANSEN/", "1 BIRT", "2 DATE 1882", "1 FAMC @F1@",
    "0 @I3@ INDI", "1 NAME Per /HANSEN/", "1 BIRT", "2 DATE 1850", "1 FAMS @F1@",
    "1 FAMC @F2@",
    "0 @I4@ INDI", "1 NAME Anna /BERG/", "1 BIRT", "2 DATE 1855", "1 FAMS @F1@",
    "0 @I5@ INDI", "1 NAME Hans /HANSEN/", "1 BIRT", "2 DATE 1820", "1 FAMS @F2@",
    "0 @F1@ FAM", "1 HUSB @I3@", "1 WIFE @I4@", "1 CHIL @I1@", "1 CHIL @I2@",
    "0 @F2@ FAM", "1 HUSB @I5@", "1 CHIL @I3@",
    "0 @F3@ FAM", "1 HUSB @I5@",
)  # fmt: skip


@pytest.fixture
def family_file(tmp_path):
    path = tmp_path / "family.ged"
    path.write_bytes(FAMILY_GED)
    return path


def test_cli_family_names_the_file_for_the_couple(family_file, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert kincade.cli.main([str(family_file), "--family", "@f1@"]) == 0
    assert (tmp_path / "Per HANSEN & Anna BERG cascading pedigree.pdf").is_file()


def test_cli_family_writes_a_pdf(family_file, tmp_path, capsys):
    out = tmp_path / "out.pdf"
    assert kincade.cli.main([str(family_file), "--family", "F1", "-o", str(out)]) == 0
    assert out.read_bytes().startswith(b"%PDF")
    assert "1 chart" in capsys.readouterr().err


def test_cli_family_errors(family_file, tmp_path, capsys):
    out = str(tmp_path / "x.pdf")
    assert kincade.cli.main([str(family_file), "--family", "F99", "-o", out]) == 1
    assert "no family matches 'F99'" in capsys.readouterr().err
    assert kincade.cli.main([str(family_file), "--family", "F3", "-o", out]) == 2
    assert "no children" in capsys.readouterr().err
    assert not (tmp_path / "x.pdf").exists()


@pytest.mark.parametrize(
    "extra", [["--root", "I1"], ["--fan"], ["--root-family", "F1"]]
)
def test_cli_family_conflicts(family_file, extra, capsys):
    with pytest.raises(SystemExit) as e:
        kincade.cli.main([str(family_file), "--family", "F1", *extra])
    assert e.value.code == 2
    assert "--" in capsys.readouterr().err


def test_cli_needs_root_or_family(family_file, capsys):
    with pytest.raises(SystemExit) as e:
        kincade.cli.main([str(family_file)])
    assert e.value.code == 2
    assert "--root or --family is required" in capsys.readouterr().err


def test_cli_family_in_a_config_file(family_file, tmp_path, capsys):
    config = tmp_path / "k.toml"
    config.write_text(f'gedcom = "{family_file}"\nfamily = "F1"\n', encoding="utf-8")
    out = tmp_path / "o.pdf"
    assert kincade.cli.main(["--config", str(config), "-o", str(out)]) == 0
    assert out.is_file()
    # on the command line, --root replaces the file's family
    args = ["--config", str(config), "--root", "I3", "-o", str(out)]
    assert kincade.cli.main(args) == 0
    config.write_text('root = "I1"\nfamily = "F1"\n', encoding="utf-8")
    assert kincade.cli.main(["--config", str(config), "--show-config"]) == 2
    assert "root and family cannot both be set" in capsys.readouterr().err
