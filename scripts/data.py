import hashlib

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
        name = inquirer.text_input(message="What’s the name of the location?")
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
            address_url = "https://nominatim.openstreetmap.org/lookup?osm_ids=N6107050239&format=json"
            result = request(
                "get",
                address_url,
                params={
                    "osm_ids": osm_place["osm_type"][0].upper() + osm_place["osm_id"],
                    "format": "json",
                },
            )[0]
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
            "osm": {"type": osm_place["osm_type"][0].upper(), "id": osm_place["osm_id"]}
        }
        try:
            details_url = "https://nominatim.openstreetmap.org/details.php"
            result = request(
                "get",
                details_url,
                params={
                    "osmtype": osm_place["osm_type"][0].upper(),
                    "osmid": osm_place["osm_id"],
                    "addressdetails": 1,
                    "format": "json",
                },
            )
            home = result.get("extratags", {}).get("website")
            if home:
                location["urls"]["home"] = home
            wikidata_id = result.get("extratags", {}).get("wikidata")

            if wikidata_id:
                add_wikidata_information(location, wikidata_id)
        except Exception:
            pass
    return location


def add_wikidata_information(location, wikidata_id):
    wikidata_url = (
        f"https://www.wikidata.org/wiki/Special:EntityData/{wikidata_id}.json"
    )
    result = list(request("get", wikidata_url)["entities"].values())[0]

    location["external"]["wikidata_id"] = wikidata_id
    description_de = result.get("descriptions", {}).get("de", "")
    description_en = result.get("descriptions", {}).get("en", "")
    location["description"] = description_de + " / " + description_en

    location["urls"]["wikipedia"] = result["sitelinks"].get("dewiki", {}).get(
        "url"
    ) or result["sitelinks"].get("enwiki", {}).get("url")
    location["urls"]["wikicommon"] = (
        result["sitelinks"].get("commonswiki", {}).get("url")
    )

    images = result.get("claims", {}).get("P18")
    if images:
        image = images[0]
        image_filename = image["mainsnak"]["datavalue"]["value"]

        image_md5 = hashlib.md5(image_filename.encode()).hexdigest()
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
        if "Credit" in result["extmetadata"]:
            attribution = result["extmetadata"]["Credit"]["value"]
        elif "Artist" in result["extmetadata"]:
            attribution = result["extmetadata"]["Artist"]["value"]
        else:
            attribution = f'<a href="{result["descriptionurl"]}">{author} ({year})'

        click.echo(
            f"Please take care to look at the license at f{result['descriptionurl']} to make sure you're allowed to use it!"
        )
        choice = inquirer.list_input(
            message="Use this image?",
            choices=[("Yes", True), ("Different image", False), ("No image", None)],
        )

        if choice is True:
            location["cover_image_attribution"] = inquirer.text_input(
                prompt="Image attribution", default=attribution
            )
        elif choice is False:
            location["cover_image_url"] = inquirer.text_input(
                prompt="Image URL", default=""
            )
            location["cover_image_attribution"] = inquirer.text_input(
                prompt="Image attribution", default=""
            )
        else:
            location["cover_image_url"] = None


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
