from src.services.normalization import (
    normalize_company,
    normalize_location,
    normalize_skill,
    normalize_title,
    normalize_url,
    normalize_whitespace,
)


def test_title_variants_converge():
    assert normalize_title("Sr. AI Engineer") == "senior ai engineer"
    assert normalize_title("Senior AI Engineer") == "senior ai engineer"
    assert normalize_title("SENIOR AI ENGINEER") == "senior ai engineer"


def test_title_normalization_preserves_original_value_elsewhere():
    original = "Sr. AI Engineer"
    normalized = normalize_title(original)
    assert original == "Sr. AI Engineer"
    assert normalized != original


def test_company_suffix_stripped_for_comparison():
    assert normalize_company("Acme Inc.") == normalize_company("Acme")
    assert normalize_company("Acme, LLC") == normalize_company("acme")


def test_company_name_not_over_stripped():
    assert normalize_company("Company Solutions Inc.") == "company solutions"


def test_location_normalization():
    assert normalize_location("New York,NY") == "new york, ny"
    assert normalize_location("  New York, NY  ") == "new york, ny"


def test_skill_alias_map():
    assert normalize_skill("JS") == "JavaScript"
    assert normalize_skill("TS") == "TypeScript"
    assert normalize_skill("Postgres") == "PostgreSQL"
    assert normalize_skill("K8s") == "Kubernetes"
    assert normalize_skill("ML") == "Machine Learning"


def test_skill_alias_map_is_case_insensitive():
    assert normalize_skill("js") == "JavaScript"
    assert normalize_skill("k8S") == "Kubernetes"


def test_unknown_skill_is_left_alone_but_whitespace_normalized():
    assert normalize_skill("  Rust  ") == "Rust"


def test_url_canonicalization_strips_tracking_params():
    a = normalize_url("https://Example.com/jobs/123/?utm_source=linkedin&ref=abc")
    b = normalize_url("https://example.com/jobs/123")
    assert a == b


def test_url_canonicalization_keeps_meaningful_query_params():
    a = normalize_url("https://example.com/jobs?id=123")
    b = normalize_url("https://example.com/jobs?id=999")
    assert a != b


def test_whitespace_collapses():
    assert normalize_whitespace("  a   b\n\tc  ") == "a b c"
