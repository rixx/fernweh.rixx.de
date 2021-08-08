from setuptools import setup

setup(
    name="fernweh-rixx-de",
    author="Tobias Kunze",
    author_email="r@rixx.de",
    url="https://github.com/rixx/fernweh.rixx.de",
    packages=["scripts"],
    entry_points="""
        [console_scripts]
        travel=scripts.cli:cli
    """,
    install_requires=[
        "click",
        "inquirer==2.6.*",
        "jinja2==2.11.*",
        "markdown==3.1.*",
        "mastodon.py",
        "networkx==2.5.*",
        "pillow==7.1.*",
        "python-dateutil",
        "python-frontmatter==0.5.*",
        "requests",
        "smartypants",
        "unidecode",
    ],
)
