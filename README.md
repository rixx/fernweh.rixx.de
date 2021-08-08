# fernweh.rixx.de

This is the source code for <https://fernweh.rixx.de>, where I track the places I've travelled, and where I want to go.
This repo contains both the scripts that build the site, and the source data used by the scripts.

## How it works

Each place is a text file, with a bit of metadata at the top, and Markdown text in the body. When I run the build
script, it reads all these files, and turns them into a set of HTML files. I upload a copy of those HTML files to my web
server, where they're served by nginx.

The data entry is eased by a data entry script that allows me to add places (either as planned or visited), and can also
pull data from Wikidata or push data to social media. But this repo and its contents are the primary data source.

## Usage

In a virtualenv, run `pip install -e .`. Then you can run:

- `travel` to get to a menu that allows you to access all other actions.
- `travel social` to post to social media. My nick and name are currently hardcoded.
- `travel build` to build the site, creates the `_html` directory
- `travel add` to add a new place.
- `travel edit` to edit an existing place.

## Related work

This site is built on my [book blog](https://books.rixx.de) which uses pretty much the same [tech and
layout](https://github.com/rixx/books.rixx.de).
