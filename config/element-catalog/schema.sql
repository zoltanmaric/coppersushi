PRAGMA foreign_keys = ON;
CREATE TABLE sites (
    site_id TEXT PRIMARY KEY NOT NULL CHECK(length(trim(site_id)) > 0),
    display_name TEXT NOT NULL CHECK(length(trim(display_name)) > 0),
    longitude REAL NOT NULL CHECK(longitude BETWEEN -180 AND 180),
    latitude REAL NOT NULL CHECK(latitude BETWEEN -90 AND 90),
    evidence TEXT NOT NULL CHECK(length(trim(evidence)) > 0)
) STRICT;
CREATE TABLE site_names (
    source TEXT NOT NULL CHECK(length(trim(source)) > 0),
    published_name TEXT NOT NULL CHECK(length(trim(published_name)) > 0),
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    PRIMARY KEY(source, published_name, site_id)
) STRICT;
CREATE TABLE elements (
    element_id TEXT PRIMARY KEY NOT NULL CHECK(length(trim(element_id)) > 0),
    source TEXT NOT NULL CHECK(length(trim(source)) > 0),
    tso TEXT NOT NULL CHECK(length(trim(tso)) > 0),
    eic TEXT NOT NULL CHECK(length(trim(eic)) > 0),
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    element_type TEXT,
    direct_orientation TEXT NOT NULL CHECK(direct_orientation IN ('a_to_b','b_to_a','unknown')),
    orientation_basis TEXT NOT NULL CHECK(orientation_basis IN ('published','inferred','unknown')),
    orientation_evidence TEXT NOT NULL CHECK(length(trim(orientation_evidence)) > 0),
    CHECK((direct_orientation='unknown') = (orientation_basis='unknown')),
    UNIQUE(source, tso, eic, name)
) STRICT;
CREATE TABLE element_endpoints (
    element_id TEXT NOT NULL REFERENCES elements(element_id),
    terminal TEXT NOT NULL CHECK(terminal IN ('a', 'b')),
    published_name TEXT CHECK(published_name IS NULL OR length(trim(published_name)) > 0),
    site_id TEXT REFERENCES sites(site_id),
    status TEXT NOT NULL CHECK(status IN ('resolved', 'missing', 'unresolved', 'ambiguous', 'conflict')),
    evidence TEXT NOT NULL CHECK(length(trim(evidence)) > 0),
    assignment_basis TEXT NOT NULL CHECK(assignment_basis IN ('published','inferred','unknown')),
    PRIMARY KEY(element_id, terminal),
    CHECK((status='resolved') = (assignment_basis<>'unknown')),
    CHECK((status = 'resolved' AND site_id IS NOT NULL)
       OR (status <> 'resolved' AND site_id IS NULL)),
    CHECK(assignment_basis <> 'published' OR published_name IS NOT NULL),
    CHECK(status <> 'missing' OR published_name IS NULL)
) STRICT;
