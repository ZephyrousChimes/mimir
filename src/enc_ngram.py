import re
import encoder

def ngrams(words, n):
    return [" ".join(words[i:i+n]) for i in range(len(words)-n+1)]

def score_tables(question, schema):
    qwords = re.findall(r"[a-z]+", question.lower())
    qgrams = set()
    for n in (1,2,3):
        qgrams |= set(ngrams(qwords, n))

    scores = {}
    for table, cols in schema.items():
        doc_words = re.findall(r"[a-z]+", (table + " " + " ".join(cols)).lower())
        docgrams = set()
        for n in (1,2,3):
            docgrams |= set(ngrams(doc_words, n))
        scores[table] = len(qgrams & docgrams)
    return scores

def link_tables(question, schema):
    scores = score_tables(question, schema)
    return {t for t, s in scores.items() if s > 0}

def ground(question, schema, value_lookup, force_tables=None):
    return encoder.ground(question, schema, value_lookup, link_tables, force_tables)

if __name__ == "__main__":
    import db_utils
    schema = db_utils.tables_and_columns()
    q = "Which employees work in the Engineering department?"
    print(score_tables(q, schema))
