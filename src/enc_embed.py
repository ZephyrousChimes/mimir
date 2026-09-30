from sentence_transformers import SentenceTransformer
import numpy as np
import encoder

_model = None
def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model

def cos(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def score_tables(question, schema):
    model = get_model()
    table_texts = {t: t + " " + " ".join(cols) for t, cols in schema.items()}
    
    tables = list(table_texts.keys())
    texts = [table_texts[t] for t in tables]

    q_vec = model.encode(question)
    t_vecs = model.encode(texts)

    scores = {}
    for t, v in zip(tables, t_vecs):
        scores[t] = cos(q_vec, v)
    return scores

THRESHOLD = 0.3

def link_tables(question, schema):
    scores = score_tables(question, schema)
    return {t for t, s in scores.items() if s > THRESHOLD}

def ground(question, schema, value_lookup, force_tables=None):
    return encoder.ground(question, schema, value_lookup, link_tables, force_tables)

if __name__ == "__main__":
    import db_utils
    schema = db_utils.tables_and_columns()
    q = "Which staff work in the Engineering department?"
    for t, s in sorted(score_tables(q, schema).items(), key=lambda x: -x[1]):
        print(t, round(s, 3))
