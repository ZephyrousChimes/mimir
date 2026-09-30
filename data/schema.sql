-- Small, hand-owned schema. Every design choice below exists to make a
-- specific, predicted failure mode reproducible on demand:
--   * department.name contains the literal value 'What' -- a value/lexical
--     collision trap (the value collides with a common interrogative word).
--   * assignment is a bridge table between employee and project that no
--     question below ever names lexically -- an unnamed-join-table trap,
--     the same failure mode schema_link.py's docstring describes for
--     RESDSQL-style linkers (e.g. Spider's "students who have pets").

CREATE TABLE department (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    budget INTEGER NOT NULL
);

CREATE TABLE employee (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    dept_id INTEGER NOT NULL REFERENCES department(id),
    salary INTEGER NOT NULL
);

-- No direct FK to employee on purpose: employee <-> project is reachable
-- *only* through the assignment bridge below. A second, shorter path (an
-- earlier version had lead_emp_id here) would let FK-graph shortest-path
-- pick the structurally shortest edge over the semantically correct one --
-- a real, separate join-path-ambiguity problem, not the one this schema
-- is built to isolate.
CREATE TABLE project (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

-- Bridge table: many-to-many employee <-> project. No column here shares a
-- word with any question in data/questions.json, so pure lexical-overlap
-- schema linking (stage 2) has zero evidence to pull this table in.
CREATE TABLE assignment (
    emp_id INTEGER NOT NULL REFERENCES employee(id),
    project_id INTEGER NOT NULL REFERENCES project(id),
    hours INTEGER NOT NULL
);

INSERT INTO department (id, name, budget) VALUES
    (1, 'Sales', 500000),
    (2, 'Engineering', 900000),
    (3, 'What', 300000);          -- the collision trap

INSERT INTO employee (id, name, dept_id, salary) VALUES
    (1, 'Alice', 2, 95000),
    (2, 'Bob', 1, 62000),
    (3, 'Carol', 2, 88000),
    (4, 'Dave', 3, 71000),
    (5, 'Erin', 1, 58000);

INSERT INTO project (id, name) VALUES
    (1, 'Website Redesign'),
    (2, 'Q3 Roadmap'),
    (3, 'Vendor Audit');

INSERT INTO assignment (emp_id, project_id, hours) VALUES
    (1, 1, 40),
    (3, 1, 12),
    (1, 2, 8),
    (2, 3, 20),
    (4, 3, 5);
