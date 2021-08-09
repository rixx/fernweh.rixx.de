import hashlib
from urllib.parse import quote

import click
import inquirer
import requests


def request(method, url, params=None, json=None, headers=None):
    headers = headers or {}
    headers["User-Agent"] = "fernweh.rixx.de"
    response = requests.request(method, url, params=params, json=json, headers=headers)
    response.raise_for_status()
    return response.json()


def get_location_data(address=True, metadata=True):
    """Gets coordinates, address and other information from OSM and Wikidata (if available)."""
    osm_place = None
    nominatim_url = "https://nominatim.openstreetmap.org/search.php"

    while not osm_place:
        name = inquirer.text(message="What’s the name of the location?")
        results = request("get", nominatim_url, params={"q": name, "format": "jsonv2"})
        if len(results) == 0:
            print("No location found!")
            continue

        chosen = inquirer.list_input(
            message=f"Found {len(results)} results!",
            choices=[
                (content["display_name"], index)
                for index, content in enumerate(results)
            ]
            + [("None of these, try again", False)],
            default=0,
            carousel=True,
        )
        if chosen is False:
            continue
        osm_place = results[chosen]

    location = {
        "name": name,
        "lat": osm_place["lat"],
        "lon": osm_place["lon"],
    }

    if address:
        try:
            address_url = "https://nominatim.openstreetmap.org/lookup"
            result = request(
                "get",
                address_url,
                params={
                    "osm_ids": osm_place["osm_type"][0].upper()
                    + str(osm_place["osm_id"]),
                    "format": "json",
                },
            )[0]["address"]
            location["address"] = {
                "street": f"{result.get('road', '')} {result.get('house_number', '')}".strip(),
                "place": result.get("town", ""),
                "postcode": result.get("postcode", ""),
                "county": result.get("county", ""),
                "state": result.get("state", ""),
                "country": result.get("country", ""),
            }
        except Exception:
            pass

    if metadata:
        location["urls"] = {}
        location["description"] = ""
        location["external"] = {
            "osm": {
                "type": osm_place["osm_type"][0].upper(),
                "id": str(osm_place["osm_id"]),
            }
        }
        try:
            details_url = "https://nominatim.openstreetmap.org/details.php"
            result = request(
                "get",
                details_url,
                params={
                    "osmtype": osm_place["osm_type"][0].upper(),
                    "osmid": str(osm_place["osm_id"]),
                    "addressdetails": 1,
                    "format": "json",
                },
            )
            home = result.get("extratags", {}).get("website")
            if home:
                location["urls"]["home"] = home
            wikidata_id = result.get("extratags", {}).get("wikidata")

            if not wikidata_id:
                from .travel import get_yesno

                add_id = get_yesno(
                    "No Wikidata entry found. Do you want to enter a Wikipedia link?"
                )
                if add_id:
                    wikidata_id = get_wikidata_id_from_url(
                        inquirer.text("Wikipedia page")
                    )
            if wikidata_id:
                add_wikidata_information(location, wikidata_id)
        except Exception:
            pass
    return location


def get_wikidata_id_from_url(url):
    url = url.strip()
    query_url = "https://www.wikidata.org/w/api.php"
    title = url.split("/")[-1]
    wiki = url.split(".")[0][-2:]  # assuming two-letter country codes
    result = request(
        "get",
        query_url,
        params={
            "action": "wbgetentities",
            "sites": f"{wiki}wiki",
            "titles": title,
            "format": "json",
        },
    )
    if result.get("entities"):
        return list(result["entities"].keys())[0]


