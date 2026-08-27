from src.services.experience_estimation import estimate_years_experience, merge_intervals, parse_resume_date


def test_parse_resume_date_formats():
    assert parse_resume_date("2020-05-01").isoformat() == "2020-05-01"
    assert parse_resume_date("2020-05").isoformat() == "2020-05-01"
    assert parse_resume_date("2020").isoformat() == "2020-01-01"


def test_parse_resume_date_present_tokens():
    from datetime import date

    assert parse_resume_date("Present") == date.today()
    assert parse_resume_date("current") == date.today()


def test_parse_resume_date_unparseable_returns_none():
    assert parse_resume_date("sometime last year") is None
    assert parse_resume_date(None) is None


def test_merge_intervals_combines_overlaps():
    from datetime import date

    intervals = [(date(2019, 1, 1), date(2021, 1, 1)), (date(2020, 1, 1), date(2022, 1, 1))]
    merged = merge_intervals(intervals)

    assert merged == [(date(2019, 1, 1), date(2022, 1, 1))]


def test_merge_intervals_keeps_disjoint_ranges_separate():
    from datetime import date

    intervals = [(date(2015, 1, 1), date(2016, 1, 1)), (date(2019, 1, 1), date(2020, 1, 1))]
    merged = merge_intervals(intervals)

    assert len(merged) == 2


def test_estimate_years_experience_non_overlapping():
    years, warnings = estimate_years_experience([("2016-06", "2019-01"), ("2019-01", "2022-06")])

    assert years == 6.0
    assert warnings == []


def test_estimate_years_experience_overlapping_does_not_double_count():
    years, warnings = estimate_years_experience([("2018-01", "2022-01"), ("2019-01", "2021-01")])

    assert years == 4.0


def test_estimate_years_experience_unparseable_dates_are_excluded_with_warning():
    years, warnings = estimate_years_experience([("not a date", "also not a date"), ("2020-01", "2021-01")])

    assert years == 1.0
    assert any("could not be parsed" in w for w in warnings)


def test_estimate_years_experience_returns_none_when_nothing_parseable():
    years, warnings = estimate_years_experience([("not a date", "also not a date")])

    assert years is None
    assert any("unknown" in w for w in warnings)


def test_estimate_years_experience_empty_input():
    years, warnings = estimate_years_experience([])

    assert years is None


def test_estimate_years_experience_ignores_end_before_start():
    years, warnings = estimate_years_experience([("2022-01", "2020-01")])

    assert years is None
    assert any("end date before start date" in w for w in warnings)
