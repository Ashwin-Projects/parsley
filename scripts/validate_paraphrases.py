"""Validate frozen held-out data and gold programs without running the NLP on inputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from parsley.compiler import semantic
from parsley.compiler.codegen import generate
from parsley.compiler.parser import parse
from parsley.session import Session
from parsley.verify.interpreter import run

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'tests/eval_data/paraphrases.json'


def validate(path: Path = DATA) -> tuple[int, int]:
    raw = path.read_bytes()
    expected_digest = path.with_suffix('.sha256').read_text().split()[0]
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ValueError('held-out data changed after freezing')
    data = json.loads(raw)
    if data.get('version') != 1 or data.get('category') != 'held_out_paraphrases':
        raise ValueError('unrecognized held-out schema')
    groups = data['groups']
    if len(groups) != 15:
        raise ValueError('expected 15 groups')
    ids, texts = set(), set()
    development = {
        fixture['input']
        for fixture_path in (ROOT / 'tests/fixtures').glob('*.json')
        for fixture in json.loads(fixture_path.read_text())['fixtures']
    }
    for group in groups:
        if group['id'] in ids or len(group['paraphrases']) != 4:
            raise ValueError('duplicate group or incorrect group size')
        ids.add(group['id'])
        if len(group['setup']) != len(parse(group['setup_minilang']).statements):
            raise ValueError(f"{group['id']}: inconsistent setup lengths")
        gold = parse(group['expected_minilang'])
        if len(gold.statements) != 1 or generate(gold) != group['expected_minilang']:
            raise ValueError(f"{group['id']}: gold is not one canonical statement")
        session = Session()
        for stmt in parse(group['setup_minilang']).statements + gold.statements:
            diagnostics = semantic.analyze(stmt, session)
            if any(d.level == 'error' for d in diagnostics):
                raise ValueError(f"{group['id']}: invalid gold semantics: {diagnostics}")
        program = group['setup_minilang'] + '\n' + group['expected_minilang']
        if run(program)[2]:
            raise ValueError(f"{group['id']}: gold failed execution")
        for item in group['paraphrases']:
            if item['id'] in ids or item['input'] in texts or item['input'] in development:
                raise ValueError('duplicate id/text or development-fixture leakage')
            if not isinstance(item['input'], str) or not 0 < len(item['input']) <= 500:
                raise ValueError('invalid held-out input')
            ids.add(item['id'])
            texts.add(item['input'])
    return len(groups), len(texts)


if __name__ == '__main__':
    groups, inputs = validate()
    print(f'PASS: {groups} groups / {inputs} inputs; digest, schema, separation and gold programs valid.')
    print('No NLP accuracy or paraphrase-consistency result is claimed by this validation.')