def add_wikidata_information(location, wikidata_id):
    wikidata_url = (
        f"https://www.wikidata.org/wiki/Special:EntityData/{wikidata_id}.json"
    )
    result = list(request("get", wikidata_url)["entities"].values())[0]

    location["external"]["wikidata_id"] = wikidata_id
    description_de = result.get("descriptions", {}).get("de", {}).get("value")
    description_en = result.get("descriptions", {}).get("en", {}).get("value")

    if description_de and description_en:
        location["description"] = description_de + " / " + description_en
    else:
        location["description"] = description_de or description_en

    location["urls"]["wikipedia"] = result["sitelinks"].get("dewiki", {}).get(
        "url"
    ) or result["sitelinks"].get("enwiki", {}).get("url")
    location["urls"]["wikicommon"] = (
        result["sitelinks"].get("commonswiki", {}).get("url")
    )

    images = result.get("claims", {}).get("P18")
    image = None
    if images:
        image = images[0]
        image_filename = image["mainsnak"]["datavalue"]["value"]
    elif location["urls"]["wikipedia"]:
        base_url = location["urls"]["wikipedia"][:25]
        title = location["urls"]["wikipedia"].split("/")[-1]
        media_query_url = f"{base_url}w/api.php"
        result = request(
            "get",
            media_query_url,
            params={
                "action": "query",
                "prop": "images",
                "titles": title,
                "format": "json",
            },
        )
        try:
            images = [
                i["title"].replace(" ", "_")
                for i in list(result["query"]["pages"].values())[0]["images"]
                if i.get("title") and "commons-logo" not in i.get("title", "").lower()
            ]
            if images:
                image_filename = inquirer.list_input(
                    "Please choose an image",
                    choices=[(f"{base_url}wiki/{image}", image) for image in images]
                    + [("none of the above", None)],
                )
                image_filename = image_filename.split(":", maxsplit=1)[-1]
        except Exception:
            pass

    if image_filename:
        image_filename = image_filename.replace(" ", "_")
        image_md5 = hashlib.md5(image_filename.encode()).hexdigest()
        image_filename = quote(image_filename)  # Only quote AFTER calculating the hash!
        location[
            "cover_image_url"
        ] = f"https://upload.wikimedia.org/wikipedia/commons/{image_md5[0]}/{image_md5[:2]}/{image_filename}"

        url = "https://en.wikipedia.org/w/api.php"
        result = request(
            "get",
            url,
            params={
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "titles": f"File:{image_filename}",
                "iiprop": "extmetadata|url|user|timestamp",
            },
        )["query"]["pages"]["-1"]["imageinfo"][0]

        # We try and locate intended attribution, and if we find none, we fall back to user name and date
        author = result["user"]
        year = result["timestamp"][:4]
        attribution_options = []
        if "Credit" in result["extmetadata"]:
            attribution_options.append(result["extmetadata"]["Credit"]["value"])
        if "Artist" in result["extmetadata"]:
            attribution_options.append(result["extmetadata"]["Artist"]["value"])
        attribution_options.append(
            f'<a href="{result["descriptionurl"]}">{author} ({year})</a>'
        )

        click.echo(
            f"Please take care to look at the license at {result['descriptionurl']} to make sure you're allowed to use it!"
        )
        choice = inquirer.list_input(
            message="Use this image?",
            choices=[("Yes", True), ("Different image", False), ("No image", None)],
            default=True,
        )

        if choice is True:
            location["cover_image_attribution"] = inquirer.list_input(
                message="Image attribution", choices=attribution_options
            )
        elif choice is False:
            location["cover_image_url"] = inquirer.text(message="Image URL", default="")
            location["cover_image_attribution"] = inquirer.text(
                message="Image attribution", default=""
            )
        else:
            location["cover_image_url"] = None
            location["cover_image_attribution"] = None


def get_komoot_route(start, end):
    result = request(
        "post",
        "https://www.komoot.de/api/routing/tour?sport=touringbicycle",
        json={
            "constitution": 3,
            "sport": "touringbicycle",
            "path": [
                {"location": {"lat": start["lat"], "lng": start["lon"]}},
                {"location": {"lat": end["lat"], "lng": end["lon"]}},
            ],
            "segments": [{"geometry": [], "type": "Routed"}],
        },
    )
    distance = round(result["distance"] / 1000, 2)  # km
    duration = int(result["duration"] / 60)  # minutes
    komoot_id = result["query"]  # https://www.komoot.de/plan/tour/{query}
    return {"distance": distance, "duration": duration, "komoot_id": komoot_id}
