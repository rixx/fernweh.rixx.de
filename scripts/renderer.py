import datetime as dt
import pathlib
import subprocess
from functools import partial
from pathlib import Path

import markdown
import smartypants
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown.extensions.smarty import SmartyExtension
from PIL import Image

from . import travel


def rsync(source, destination):
    subprocess.check_call(["rsync", "--recursive", "--delete", source, destination])


def render_markdown(text):
    return markdown.markdown(text, extensions=[SmartyExtension()])


def render_date(date_value):
    if isinstance(date_value, dt.date):
        return date_value.strftime("%Y-%m-%d")
    return date_value


def render_page(template_name, path, env=None, **context):
    template = env.get_template(template_name)
    html = template.render(**context)
    out_path = pathlib.Path("_html") / path
    out_path.parent.mkdir(exist_ok=True, parents=True)
    out_path.write_text(html)


def _create_new_thumbnail(src_path, dst_path):
    dst_path.parent.mkdir(exist_ok=True, parents=True)

    im = Image.open(src_path)

    if im.width > 240 and im.height > 240:
        im.thumbnail((240, 240))
    im.save(dst_path)


def _create_new_square(src_path, square_path):
    square_path.parent.mkdir(exist_ok=True, parents=True)

    im = Image.open(src_path)
    im.thumbnail((240, 240))

    dimension = max(im.size)

    new = Image.new("RGB", size=(dimension, dimension), color=(255, 255, 255))

    if im.height > im.width:
        new.paste(im, box=((dimension - im.width) // 2, 0))
    else:
        new.paste(im, box=(0, (dimension - im.height) // 2))

    new.save(square_path)


def create_thumbnail(report):
    if not report.cover_path:
        return

    html_path = pathlib.Path("_html") / report.id
    thumbnail_path = html_path / "thumbnail.jpg"
    square_path = html_path / "square.jpg"
    cover_path = html_path / report.cover_path.name
    cover_age = report.cover_path.stat().st_mtime

    if not cover_path.exists() or cover_age > cover_path.stat().st_mtime:
        rsync(report.cover_path, cover_path)
        _create_new_thumbnail(report.cover_path, thumbnail_path)
        _create_new_square(report.cover_path, square_path)


def build_site(**kwargs):
    print("✨ Starting to build the site … ✨")
    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["render_markdown"] = render_markdown
    env.filters["render_date"] = render_date
    env.filters["smartypants"] = smartypants.smartypants
    render = partial(render_page, env=env, home=(travel.HOME_LAT, travel.HOME_LON))

    print("📔 Loading reports from files")
    all_plans = sorted(
        list(travel.load_plans()), key=lambda x: x.relevant_date, reverse=True
    )
    all_reports = sorted(
        list(travel.load_reports()), key=lambda x: x.relevant_date, reverse=True
    )
    all_entries = all_plans + all_reports

    print("🖋 Rendering report pages")
    for report in all_entries:
        render(
            "report.html",
            Path(report.id) / "index.html",
            report=report,
            title=report.metadata["location"]["name"],
            active=report.entry_type,
        )

    print("🔎 Rendering list pages")

    render(
        "list_reports.html",
        "reports/index.html",
        title="Travel reports",
        reports=all_reports,
    )
    render(
        "list_plans.html",
        "plans/index.html",
        title="Travel plans",
        reports=all_plans,
    )

    print("📷 Generating thumbnails")
    for report in all_entries:
        create_thumbnail(report)

    rsync(source="static/", destination="_html/static/")

    # Render the front page
    render(
        "index.html",
        "index.html",
        plans=sorted(all_plans, key=lambda x: x.overview["distance"]["bike"]),
        reports=all_reports,
    )

    print("✨ Rendered HTML files to _html ✨")
