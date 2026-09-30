from collections import deque

from encoder import Grounding


def _fk_graph(schema, foreign_keys):
    g = {t: [] for t in schema}
    for ft, fc, tt, tc in foreign_keys:
        if ft in g and tt in g:
            g[ft].append((tt, fc, tc))
            g[tt].append((ft, tc, fc))
    return g


def _shortest_path(g, a, b):
    if a == b:
        return []
    prev = {a: None}
    q = deque([a])
    while q:
        cur = q.popleft()
        if cur == b:
            break
        for nxt, mycol, othercol in g[cur]:
            if nxt not in prev:
                prev[nxt] = (cur, mycol, nxt, othercol)
                q.append(nxt)
    path = []
    node = b
    while prev.get(node):
        edge = prev[node]
        path.append(edge)
        node = edge[0]
    return list(reversed(path))


def _bridge_close(g, tables):
    tables = list(tables)
    all_tables = set(tables)
    all_edges = []
    for i in range(len(tables)):
        for j in range(i + 1, len(tables)):
            path = _shortest_path(g, tables[i], tables[j])
            for edge in path:
                all_tables.add(edge[0])
                all_tables.add(edge[2])
                all_edges.append(edge)
    return all_tables, all_edges


def _default_target(g, schema):
    where_tables = {t for t, c, op, v in g.filters}
    candidates = [t for t in g.tables if t not in where_tables] or list(g.tables)
    target_table = sorted(candidates)[0]
    free_cols = [c for c in schema[target_table] if not (c.endswith("_id") and c != "id")]
    name_col = "name" if "name" in schema[target_table] else (free_cols or schema[target_table])[0]
    return target_table, name_col


def build(g, schema, foreign_keys):
    fk_graph = _fk_graph(schema, foreign_keys)
    all_tables, join_edges = _bridge_close(fk_graph, g.tables)

    if g.aggregation:
        op, t, c = g.aggregation
        select = f"{op}(*)" if t is None else f'{op}("{t}"."{c}")'
    elif g.target:
        select = ", ".join(f'"{t}"."{c}"' for t, c in g.target)
    elif not g.filters and len(g.tables) == 1:
        select = "*"
    else:
        t, c = _default_target(g, schema)
        select = f'"{t}"."{c}"'

    where_parts = []
    for t, c, op, v in g.filters:
        where_parts.append(f'"{t}"."{c}" = \'{v}\'' if op == "=" else f'"{t}"."{c}" {op} {v}')
    where_clause = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""

    ordered = sorted(all_tables)
    from_table = ordered[0]
    join_clause = ""
    joined = {from_table}
    for a, ca, b, cb in join_edges:
        if a in joined and b not in joined:
            join_clause += f' JOIN "{b}" ON "{a}"."{ca}" = "{b}"."{cb}"'
            joined.add(b)
        elif b in joined and a not in joined:
            join_clause += f' JOIN "{a}" ON "{b}"."{cb}" = "{a}"."{ca}"'
            joined.add(a)

    return f'SELECT {select} FROM "{from_table}"{join_clause}{where_clause}'
