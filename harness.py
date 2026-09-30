import sys, csv, json, sqlite3
sys.path.insert(0, "src")
import enc_rule, enc_ngram, enc_embed, decoder, db_utils

ENCODERS = {"rule": enc_rule, "ngram": enc_ngram, "embed": enc_embed}
enc = ENCODERS[sys.argv[1] if len(sys.argv) > 1 else "rule"]

schema = db_utils.tables_and_columns()
fks = db_utils.foreign_keys()
lookup = db_utils.value_lookup_for(db_utils.DB_PATH)
questions = json.load(open("data/questions.json"))

def run(sql):
    if sql is None:
        return None
    try:
        conn = sqlite3.connect(f"file:{db_utils.DB_PATH}?mode=ro", uri=True)
        rows = conn.execute(sql).fetchall()
        conn.close()
        return rows
    except Exception:
        return None

rows_out = []
correct = 0
for q in questions:
    g = enc.ground(q["question"], schema, lookup)
    pred_sql = decoder.build(g, schema, fks) if g else None
    gold_rows = run(q["gold_sql"])
    pred_rows = run(pred_sql)
    ok = pred_rows is not None and sorted(map(str, gold_rows)) == sorted(map(str, pred_rows))
    correct += ok
    rows_out.append([q["id"], q["question"], q["gold_sql"], pred_sql, ok])

with open("results.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "question", "gold_sql", "pred_sql", "correct"])
    w.writerows(rows_out)

print(f"{correct}/{len(questions)} = {correct/len(questions):.1%}")
