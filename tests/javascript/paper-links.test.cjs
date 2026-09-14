const {test} = require('node:test');
const assert = require('node:assert/strict');
const {paperUrlParts} = require('../../static/paper-links.js');
test('paper URL recognition preserves prose and DOI parentheses', () => {
    const text = 'See https://doi.org/10.1234/test(1). Also (https://example.org/paper).';
    const parts = paperUrlParts(text);
    assert.equal(parts.map(p => p.text).join(''), text);
    assert.deepEqual(parts.filter(p => p.url).map(p => p.url), ['https://doi.org/10.1234/test(1)', 'https://example.org/paper']);
});
test('only HTTP URLs become links and query strings are preserved', () => {
    assert.equal(paperUrlParts('javascript:alert(1)').some(p => p.url), false);
    assert.equal(paperUrlParts('https://example.org/pdf?a=1&b=2').find(p => p.url).url, 'https://example.org/pdf?a=1&b=2');
});
