# -*- coding: utf-8 -*-
import re


def parse_fixed_count(output):
    match = re.search(r'opraveno:\s*(\d+)', output)
    if match:
        return int(match.group(1))
    return 0


def test_parse_fixed_count_from_output():
    output = "Síť: Oneplay1 (abc)\nOpraveno: Nova HD\nJiž v pořádku: 6, opraveno: 22\nHotovo."
    assert parse_fixed_count(output) == 22


def test_parse_fixed_count_zero():
    output = "Již v pořádku: 28, opraveno: 0\nŽádné změny nebyly potřeba."
    assert parse_fixed_count(output) == 0
