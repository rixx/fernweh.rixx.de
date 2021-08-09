import datetime as dt
import glob
import os
import re
import shutil
import subprocess
from functools import cached_property
from pathlib import Path
from urllib.request import urlretrieve

import click
import frontmatter
import inquirer
from unidecode import unidecode

from . import data

HOME_LAT = "52.741860"
HOME_LON = "13.265480"


def slugify(text):
    """Convert Unicode string into blog slug."""
    # https://leancrew.com/all-this/2014/10/asciifying/
    text = re.sub("[–—/:;,.]", "-", text)  # replace separating punctuation
    ascii_text = unidecode(text).lower()  # best ASCII substitutions, lowercased
    ascii_text = re.sub(r"[^a-z0-9 -]", "", ascii_text)  # delete any other characters
    ascii_text = ascii_text.replace(" ", "-")  # spaces to hyphens
    ascii_text = re.sub(r"-+", "-", ascii_text)  # condense repeated hyphens
    return ascii_text


def get_date(prompt, default="today", allow_empty=False):
    choices = ["today", "yesterday", "another day"]
    if default:
        choices.append(default)
    if allow_empty:
        choices.append("none")
    date = inquirer.list_input(
        message=prompt, choices=choices, carousel=True, default=default
    )
    today = dt.datetime.now()

    if allow_empty and date == "none":
        return
    if date == "today":
        return today.date()
    if date == "yesterday":
        yesterday = today - dt.timedelta(days=1)
        return yesterday.date()
    if date == default:
        return default

    date = None
    while True:
        date = inquirer.text(message="Which other day?")

        if re.match(r"^\d{4}-\d{2}-\d{2}$", date.strip()):
            return dt.datetime.strptime(date, "%Y-%m-%d").date()
        elif re.match(r"^\d{1,2} [A-Z][a-z]+ \d{4}$", date.strip()):
            return dt.datetime.strptime(date, "%d %B %Y").date()
        else:
            click.echo(click.style(f"Unrecognised date: {date}", fg="red"))


def get_yesno(prompt, default=True):
    return inquirer.list_input(
        message=prompt,
        choices=[("Yes", True), ("No", False)],
        default=default,
        carousel=True,
    )


class Report:
    def __init__(self, entry_type=None, metadata=None, text=None, path=None):
        self.entry_type = entry_type
        self.path = Path(path) if path else None
        if path:
            self._load_data_from_file()
        elif metadata and entry_type:
            self.metadata = metadata
            self.text = text
        else:
            raise Exception(f"A report needs metadata or a path! ({self.path})")

    def __str__(self):
        if self.path:
            return f"Report(path={self.path})"
        return f"Report(path=None, title={self.metadata['location']['name']})"

    def __repr__(self):
        return str(self)

    def _load_data_from_file(self, path=None):
        try:
            post = frontmatter.load(path or self.path)
        except Exception as e:
            raise Exception(
                f"Error while loading report from {path or self.path}!\n{e}"
            )
        self.metadata = post.metadata
        self.text = post.content
        if not self.entry_type:
            self.entry_type = self.entry_type_from_path()

    @cached_property
    def slug(self):
        if self.path:
            return self.path.parent.name
        return slugify(self.metadata["location"]["name"])

    @cached_property
    def latlon(self):
        return self.metadata["location"]["lat"], self.metadata["location"]["lon"]

    @property
    def relevant_date(self):
        if self.entry_type == "reports":
            result = sorted([visit["start_time"] for visit in self.metadata["visits"]])[
                -1
            ]
        else:
            result = self.metadata["plan"].get(
                "start_time", self.metadata["plan"]["date_added"]
            )
        if isinstance(result, dt.date):
            return result
        return dt.datetime.strptime(result, "%Y-%m-%d").date()

    @cached_property
    def id(self):
        return self.slug

    @property
    def first_paragraph(self):
        return self.text.strip().split("\n\n")[0] if self.text else ""

    @cached_property
    def cover_path(self):
        cover_path = self.path.parent / "cover.jpg"
        if cover_path.exists():
            return cover_path

    def entry_type_from_path(self):
        valid_entry_types = ("reports", "plans")
        entry_type = self.path.parent.parent.name
        if entry_type not in valid_entry_types:
            raise Exception(f"Wrong path: {entry_type}")
        return entry_type

    def change_entry_type(
        self,
        entry_type,
        save=True,
    ):
        if entry_type != self.entry_type:
            if entry_type not in ("reports", "plans"):
                raise Exception(f"Invalid entry_type {entry_type}")
            if entry_type == "report" and not self.metadata.get("visits", {}).get(
                "start_time"
            ):
                raise Exception(
                    f"Cannot become a report, no start_time provided! ({self.path})"
                )
            self.entry_type = entry_type
        if save:
            self.save()

    def get_path(self):
        out_path = Path("data") / self.entry_type / self.id / "index.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        return out_path

    def save(self):
        self.clean()
        current_path = self.get_path()
        if self.path and current_path != self.path:
            if Path(self.path).exists():
                Path(self.path).unlink()
            for other_file in self.path.parent.glob("*"):
                other_file.rename(current_path.parent / other_file.name)
        with open(current_path, "wb") as out_file:
            frontmatter.dump(
                frontmatter.Post(content=self.text, **self.metadata), out_file
            )
            out_file.write(b"\n")
        self.path = current_path
        return current_path

    def edit(self):
        subprocess.check_call([os.environ.get("EDITOR", "vim"), self.path])
        self._load_data_from_file()
        self.save()

    def clean(self):
        required = ("name", "lat", "lon")
        if any(not self.metadata["location"].get(key) for key in required):
            raise Exception(
                "Missing required metadata! Has to include name, description, lat and lon."
            )

        if "visits" in self.metadata and self.entry_type == "reports":
            if not self.metadata["visits"][-1].get("start_time"):
                raise Exception(
                    f"A report needs at least one start_time entry. ({self.path})"
                )

        if "plan" in self.metadata:
            if not self.metadata["plan"].get("date_added"):
                self.metadata["plan"]["date_added"] = dt.datetime.now().date()
        else:
            self.metadata["plan"] = {"date_added": dt.datetime.now().date()}

    def download_cover(self, cover_image_url=None, force_new=False, attribution=None):
        if not force_new and self.cover_path:
            click.echo(f"Cover for {self.slug} already exists, passing.")
            return

        filename, headers = urlretrieve(cover_image_url)
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif"}[
            headers["Content-Type"]
        ]
        destination = self.path.parent / "cover.jpg"
        if not destination.exists() or force_new:
            if self.cover_path:
                self.cover_path.unlink()

            if extension == "jpg":
                shutil.move(filename, destination)
            else:
                subprocess.check_call(["convert", filename, destination])

        self.metadata["location"]["cover_image_url"] = cover_image_url
        if attribution:
            self.metadata["location"]["cover_image_attribution"] = attribution
        del self.cover_path
        return self.cover_path

    @property
    def start_time_lookup(self):
        return {
            d.strftime("%Y"): d
            for d in self.metadata.get("visits", {}).get("start_time", [])
        }

    def show_cover(self):
        if not self.cover_path:
            print("No cover image found.")
            return
        subprocess.check_call(["xdg-open", self.cover_path])


