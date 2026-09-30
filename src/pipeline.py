import decoder
import enc_rule as active_encoder

def generate(question, schema, foreign_keys, value_lookup, force_tables=None):
    grounding = active_encoder.ground(question, schema, value_lookup, force_tables)
    if grounding is None:
        return None
    return decoder.build(grounding, schema, foreign_keys)
