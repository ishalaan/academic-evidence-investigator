"""Targeted conservative checks, not a semantic faithfulness guarantee."""
import re
from package.services.references import normalise_source_tokens


def _tokens(text):
    return set(re.findall(r'[a-z]{3,}', re.sub(r'\[[^]]*\]|\([^)]*\d{4}[^)]*\)', '', text.lower())))


def repeats_summary(findings, previous):
    old = [s for p in previous for s in re.split(r'(?<=[.!?])\s+', p) if len(_tokens(s)) >= 12]
    for sentence in re.split(r'(?<=[.!?])\s+', findings):
        terms = _tokens(sentence)
        if len(terms) < 12:
            continue
        for earlier in old:
            other = _tokens(earlier)
            if len(terms & other) / max(1, len(terms | other)) >= .72:
                return True
    return False


def grounding_issue(text, context):
    """Check claims against their cited selected passages, not unselected paper text."""
    import json
    try:
        rows = json.loads(context)
    except (ValueError, TypeError):
        return None
    if not isinstance(rows, list):
        return None
    # Keep passages grouped by citation ID. Pooling all paper text would let a
    # claim borrow a sample size or result from an unrelated source.
    sources = {}
    for row in rows:
        key = row.get('source_id') or row.get('id')
        if key:
            sources.setdefault(key, []).append(row.get('text') or row.get('abstract') or row.get('abstract_excerpt') or '')
    text = normalise_source_tokens(text)
    for paragraph in text.split('\n\n'):
        for sentence in re.split(r'(?<=[.!?])\s+', paragraph):
            ids = re.findall(r'\[(S\d+)\]', sentence)
            if not ids and re.search(r'\b\d[\d,]*\s+(?:students|participants|respondents)|\b(?:systematic review|mixed.methods|regression analysis)\b', sentence, re.I):
                return 'missing_claim_citation'
            evidence = ' '.join(t for sid in ids for t in sources.get(sid, [])).lower()
            claim = sentence.lower()
            statistics = re.findall(r'\b(r|p|beta|β)\s*([=<>≤≥])\s*(-?(?:\d+(?:\.\d+)?|\.\d+))', claim)
            if statistics:
                def stats(value):
                    return {(label, op, float(number)) for label, op, number in re.findall(r'\b(r|p|beta|β)\s*([=<>≤≥])\s*(-?(?:\d+(?:\.\d+)?|\.\d+))', value.lower())}
                if not ids or any(not stats(sentence).issubset(stats(' '.join(sources.get(sid, [])))) for sid in ids):
                    return 'unsupported_statistic'
            for pattern, reason in [
                (r'\b(?:analysis|study|research) (?:was |is |has been )?truncated\b', 'truncation_as_study_limitation'),
                (r'\bsmall samples?\b', 'unsupported_sample_limitation'),
                (r'\b(?:negative effects?|minimal gains?)\b', 'unsupported_outcome'),
            ]:
                if re.search(pattern, claim) and not re.search(pattern, evidence):
                    return reason
            if not evidence:
                continue
            claim = sentence.lower()
            # A number mentioned elsewhere in the evidence set is not enough;
            # each attached citation must support the stated sample size.
            for count in re.findall(r'\b(\d[\d,]*)\s+(?:students|participants|respondents)\b', claim):
                number = count.replace(',', '')
                if not all(re.search(r'(?<!\d)' + re.escape(number) + r'(?!\d)', ' '.join(sources.get(sid, [])).replace(',', '')) for sid in ids):
                    return 'unsupported_sample_size'
            for design, pattern in [('systematic review', r'systematic (?:literature )?review'), ('mixed-methods', r'mixed[\s\-‐-—]+methods?'), ('regression analysis', r'regression')]:
                supports = [bool(re.search(pattern, ' '.join(sources.get(sid, [])).lower())) for sid in ids]
                universal = bool(re.search(r'\b(?:both|all|each|every)\b', claim))
                if re.search(pattern, claim) and not (all(supports) if universal else any(supports)):
                    return 'unsupported_study_design'
            qualified = bool(re.search(r'\b(may|might|could|can|potential|expected|proposed|suggests?|reported|reports?|associated|correlat\w*|recommend\w*|should)\b', claim))
            empirical = bool(re.search(r'results (?:revealed|showed)|randomi[sz]ed|p\s*[<=]\s*0\.|β\s*=', evidence))
            if 'expected learning benefit' in evidence and not empirical:
                if re.search(r'\b(demonstrated|proven|established)\b', claim) or (not qualified and re.search(r'\b(enhances?|improves?|boosts?)\b', claim)):
                    return 'expected_benefit_as_result'
            if not qualified and re.search(r'\b(causes?|leads? to|results? in|improves?|enhances?)\b', claim):
                if re.search(r'correlat|questionnaire|self.report|perceived', evidence) and not re.search(r'randomi[sz]ed|controlled experiment', evidence):
                    return 'observational_as_causal'
            if re.search(r'contingent on|depends? on|dependent on', claim):
                for condition in ('faculty training', 'institutional support'):
                    if condition in claim and condition not in evidence:
                        return 'unsupported_condition'
    return None
