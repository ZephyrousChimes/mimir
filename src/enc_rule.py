import re
import encoder

def col_words(c, table_stems):
    ws = {encoder._stem(w) for w in c.split("_") if w}

    return ws - {"id"} - table_stems

def score_tables(question, schema):
    qwords = encoder._words(question)
    table_stems = {encoder._stem(t) for t in schema}
    scores = {}

    # 
    for table, cols in schema.items():
        if encoder._stem(table) in qwords:
            scores[table] = 1
            continue

        hit = any(col_words(c, table_stems) & qwords for c in cols)
        scores[table] = 1 if hit else 0

    return scores

def link_tables(question, schema):
    scores = score_tables(question, schema)

    return {t for t, s in scores.items() if s > 0}

def ground(question, schema, value_lookup, force_tables=None):

    return encoder.ground(
        question, schema, 
        value_lookup, link_tables, 
        force_tables
    )

if __name__ == "__main__":
    import db_utils
    schema = db_utils.tables_and_columns()

    q = "Which employees work in the Engineering department?"

    print(score_tables(q, schema))