def _load_entries(dirpath):
    for path in Path(dirpath).rglob("*.md"):
        try:
            yield Report(path=path)
        except Exception as e:
            print(f"Error loading {path}")
            raise e


def load_reports():
    return _load_entries(dirpath="data/reports")


def load_plans():
    return _load_entries(dirpath="data/plans")


def get_location_from_input():
    questions = [
        inquirer.Text("name", message="What’s the name of the location?"),
        inquirer.Text("cover_image_url", message="What’s the cover URL?"),
        inquirer.Text("wikipedia_url", message="Wikipedia link"),
        inquirer.Text("home_url", message="Homepage"),
        inquirer.Text("description", message="Short description"),
        inquirer.Text("lat", message="Latitude"),
        inquirer.Text("lon", message="Longitude"),
    ]
    answers = inquirer.prompt(questions)
    answers["address"] = inquirer.prompt(
        [
            inquirer.Text("street", message="Street & no"),
            inquirer.Text("postcode", message="Postal code"),
            inquirer.Text("place", message="Place"),
            inquirer.Text("county", message="County"),
            inquirer.Text("state", message="State"),
            inquirer.Text("country", message="Country", default="Germany"),
        ]
    )

    wiki_url = answers.pop("wikipedia_url")
    home_url = answers.pop("home_url")

    if wiki_url or home_url:
        answers["urls"] = {"wikipedia": wiki_url, "home": home_url}
    return answers


def inquire_location(prompt, none_value=None):
    result = inquirer.list_input(
        message=prompt,
        choices=[
            ("At home", "home"),
            ("At another known location", "known"),
            ("Let me enter a location", "custom"),
        ]
        + ([none_value, None] if none_value else []),
    )
    if result in (None, "home"):
        return result
    if result == "known":
        return get_location_from_user()
    if result == "custom":
        return data.get_location_data(address=False, metadata=False)


