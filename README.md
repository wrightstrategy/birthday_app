# birthday_app

A small Flask app for keeping a list of people and their birthdays, with sorting
by name, age, and whose birthday is coming up next.

## Getting started

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp names.sample.txt names.txt      # your list of people, one name per line
.venv/bin/python app.py            # http://127.0.0.1:5001
```

On first run the app creates `names.csv` from `names.txt`, with every birthday
blank. Fill them in from the web page — you don't need to edit the CSV by hand.

If you'd rather start from data that already has birthdays in it:

```bash
cp names.sample.csv names.csv
```

Seeding happens once. If you started the app before creating `names.txt`, you'll
have an empty `names.csv` that won't re-seed — delete it and start again.

`names.txt` and `names.csv` are gitignored, so real names and birthdates stay on
your machine.

## Using it

- **Sort buttons** — Original, Alphabetical, Age (oldest), Age (youngest), and
  Upcoming birthday, which orders by how soon each birthday falls from today and
  wraps around the year end.
- **Set a birthday** — pick a person and a date. The name dropdown preselects the
  first person still missing a birthday, so you can work down the list.
- **Add a name** — appends a person, with an optional birthday in the same step.
- **Download CSV** — saves a local copy of the birthday store as `birthdays.csv`
  (same `name,birthdate` format the app uses).

People with no birthday recorded always stay at the end of the age and upcoming
sorts rather than being dropped or floated to the top.

## Data

`names.csv` is the store the app reads and writes:

```csv
name,birthdate
Ada,1988-12-10
Nina,
```

Birthdates are stored as ISO `YYYY-MM-DD` — sortable, unambiguous, and what
`<input type="date">` requires. The page renders them US-style ("December 10,
1988"); age is derived at render time and never stored. An empty birthdate means
unknown.

Writes are atomic (temp file + `os.replace`), so an interrupted save can't
truncate the store. Names are unique case-insensitively, since a birthday edit
finds its row by name.

## Tests

```bash
.venv/bin/python -m pytest -q
```

Anything date-dependent takes an explicit reference date rather than calling
`date.today()` internally, so the tests pin a fixed date and don't change meaning
as the calendar moves.

## Also here

`sort_names.py` is the original standalone CLI this grew out of — it reads
`names.txt` and prints the names alphabetically.

```bash
.venv/bin/python sort_names.py
```
