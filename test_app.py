"""Tests for the birthday web application."""

import csv
import re
from datetime import date
from html.parser import HTMLParser

import pytest

from app import app, calculate_age, people_with_birthday_today, sort_people, us_date


class OptionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.options = []

    def handle_starttag(self, tag, attrs):
        if tag == "option":
            self.options.append(dict(attrs))


def selected_option_value(page):
    parser = OptionParser()
    parser.feed(page)
    selected_values = [
        option["value"] for option in parser.options if "selected" in option
    ]
    assert len(selected_values) == 1
    return selected_values[0]


def write_store(path, rows):
    with path.open("w", encoding="utf-8", newline="") as data_file:
        writer = csv.writer(data_file, lineterminator="\n")
        writer.writerow(["name", "birthdate"])
        writer.writerows(rows)


def read_store(path):
    with path.open(encoding="utf-8", newline="") as data_file:
        return list(csv.DictReader(data_file))


@pytest.fixture
def files(tmp_path, monkeypatch):
    seed_path = tmp_path / "names.txt"
    data_path = tmp_path / "names.csv"
    seed_path.write_text("  zebra  \nAlice\n\nbob\n", encoding="utf-8")
    monkeypatch.setenv("DATA_FILE", str(data_path))
    monkeypatch.setenv("NAMES_SEED_FILE", str(seed_path))
    return data_path, seed_path


@pytest.fixture
def client(files):
    app.config.update(TESTING=True)
    return app.test_client()


def test_default_page_contains_names_in_file_order(client):
    response = client.get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "zebra" in page
    assert "Alice" in page
    assert "bob" in page
    assert page.index("zebra") < page.index("Alice") < page.index("bob")
    assert "3 names read" in page
    assert "Original file order" in page


def test_alphabetical_sort_is_case_insensitive(client):
    response = client.get("/?sort=alpha")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert page.index("Alice") < page.index("bob") < page.index("zebra")
    assert "Alphabetical order" in page
    assert ">Original</a>" in page
    assert 'aria-current="page">Alphabetical</span>' in page


def test_first_missing_birthday_is_preselected_in_default_order(client, files):
    data_path, _ = files
    write_store(
        data_path,
        [("zebra", "2000-01-01"), ("Alice", ""), ("bob", "")],
    )

    page = client.get("/").get_data(as_text=True)

    assert selected_option_value(page) == "Alice"


def test_preselected_person_follows_active_sort(client, files):
    data_path, _ = files
    write_store(
        data_path,
        [("zebra", ""), ("Alice", "2000-01-01"), ("bob", "")],
    )

    default_page = client.get("/").get_data(as_text=True)
    alpha_page = client.get("/?sort=alpha").get_data(as_text=True)

    assert selected_option_value(default_page) == "zebra"
    assert selected_option_value(alpha_page) == "bob"


def test_first_person_is_preselected_when_all_birthdays_are_known(client, files):
    data_path, _ = files
    write_store(
        data_path,
        [("zebra", "2000-01-01"), ("Alice", "1990-02-02")],
    )

    response = client.get("/")

    assert response.status_code == 200
    assert selected_option_value(response.get_data(as_text=True)) == "zebra"


