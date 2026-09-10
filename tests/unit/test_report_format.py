import pytest
from package.agents.reporter import parse_section

@pytest.mark.parametrize('content', [
    '{"summary":"First [S1].\\n\\nSecond [S2]."}',
    '{"summary":"First [S1].\n\nSecond [S2]."}',
    'Here is the section:\n{"summary":["First [S1].", "Second [S2]."]}',
    '```json\n{"summary":["First [S1].", "Second [S2]."]}\n```',
])
def test_lossless_summary_format_variations(content):
    assert parse_section(content, 'summary') == 'First [S1].\n\nSecond [S2].'

@pytest.mark.parametrize('content', ['{"summary":"unfinished', '{"wrong":"text"}', '{"summary":[{}]}', '{"summary":"Valid"} trailing claims', 'Plain prose', '{"summary":"one"}{"summary":"two"}'])
def test_incomplete_or_ambiguous_sections_are_rejected(content):
    with pytest.raises(ValueError):
        parse_section(content, 'summary')
