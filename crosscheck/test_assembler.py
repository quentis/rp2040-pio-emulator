from .assembler import assemble
from .case import Case


def make_case(*program: str) -> Case:
    return Case(name="c", program=list(program), cycles=1, observed_pins=[0])


def test_assembles_opcodes():
    assert assemble(make_case("set pins, 1", "pull block")).opcodes == [0xE001, 0x80A0]


def test_wrap_directives_become_config():
    program = assemble(make_case("nop", ".wrap_target", "nop", "nop", ".wrap"))

    assert program.config["wrap_target"] == 1
    assert program.config["wrap_top"] == 2


def test_default_wrap_covers_the_whole_program():
    program = assemble(make_case("nop", "nop", "nop"))

    assert (program.config["wrap_target"], program.config["wrap_top"]) == (0, 2)


def test_side_set_directive_becomes_config():
    program = assemble(make_case(".side_set 2", "nop side 3"))

    assert program.config["side_set_count"] == 2
    assert program.config["side_set_opt"] is False


def test_optional_side_set_directive_becomes_config():
    program = assemble(make_case(".side_set 1 opt", "nop side 1"))

    assert program.config["side_set_count"] == 1
    assert program.config["side_set_opt"] is True


def test_no_side_set_directive_leaves_side_set_unconfigured():
    assert "side_set_count" not in assemble(make_case("nop")).config
