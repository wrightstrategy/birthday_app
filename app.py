#!/usr/bin/env python3
"""Small web interface for viewing names and editing their birthdays."""

from __future__ import annotations

import calendar
import csv
import os
import re
import tempfile
from datetime import date
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for


app = Flask(__name__)

SORT_LABELS = {
    "original": "Original file order",
    "alpha": "Alphabetical order",
    "age": "Age (oldest first)",
    "age_desc": "Age (youngest first)",
    "upcoming": "Upcoming birthdays (next first)",
}


def read_names(path: str | os.PathLike[str]) -> list[str]:
    """Read non-blank, whitespace-trimmed names from *path*."""
    with open(path, encoding="utf-8") as names_file:
        return [line.strip() for line in names_file if line.strip()]


@app.template_filter("us_date")
def us_date(value: str) -> str:
    """Render a stored ISO birthdate in US long form, e.g. "April 12, 1998"."""
    parsed = parse_birthdate(value)
    if parsed is None:
        return ""
    return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"


def parse_birthdate(value: str) -> date | None:
    """Parse a stored or submitted ISO birthdate; an empty value is unknown."""
    if value == "":
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Birthdate must use YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Birthdate must be a valid calendar date.") from exc


def write_people(path: str | os.PathLike[str], people: list[dict[str, str]]) -> None:
    """Atomically replace *path* with people in name/birthdate CSV format."""
    data_path = Path(path)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=data_path.parent,
            prefix=f".{data_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            writer = csv.DictWriter(
                temporary_file, fieldnames=["name", "birthdate"], lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(people)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, data_path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def seed_data_file(
    data_path: str | os.PathLike[str], seed_path: str | os.PathLike[str]
) -> None:
    """Create a missing CSV store from a plain-text seed file, if available."""
    data_path = Path(data_path)
    if data_path.exists():
        return

    try:
        names = read_names(seed_path)
    except FileNotFoundError:
        names = []

    write_people(data_path, [{"name": name, "birthdate": ""} for name in names])


def read_people(path: str | os.PathLike[str]) -> list[dict[str, str]]:
    """Read and validate people from the app's CSV store."""
    people: list[dict[str, str]] = []
    with open(path, encoding="utf-8", newline="") as data_file:
        reader = csv.reader(data_file)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("Data file is empty; expected a name,birthdate header.") from exc
        if header != ["name", "birthdate"]:
            raise ValueError("Data file must have a name,birthdate header.")

        for row_number, row in enumerate(reader, start=2):
            if not row or all(not value.strip() for value in row):
                continue
            if len(row) != 2:
                raise ValueError(f"Data file row {row_number} must have two columns.")
            name, birthdate = (value.strip() for value in row)
            if not name:
                raise ValueError(f"Data file row {row_number} has no name.")
            try:
                parse_birthdate(birthdate)
            except ValueError as exc:
                raise ValueError(f"Data file row {row_number}: {exc}") from exc
            people.append({"name": name, "birthdate": birthdate})
    return people


def birthday_in_year(birthdate: date, year: int) -> date:
    """Return the observed birthday in *year*, moving Feb 29 to Mar 1 if needed."""
    if birthdate.month == 2 and birthdate.day == 29 and not calendar.isleap(year):
        return date(year, 3, 1)
    return date(year, birthdate.month, birthdate.day)


def days_until_birthday(birthdate: date, today: date) -> int:
    """Return whole days from *today* to the next observed birthday."""
    next_birthday = birthday_in_year(birthdate, today.year)
    if next_birthday < today:
        next_birthday = birthday_in_year(birthdate, today.year + 1)
    return (next_birthday - today).days


def calculate_age(value: str, today: date | None = None) -> int | None:
    """Return completed years on *today*, or None for unknown/future dates."""
    today = today or date.today()
    birthdate = parse_birthdate(value)
    if birthdate is None or birthdate > today:
        return None
    birthday_this_year = birthday_in_year(birthdate, today.year)
    return today.year - birthdate.year - (today < birthday_this_year)


def add_ages(
    people: list[dict[str, str]], today: date | None = None
) -> list[dict[str, str | int | None]]:
    """Return display copies of *people* with age derived for *today*."""
    today = today or date.today()
    return [
        {**person, "age": calculate_age(person["birthdate"], today)}
        for person in people
    ]


def sort_people(
    people: list[dict[str, str]], sort_mode: str, today: date | None = None
) -> list[dict[str, str]]:
    """Return people in the requested deterministic order."""
    if sort_mode == "alpha":
        return sorted(people, key=lambda person: person["name"].casefold())
    if sort_mode in {"age", "age_desc"}:
        youngest_first = sort_mode == "age_desc"

        def age_key(person: dict[str, str]) -> tuple[bool, int, str, str]:
            birthdate = parse_birthdate(person["birthdate"])
            birthdate_order = birthdate.toordinal() if birthdate else 0
            if youngest_first:
                birthdate_order = -birthdate_order
            return (
                birthdate is None,
                birthdate_order,
                person["name"].casefold(),
                person["name"],
            )

        return sorted(people, key=age_key)
    if sort_mode == "upcoming":
        today = today or date.today()

        def upcoming_key(person: dict[str, str]) -> tuple[bool, int, str, str, str]:
            birthdate = parse_birthdate(person["birthdate"])
            return (
                birthdate is None,
                days_until_birthday(birthdate, today) if birthdate else 0,
                person["name"].casefold(),
                person["name"],
                person["birthdate"],
            )

        return sorted(
            people,
            key=upcoming_key,
        )
    return list(people)