def test_posting_preselected_birthday_advances_to_next_missing_person(client, files):
    data_path, _ = files
    write_store(
        data_path,
        [("Alice", ""), ("bob", ""), ("zebra", "2000-01-01")],
    )
    initial_page = client.get("/").get_data(as_text=True)
    selected_name = selected_option_value(initial_page)

    response = client.post(
        "/birthday",
        data={"name": selected_name, "birthdate": "1994-06-15"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert selected_option_value(response.get_data(as_text=True)) == "bob"


def test_malformed_data_file_renders_error(client, files):
    data_path, _ = files
    data_path.write_text("wrong,header\nAlice,2000-01-01\n", encoding="utf-8")

    response = client.get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Unable to read birthday data" in page
    assert "0 names read" in page


def test_absent_csv_is_seeded_from_names_file(client, files):
    data_path, _ = files

    assert not data_path.exists()
    response = client.get("/")

    assert response.status_code == 200
    assert data_path.read_text(encoding="utf-8") == (
        "name,birthdate\nzebra,\nAlice,\nbob,\n"
    )


def test_missing_seed_starts_with_empty_store(tmp_path, monkeypatch):
    data_path = tmp_path / "names.csv"
    monkeypatch.setenv("DATA_FILE", str(data_path))
    monkeypatch.setenv("NAMES_SEED_FILE", str(tmp_path / "missing.txt"))
    app.config.update(TESTING=True)

    response = app.test_client().get("/")

    assert response.status_code == 200
    assert data_path.read_text(encoding="utf-8") == "name,birthdate\n"
    assert "0 names read" in response.get_data(as_text=True)


def test_age_sort_is_oldest_to_youngest(client, files):
    data_path, _ = files
    write_store(
        data_path,
        [("Young", "2005-04-12"), ("Old", "1970-11-03"), ("Middle", "1992-01-22")],
    )

    page = client.get("/?sort=age").get_data(as_text=True)

    assert page.index("Old") < page.index("Middle") < page.index("Young")


def test_age_desc_sort_is_youngest_to_oldest(client, files):
    data_path, _ = files
    write_store(
        data_path,
        [("Middle", "1992-01-22"), ("Young", "2005-04-12"), ("Old", "1970-11-03")],
    )

    page = client.get("/?sort=age_desc").get_data(as_text=True)

    assert page.index("Young") < page.index("Middle") < page.index("Old")
    assert "Age (youngest first)" in page
    assert 'aria-current="page">Age: youngest</span>' in page


@pytest.mark.parametrize("sort_mode", ["age", "age_desc"])
def test_age_sorts_break_birthdate_ties_by_case_insensitive_name(sort_mode):
    people = [
        {"name": "Bob", "birthdate": "2000-01-01"},
        {"name": "alice", "birthdate": "2000-01-01"},
    ]

    sorted_people = sort_people(people, sort_mode)

    assert [person["name"] for person in sorted_people] == ["alice", "Bob"]


def test_upcoming_sort_wraps_from_reference_date():
    people = [
        {"name": "January", "birthdate": "2010-01-30"},
        {"name": "September", "birthdate": "1985-09-04"},
    ]

    sorted_people = sort_people(people, "upcoming", today=date(2026, 8, 2))

    assert [person["name"] for person in sorted_people] == ["September", "January"]


def test_upcoming_sort_puts_birthday_today_first():
    people = [
        {"name": "Tomorrow", "birthdate": "1990-08-03"},
        {"name": "Today", "birthdate": "2000-08-02"},
    ]

    sorted_people = sort_people(people, "upcoming", today=date(2026, 8, 2))

    assert [person["name"] for person in sorted_people] == ["Today", "Tomorrow"]


def test_people_with_birthday_today_matches_month_and_day():
    people = [
        {"name": "Today", "birthdate": "2000-08-02"},
        {"name": "Tomorrow", "birthdate": "1990-08-03"},
        {"name": "Unknown", "birthdate": ""},
        {"name": "Also today", "birthdate": "1995-08-02"},
    ]

    assert people_with_birthday_today(people, today=date(2026, 8, 2)) == [
        "Today",
        "Also today",
    ]


def test_people_with_birthday_today_treats_leap_day_as_march_1_in_non_leap_year():
    people = [
        {"name": "Leap day", "birthdate": "2000-02-29"},
        {"name": "March first", "birthdate": "1990-03-01"},
    ]

    assert people_with_birthday_today(people, today=date(2026, 3, 1)) == [
        "Leap day",
        "March first",
    ]


def test_page_includes_today_birthdays_for_auto_confetti(client, files, monkeypatch):
    data_path, _ = files
    write_store(
        data_path,
        [("Alice", "2000-08-02"), ("Bob", "1990-01-01")],
    )
    monkeypatch.setitem(app.config, "TODAY", date(2026, 8, 2))

    page = client.get("/").get_data(as_text=True)

    assert "const todayBirthdays = " in page
    assert '"Alice"' in page
    # Manual confetti control and full-width birthday banner remain available.
    assert 'id="confetti-button"' in page
    assert 'id="birthday-mega-banner"' in page


def test_upcoming_sort_treats_february_29_as_march_1_in_non_leap_year():
    people = [
        {"name": "March second", "birthdate": "1990-03-02"},
        {"name": "Leap day", "birthdate": "2000-02-29"},
    ]

    sorted_people = sort_people(people, "upcoming", today=date(2026, 2, 28))

    assert [person["name"] for person in sorted_people] == ["Leap day", "March second"]


def test_upcoming_sort_puts_unknown_birthdays_last_with_pinned_date():
    people = [
        {"name": "Unknown", "birthdate": ""},
        {"name": "January", "birthdate": "2000-01-01"},
        {"name": "September", "birthdate": "2000-09-01"},
    ]

    sorted_people = sort_people(people, "upcoming", today=date(2026, 8, 2))

    assert [person["name"] for person in sorted_people] == [
        "September",
        "January",
        "Unknown",
    ]


def test_upcoming_sort_breaks_same_day_ties_by_case_insensitive_name():
    people = [
        {"name": "Bob", "birthdate": "1990-09-01"},
        {"name": "alice", "birthdate": "2000-09-01"},
    ]

    sorted_people = sort_people(people, "upcoming", today=date(2026, 8, 2))

    assert [person["name"] for person in sorted_people] == ["alice", "Bob"]


@pytest.mark.parametrize(
    ("sort_mode", "ordered_names"),
    [
        ("age", ["Earlier", "Later", "Unknown"]),
        ("age_desc", ["Later", "Earlier", "Unknown"]),
        ("upcoming", ["Later", "Earlier", "Unknown"]),
    ],
)
def test_unknown_birthdays_are_present_and_last(
    client, files, monkeypatch, sort_mode, ordered_names
):
    data_path, _ = files
    write_store(
        data_path,
        [("Unknown", ""), ("Later", "2000-10-10"), ("Earlier", "1990-02-02")],
    )
    monkeypatch.setitem(app.config, "TODAY", date(2026, 8, 2))

    page = client.get(f"/?sort={sort_mode}").get_data(as_text=True)

    positions = [page.index(name) for name in ordered_names]
    assert positions == sorted(positions)
    assert "1 person has no birthday recorded." in page


def test_post_sets_birthday_redirects_and_preserves_sort(client, files):
    data_path, _ = files
    client.get("/")

    response = client.post(
        "/birthday?sort=age", data={"name": "Alice", "birthdate": "1994-06-15"}
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/?sort=age"
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "1994-06-15" in page
    assert next(row for row in read_store(data_path) if row["name"] == "Alice")[
        "birthdate"
    ] == "1994-06-15"


def test_post_with_empty_date_clears_birthday(client, files):
    data_path, _ = files
    write_store(data_path, [("Alice", "1994-06-15")])

    response = client.post("/birthday", data={"name": "Alice", "birthdate": ""})

    assert response.status_code == 302
    assert read_store(data_path) == [{"name": "Alice", "birthdate": ""}]
    assert "1 person has no birthday recorded." in client.get("/").get_data(as_text=True)


@pytest.mark.parametrize(
    ("form_data", "message"),
    [
        ({"name": "Nobody", "birthdate": "2000-01-01"}, "not in the birthday store"),
        ({"name": "Alice", "birthdate": "not-a-date"}, "YYYY-MM-DD format"),
    ],
)
def test_invalid_posts_show_error_and_do_not_modify_store(
    client, files, form_data, message
):
    data_path, _ = files
    write_store(data_path, [("Alice", "1994-06-15")])
    original_contents = data_path.read_bytes()

    response = client.post("/birthday", data=form_data)

    assert response.status_code == 302
    assert data_path.read_bytes() == original_contents
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert message in page
    assert "1994-06-15" in page


def test_post_person_appends_and_name_appears_on_page(client, files):
    data_path, _ = files
    client.get("/")

    response = client.post("/person", data={"name": "Charlie", "birthdate": ""})

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert read_store(data_path)[-1] == {"name": "Charlie", "birthdate": ""}
    assert "Charlie" in client.get(response.headers["Location"]).get_data(as_text=True)


def test_post_person_with_birthday_stores_and_renders_age(
    client, files, monkeypatch
):
    data_path, _ = files
    monkeypatch.setitem(app.config, "TODAY", date(2026, 8, 2))

    response = client.post(
        "/person", data={"name": "Ada", "birthdate": "1998-04-12"}
    )

    assert response.status_code == 302
    assert read_store(data_path)[-1] == {
        "name": "Ada",
        "birthdate": "1998-04-12",
    }
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "April 12, 1998" in page
    assert 'aria-label="Ada age">28</span>' in page


@pytest.mark.parametrize(
    ("form_data", "message"),
    [
        ({"name": "   ", "birthdate": ""}, "Name is required."),
        ({"name": "BOB", "birthdate": ""}, "already in the list"),
        ({"name": "Charlie", "birthdate": "not-a-date"}, "YYYY-MM-DD format"),
    ],
)
def test_invalid_person_posts_show_error_and_leave_store_byte_identical(
    client, files, form_data, message
):
    data_path, _ = files
    client.get("/")
    original_contents = data_path.read_bytes()

    response = client.post("/person", data=form_data)

    assert response.status_code == 302
    assert data_path.read_bytes() == original_contents
    assert message in client.get(response.headers["Location"]).get_data(as_text=True)


def test_post_person_trims_name_before_storing(client, files):
    data_path, _ = files

    response = client.post(
        "/person", data={"name": "  Charlie  ", "birthdate": ""}
    )

    assert response.status_code == 302
    assert read_store(data_path)[-1]["name"] == "Charlie"


def test_post_person_preserves_active_sort_in_redirect(client):
    response = client.post(
        "/person?sort=age_desc", data={"name": "Charlie", "birthdate": ""}
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/?sort=age_desc"


def test_post_delete_removes_person_and_preserves_sort(client, files):
    data_path, _ = files
    write_store(data_path, [("Alice", "1994-06-15"), ("Bob", "1988-01-02")])

    response = client.post("/delete?sort=alpha", data={"name": "Alice"})

    assert response.status_code == 302
    assert response.headers["Location"] == "/?sort=alpha"
    assert read_store(data_path) == [{"name": "Bob", "birthdate": "1988-01-02"}]
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Alice" not in page
    assert "Bob" in page


def test_post_delete_unknown_name_shows_error_and_leaves_store_byte_identical(
    client, files
):
    data_path, _ = files
    write_store(data_path, [("Alice", "1994-06-15")])
    original_contents = data_path.read_bytes()

    response = client.post("/delete", data={"name": "Nobody"})

    assert response.status_code == 302
    assert data_path.read_bytes() == original_contents
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "not in the birthday store" in page
    assert "Alice" in page


def test_delete_button_is_rendered_for_each_person(client, files):
    data_path, _ = files
    write_store(data_path, [("Alice", ""), ("Bob", "")])

    page = client.get("/").get_data(as_text=True)

    assert 'aria-label="Delete Alice"' in page
    assert 'aria-label="Delete Bob"' in page
    assert 'action="/delete"' in page


def test_delete_confirm_handler_is_a_well_formed_attribute(client, files):
    """The confirm() call must survive HTML attribute parsing.

    tojson escapes < > & and ', but not " -- so inside a double-quoted
    attribute the message's own quote ends the attribute early, the handler
    never compiles, and Delete fires with no confirmation prompt.
    """
    data_path, _ = files
    write_store(data_path, [("Alice", "")])

    page = client.get("/").get_data(as_text=True)

    handler = re.search(r"onsubmit='([^']*)'", page)
    assert handler, "delete form has no single-quoted onsubmit handler"
    assert handler.group(1) == 'return confirm("Remove Alice from the list?");'


def test_delete_confirm_escapes_markup_in_names(client, files):
    data_path, _ = files
    write_store(data_path, [('<script>alert(1)</script>', "")])

    page = client.get("/").get_data(as_text=True)

    assert "<script>alert(1)</script>" not in page
    assert re.search(r"onsubmit='return confirm\(\"[^']*\"\);'", page)


def test_download_returns_csv_attachment_of_store(client, files):
    data_path, _ = files
    write_store(data_path, [("Alice", "1994-06-15"), ("Bob", "")])

    response = client.get("/download")

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    disposition = response.headers["Content-Disposition"]
    assert "attachment" in disposition
    assert "birthdays.csv" in disposition
    body = response.get_data(as_text=True)
    assert body.splitlines() == [
        "name,birthdate",
        "Alice,1994-06-15",
        "Bob,",
    ]


def test_download_link_is_rendered_on_page(client):
    page = client.get("/").get_data(as_text=True)

    assert 'href="/download"' in page
    assert "Download CSV" in page


def test_download_with_malformed_store_redirects_with_error(client, files):
    data_path, _ = files
    data_path.write_text("not,a,valid,header\n", encoding="utf-8")

    response = client.get("/download")

    assert response.status_code == 302
    from urllib.parse import unquote_plus

    location = unquote_plus(response.headers["Location"])
    assert location.startswith("/?error=")
    assert "Unable to download birthday data" in location
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    # Index re-reads the same broken store and surfaces a read error instead.
    assert "Unable to read birthday data" in page


def test_birthdates_display_in_us_long_format(client, files):
    data_path, _ = files
    write_store(data_path, [("Ada", "1998-04-12"), ("Grace", "1995-11-03")])

    page = client.get("/").get_data(as_text=True)

    assert "April 12, 1998" in page
    assert "November 3, 1995" in page  # day is not zero-padded
    assert ">1998-04-12<" not in page  # ISO is not rendered as visible text
    assert 'datetime="1998-04-12"' in page  # ...but stays in the machine-readable attribute


def test_us_date_filter_handles_unknown_birthdate():
    assert us_date("") == ""


def test_calculate_age_for_passed_and_upcoming_birthdays():
    today = date(2026, 8, 2)

    assert calculate_age("1998-04-12", today=today) == 28
    assert calculate_age("1998-11-03", today=today) == 27


def test_calculate_age_treats_unknown_and_future_birthdates_as_unknown():
    today = date(2026, 8, 2)

    assert calculate_age("", today=today) is None
    assert calculate_age("2030-01-01", today=today) is None


def test_age_column_renders_headers_values_and_unknown_placeholders(
    client, files, monkeypatch
):
    data_path, _ = files
    write_store(
        data_path,
        [
            ("Known", "1998-04-12"),
            ("Unknown", ""),
            ("Future", "2030-01-01"),
        ],
    )
    monkeypatch.setitem(app.config, "TODAY", date(2026, 8, 2))

    page = client.get("/").get_data(as_text=True)

    assert "<span>Name</span>" in page
    assert "<span>Birthday</span>" in page
    assert '<span class="age">Age</span>' in page
    assert 'aria-label="Known age">28</span>' in page
    assert page.count('aria-label="Age unknown">—</span>') == 2
