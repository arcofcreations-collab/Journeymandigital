"""Benchmark sources: real public datasets, pinned to commits.

Split is fixed in docs/SPEC_v1_FROZEN.md. DEV sources may be used for
design and tuning; TEST sources are held out.
"""

REPOS = {
    "oil-prices": ("datasets/oil-prices", "b9059a0a47cf5bc8e8bc18078ef7981a6fca0fc0"),
    "natural-gas": ("datasets/natural-gas", "83b8b85fbad7d18bbecbd6570c068b91148711d2"),
    "gold-prices": ("datasets/gold-prices", "95bfea9197222dcda13d8c4d9928fb631fe745aa"),
    "finance-vix": ("datasets/finance-vix", "3dbea23c70cc2afbeeec8ac232c9ec72ac26ac21"),
    "exchange-rates": ("datasets/exchange-rates", "0947c2304370a5a4dd8db74cdacb8486e7d85cbe"),
    "covid-19": ("datasets/covid-19", "bdd76cfa0d80a132898345bc21939f89b2e29137"),
    "cpi-us": ("datasets/cpi-us", "34598e807abe4b65ca322b2a7d086a0816fa768f"),
    "house-prices-us": ("datasets/house-prices-us", "ed61ff762205793f82a88417cb30e5b3cbc6e49e"),
    "bond-yields-us-10y": ("datasets/bond-yields-us-10y", "ba336158ac627766ae23ab8bbc46e6e7eab1294a"),
    "s-and-p-500": ("datasets/s-and-p-500", "78cdcebfd6725c31a914947efd08ddadac08eb1e"),
    "vega": ("vega/vega-datasets", "ede9366badecc625cd6bcea5c4aaa055870c6ca6"),
    "jbrownlee": ("jbrownlee/Datasets", "d20fcb6402ae34e653d4513b00f39257bb37ed7f"),
}

# (split, repo key, path in repo, column, parser)
# parser: "iso" (YYYY-MM-DD[...]), "ymd_slash_time" (YYYY/MM/DD HH:MM:SS),
#         "mon_d_y" (Jun 12 1998), "iso_datepart" (drop time/timezone)
SOURCES = [
    # ---------------- DEV ----------------
    ("DEV", "oil-prices", "data/brent-daily.csv", "Date", "iso"),
    ("DEV", "oil-prices", "data/brent-weekly.csv", "Date", "iso"),
    ("DEV", "oil-prices", "data/brent-monthly.csv", "Date", "iso"),
    ("DEV", "oil-prices", "data/brent-year.csv", "Date", "iso"),
    ("DEV", "oil-prices", "data/wti-daily.csv", "Date", "iso"),
    ("DEV", "oil-prices", "data/wti-weekly.csv", "Date", "iso"),
    ("DEV", "oil-prices", "data/wti-monthly.csv", "Date", "iso"),
    ("DEV", "oil-prices", "data/wti-year.csv", "Date", "iso"),
    ("DEV", "natural-gas", "data/daily.csv", "Date", "iso"),
    ("DEV", "natural-gas", "data/monthly-processed.csv", "Date", "iso"),
    ("DEV", "gold-prices", "data/monthly-processed.csv", "Date", "iso"),
    ("DEV", "finance-vix", "data/vix-daily.csv", "DATE", "iso"),
    ("DEV", "finance-vix", "data/vix-monthly.csv", "Date", "iso"),
    ("DEV", "jbrownlee", "daily-min-temperatures.csv", "Date", "iso"),
    ("DEV", "vega", "data/birdstrikes.csv", "Flight Date", "iso"),
    # ---------------- TEST (held out) ----------------
    ("TEST", "exchange-rates", "data/daily.csv", "Date", "iso"),
    ("TEST", "exchange-rates", "data/monthly.csv", "Date", "iso"),
    ("TEST", "exchange-rates", "data/annual.csv", "Date", "iso"),
    ("TEST", "covid-19", "data/countries-aggregated-sample.csv", "Date", "iso"),
    ("TEST", "covid-19", "data/key-countries-pivoted.csv", "Date", "iso"),
    ("TEST", "covid-19", "data/worldwide-aggregate.csv", "Date", "iso"),
    ("TEST", "cpi-us", "data/cpiai.csv", "Date", "iso"),
    ("TEST", "house-prices-us", "data/national-month.csv", "Date", "iso"),
    ("TEST", "bond-yields-us-10y", "data/monthly.csv", "Date", "iso"),
    ("TEST", "s-and-p-500", "archive/fred_sp500.csv", "observation_date", "iso"),
    ("TEST", "vega", "data/seattle-weather.csv", "date", "iso"),
    ("TEST", "vega", "data/weather.csv", "date", "iso"),
    ("TEST", "vega", "data/sp500-2000.csv", "date", "iso"),
    ("TEST", "vega", "data/movies.json", "Release Date", "mon_d_y"),
    ("TEST", "vega", "data/la-riots.csv", "death_date", "iso"),
    ("TEST", "vega", "data/stocks.csv", "date", "mon_d_y"),
    ("TEST", "vega", "data/unemployment-across-industries.json", "date", "iso_datepart"),
    ("TEST", "vega", "data/co2-concentration.csv", "Date", "iso"),
    ("TEST", "vega", "data/iowa-electricity.csv", "year", "iso"),
    ("TEST", "vega", "data/github.csv", "time", "ymd_slash_time"),
    ("TEST", "jbrownlee", "daily-max-temperatures.csv", "Date", "iso"),
    ("TEST", "jbrownlee", "daily-total-female-births.csv", "Date", "iso"),
]


def raw_url(repo_key: str, path: str) -> str:
    slug, commit = REPOS[repo_key]
    return f"https://raw.githubusercontent.com/{slug}/{commit}/{path}"