def update_birthday(
    path: str | os.PathLike[str], people: list[dict[str, str]], name: str, birthdate: str
) -> None:
    """Set or clear a person's birthday and atomically persist the store."""
    if name not in {person["name"] for person in people}:
        raise ValueError("That name is not in the birthday store.")
    parse_birthdate(birthdate)

    updated_people = [
        {**person, "birthdate": birthdate if person["name"] == name else person["birthdate"]}
        for person in people
    ]
    write_people(path, updated_people)


def add_person(
    path: str | os.PathLike[str],
    people: list[dict[str, str]],
    name: str,
    birthdate: str,
) -> None:
    """Validate and append a person, then atomically persist the store."""
    name = name.strip()
    if not name:
        raise ValueError("Name is required.")
    if name.casefold() in {person["name"].casefold() for person in people}:
        raise ValueError("That name is already in the list.")
    parse_birthdate(birthdate)

    write_people(path, [*people, {"name": name, "birthdate": birthdate}])


def delete_person(
    path: str | os.PathLike[str], people: list[dict[str, str]], name: str
) -> None:
    """Remove a person by exact name and atomically persist the store."""
    if name not in {person["name"] for person in people}:
        raise ValueError("That name is not in the birthday store.")

    write_people(path, [person for person in people if person["name"] != name])


def get_paths() -> tuple[Path, Path]:
    """Resolve the writable store and read-only seed paths from the environment."""
    return (
        Path(os.environ.get("DATA_FILE", "names.csv")),
        Path(os.environ.get("NAMES_SEED_FILE", "names.txt")),
    )


def get_sort_mode(value: str | None) -> str:
    """Normalize an unsupported or missing sort query to original order."""
    return value if value in SORT_LABELS else "original"


@app.route("/")
def index():
    """Display people in original, alphabetical, age, or calendar order."""
    data_path, seed_path = get_paths()
    sort_mode = get_sort_mode(request.args.get("sort"))
    error = request.args.get("error")

    try:
        seed_data_file(data_path, seed_path)
        people = read_people(data_path)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        people = []
        error = f"Unable to read birthday data: {exc}"

    today = app.config.get("TODAY") or date.today()
    people = sort_people(people, sort_mode, today=today)
    unknown_count = sum(not person["birthdate"] for person in people)
    selected_name = next(
        (person["name"] for person in people if not person["birthdate"]),
        people[0]["name"] if people else None,
    )

    return render_template(
        "index.html",
        people=add_ages(people, today=today),
        error=error,
        order_label=SORT_LABELS[sort_mode],
        sort_mode=sort_mode,
        unknown_count=unknown_count,
        selected_name=selected_name,
    )


@app.post("/birthday")
def birthday():
    """Validate and persist a birthday, then redirect to the active view."""
    data_path, seed_path = get_paths()
    sort_mode = get_sort_mode(request.args.get("sort"))
    name = request.form.get("name", "")
    birthdate = request.form.get("birthdate", "")

    try:
        seed_data_file(data_path, seed_path)
        people = read_people(data_path)
        update_birthday(data_path, people, name, birthdate)
        error = None
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        error = str(exc)

    redirect_args = {"sort": sort_mode} if sort_mode != "original" else {}
    if error:
        redirect_args["error"] = error
    return redirect(url_for("index", **redirect_args))


@app.post("/person")
def person():
    """Validate and append a person, then redirect to the active view."""
    data_path, seed_path = get_paths()
    sort_mode = get_sort_mode(request.args.get("sort"))
    name = request.form.get("name", "")
    birthdate = request.form.get("birthdate", "")

    try:
        seed_data_file(data_path, seed_path)
        people = read_people(data_path)
        add_person(data_path, people, name, birthdate)
        error = None
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        error = str(exc)

    redirect_args = {"sort": sort_mode} if sort_mode != "original" else {}
    if error:
        redirect_args["error"] = error
    return redirect(url_for("index", **redirect_args))


@app.post("/delete")
def delete():
    """Remove a person from the store, then redirect to the active view."""
    data_path, seed_path = get_paths()
    sort_mode = get_sort_mode(request.args.get("sort"))
    name = request.form.get("name", "")

    try:
        seed_data_file(data_path, seed_path)
        people = read_people(data_path)
        delete_person(data_path, people, name)
        error = None
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        error = str(exc)

    redirect_args = {"sort": sort_mode} if sort_mode != "original" else {}
    if error:
        redirect_args["error"] = error
    return redirect(url_for("index", **redirect_args))


if __name__ == "__main__":
    data_file, seed_file = get_paths()
    try:
        seed_data_file(data_file, seed_file)
    except (OSError, UnicodeError):
        pass
    app.run(debug=True)
