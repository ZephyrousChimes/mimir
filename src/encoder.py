import re
from dataclasses import dataclass, field

_STOP = {"the", "a", "an", "of", "in", "is", "are", "was", "were", "for", "to", "and", "or",
         "list", "show", "all", "each", "with", "that", "have", "has", "on"}
_CMP = [(re.compile(r"\b(above|greater than|more than|over)\b"), ">"),
        (re.compile(r"\b(below|less than|under)\b"), "<")]


def _stem(w):
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def _words(s):
    return {_stem(w) for w in re.findall(r"[a-z]+", s.lower()) if w not in _STOP and len(w) > 1}


def _text_columns(schema, table):
    return [c for c in schema[table] if c != "id" and not c.endswith("_id")]


def _value_grounded(schema, question, value_lookup):
    raw = [t for t in re.findall(r"[A-Za-z0-9]+", question) if t.lower() not in _STOP]
    hits = []
    matched_spans = set()
    for n in (3, 2, 1):
        for i in range(len(raw) - n + 1):
            if any(i < e and s < i + n for s, e in matched_spans):
                continue
            phrase = " ".join(raw[i:i + n]).lower()
            if len(phrase) < 2:
                continue
            phrase_hits = []
            for table in schema:
                for col in _text_columns(schema, table):
                    vmap = value_lookup(table, col)
                    if phrase in vmap:
                        phrase_hits.append((table, col, vmap[phrase]))
            if len(phrase_hits) == 1:
                hits.append(phrase_hits[0])
                matched_spans.add((i, i + n))
    return hits


@dataclass
class Grounding:
    tables: set
    target: list = field(default_factory=list)
    filters: list = field(default_factory=list)
    aggregation: tuple = None


def ground(question, schema, value_lookup, link_tables, force_tables=None):
    q_words = _words(question)
    name_linked = link_tables(question, schema) | (force_tables or set())

    cmp_col = None
    cmp_filter = None
    for pat, op in _CMP:
        if pat.search(question.lower()):
            num = re.search(r"-?\d+(\.\d+)?", question)
            for t in name_linked:
                for c in schema[t]:
                    if c.lower() not in ("id",) and not c.lower().endswith("_id") and _stem(c.lower()) in q_words:
                        cmp_col = (t, c)
            if num and cmp_col:
                cmp_filter = (cmp_col[0], cmp_col[1], op, num.group())
            break

    value_hits = _value_grounded(schema, question, value_lookup)
    value_linked = {h[0] for h in value_hits}
    tables = name_linked | value_linked
    if not tables:
        return None

    eq_cols = {(t, c) for t, c, v in value_hits}
    filters = [(t, c, "=", v) for t, c, v in value_hits]
    if cmp_filter:
        filters.append(cmp_filter)

    def is_free(t, c):
        cl = c.lower()
        return not (cl.endswith("_id") and cl != "id") and (t, c) not in eq_cols and cmp_col != (t, c)

    aggregation = None
    if "how many" in question.lower() or re.search(r"\bcount\b", question.lower()):
        agg_col = None
        for t in tables:
            for c in schema[t]:
                if is_free(t, c) and _stem(c.lower()) in q_words:
                    agg_col = (t, c)
        aggregation = ("COUNT", agg_col[0], agg_col[1]) if agg_col else ("COUNT", None, None)

    target = []
    if aggregation is None:
        named = []
        for t in tables:
            for c in schema[t]:
                if is_free(t, c) and _stem(c.lower()) in q_words:
                    named.append((t, c))
        if named:
            target = named
        else:
            where_tables = {h[0] for h in value_hits}
            candidates = [t for t in tables if t not in where_tables] or list(tables)
            best_table, best_col, best_score = None, None, 0
            for t in sorted(candidates):
                table_stem = _stem(t)
                for c in schema[t]:
                    if not is_free(t, c):
                        continue
                    col_words = {_stem(w) for w in re.findall(r"[a-z]+", c.lower())} - {table_stem}
                    score = len(col_words & q_words)
                    if score > best_score:
                        best_table, best_col, best_score = t, c, score
            if best_table:
                target = [(best_table, best_col)]

    return Grounding(tables=tables, target=target, filters=filters, aggregation=aggregation)