def get_journey_data(metadata, entry_type):
    questions = {
        "date": {
            "reports": "When did you go there?",
            "plans": "Do you have a date in mind?",
        },
        "leg_count": {
            "reports": "How many parts did your journey have?",
            "plans": "How many parts will your journey have?",
        },
        "start": {"reports": "Where did you start?", "plans": "Where will you start?"},
        "end": {
            "reports": "Where did this leg end?",
            "plans": "Where will this leg end?",
        },
        "transport": {
            "reports": "How did you get there?",
            "plans": "How will you get there?",
        },
    }
    journey = {
        "start_time": get_date(
            prompt=questions["date"][entry_type], allow_empty=(entry_type == "plans")
        ),
        "legs": [],
    }
    leg_count = int(
        inquirer.text(message=questions["leg_count"][entry_type], default="1")
    )
    end = None

    def get_coordinates(place):
        if isinstance(place, Report):
            return {"lat": place.latlon[0], "lon": place.latlon[1]}
        if isinstance(place, dict):
            return place
        if place == "home":
            return {"lat": HOME_LAT, "lon": HOME_LON}
        if not place:
            return {
                "lat": metadata["location"]["lat"],
                "lon": metadata["location"]["lon"],
            }

    total_cost = 0
    total_distance = 0
    total_duration = 0
    for count in range(1, leg_count + 1):
        click.echo(f"Leg {count}")
        if end or count > 1:
            start = end
        else:
            start = inquire_location(prompt=questions["start"][entry_type])
        if count == leg_count and entry_type == "plans":
            end = None  # Planned journeys always end at the target
        else:
            end = inquire_location(
                prompt=questions["end"][entry_type], none_value="At the goal"
            )

        # start and end can be: empty (meaning the current location), a string called "home", a report object (serialised as its slug), or a dictionary with a lat/len and a name
        transport = inquirer.list_input(
            message=questions["transport"][entry_type],
            choices=("train", "bike", "car", "foot"),
        )
        leg = {
            "start_location": start.slug if hasattr(start, "slug") else start,
            "end_location": end.slug if hasattr(end, "slug") else end,
            "distance": None,
            "duration": None,
            "cost": None,
        }
        route_data = data.get_komoot_route(get_coordinates(start), get_coordinates(end))
        leg["distance"] = route_data["distance"]
        if transport == "train":
            leg["cost"] = inquirer.text(message="How much does this leg cost?")

        if transport == "bike":
            leg["duration"] = route_data["duration"]
            leg["komoot_id"] = route_data["komoot_id"]
        else:
            leg["duration"] = int(
                inquirer.text(message="How many minutes does this leg take?")
            )
        total_duration += int(leg["duration"] or 0)
        total_distance += float(leg["distance"] or 0)
        total_cost += float(leg["cost"] or 0)
        journey["legs"].append(leg)

    journey["distance"] = inquirer.text(
        f"Total journey distance (calculated: {total_distance}km)",
        default=total_distance,
    )
    journey["duration"] = inquirer.text(
        f"Total journey duration, human readable (calculated: {total_duration} minutes)",
        default=total_duration,
    )
    journey["cost"] = inquirer.text(
        f"Total journey cost (calculated: {total_cost}€)", default=total_cost
    )
    return journey


def create_journey():
    entry_type = inquirer.list_input(
        message="What type of location is this?",
        choices=[
            ("One I want to visit", "plans"),
            ("One I’ve visited", "reports"),
        ],
        carousel=True,
    )
    get_apis = get_yesno("Do you want to get the location data from APIs?")

    metadata = None
    if get_apis:
        try:
            metadata = {"location": data.get_location_data()}
        except Exception as e:
            print(f"Could not get API data: {e}")

    if not metadata:
        metadata = {"location": get_location_from_input()}

    journey = get_journey_data(metadata, entry_type=entry_type)
    if entry_type == "reports":
        metadata["visits"] = [journey]
    else:
        metadata["plan"] = journey
        metadata["visits"] = []

    report = Report(metadata=metadata, text="", entry_type=entry_type)
    report.save()

    if metadata["location"].get("cover_image_url"):
        report.download_cover(metadata["location"]["cover_image_url"], force_new=True)
        report.save()

    report.edit()


def get_location_from_user():
    while True:
        original_search = inquirer.text(message="What's the place called?")
        search = original_search.strip().lower().replace(" ", "-")
        files = list(glob.glob(f"data/**/**/*{search}*/index.md"))
        if len(files) == 0:
            click.echo(click.style("No location like that was found.", fg="red"))
            continue

        reports = [Report(path=path) for path in files]
        options = [
            (
                f"{report.metadata['location']['name']} ({report.entry_type})",
                report,
            )
            for report in reports
        ]
        options += [("Try a different search", "again")]
        choice = inquirer.list_input(
            f"Found {len(reports)} locations. Which one did you mean?",
            choices=options,
            carousel=True,
        )
        if choice == "again":
            continue
        return choice


def _change_rating(report):
    plan = report.metadata.get("plan")
    if plan:
        report.metadata["plan"] = {"date_added": plan.pop("date_added", None)}
        report["visits"].append(plan)
        report.entry_type = "reports"
        report.save()
    report.edit()


def _change_remove(report):
    report.path.unlink()


def _change_manually(report):
    report.edit()


def _change_cover(report):
    url = inquirer.text(message="Cover image URL")
    attribution = inquirer.text(message="Cover image attribution")
    report.download_cover(url, attribution=attribution, force_new=True)
    report.show_cover()


def change_journey():
    report = get_location_from_user()
    while True:
        action = inquirer.list_input(
            message="What do you want to do with this location?",
            choices=[
                ("Write report", "rating"),
                ("Remove from library", "remove"),
                ("Edit manually", "manually"),
                ("Change cover image", "cover"),
                ("Choose different place", "location"),
                ("Quit", "quit"),
            ],
            carousel=True,
        )
        if action == "quit":
            return
        if action == "location":
            return change_journey()
        globals()[f"_change_{action}"](
            report=report,
        )
        if action == "remove":
            return change_journey()
