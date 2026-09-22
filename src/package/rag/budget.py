"""Measure final JSON length, including escaping and provenance overhead."""
import json

TEXT_FIELDS = ('text', 'abstract_excerpt', 'abstract')


def fit_evidence(context, budget):
    rows = json.loads(context)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Evidence must be a list of records')
    records = []
    for row in rows:
        record = dict(row)
        for key, limit in {'title':220, 'source_url':240, 'section_title':160, 'html_anchor':160}.items():
            if isinstance(record.get(key), str) and len(record[key]) > limit:
                record[key] = record[key][:limit]
                record['metadata_truncated'] = True
        records.append(record)
    def encode(cap):
        fitted = []
        for row in records:
            item = dict(row)
            for key in TEXT_FIELDS:
                if isinstance(item.get(key), str) and len(item[key]) > cap:
                    item[key] = item[key][:cap]
                    item['excerpt_truncated'] = True
            fitted.append(item)
        return json.dumps(fitted, ensure_ascii=False)
    # Retain some substantive evidence for every record; never drop a source.
    low = 100
    if len(encode(low)) > budget:
        # Shorten descriptive metadata only; stored provenance and identifiers
        # remain untouched. Keep every evidence record in the request.
        for row in records:
            for key in ('title', 'source_url', 'section_title', 'html_anchor'):
                if isinstance(row.get(key), str) and len(row[key]) > 80:
                    row[key] = row[key][:80]
                    row['metadata_truncated'] = True
    if len(encode(low)) > budget:
        raise ValueError('Evidence metadata and minimum excerpts exceed the available budget')
    # Search for the largest shared excerpt cap that fits the encoded JSON.
    # Counting raw text alone misses escaping and provenance overhead.
    high = max([low] + [len(row[key]) for row in records for key in TEXT_FIELDS if isinstance(row.get(key),str)])
    while low < high:
        middle = (low + high + 1) // 2
        if len(encode(middle)) <= budget:
            low = middle
        else:
            high = middle - 1
    return encode(low)


def previous_excerpt(previous, budget=2500):
    # Earlier sections provide continuity, but must not crowd out the evidence
    # needed to write the next section.
    text = '\n\n'.join(previous[-3:])
    def encode(cap):
        return json.dumps({'excerpt':text[:cap], 'truncated':len(text)>cap}, ensure_ascii=False, separators=(',', ':'))
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if len(encode(middle)) <= budget:
            low = middle
        else:
            high = middle - 1
    return encode(low)
