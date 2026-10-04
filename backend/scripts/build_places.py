"""Build the offline North-American places index used for remarks and geocoding fallback.

Source: GeoNames "cities500" (CC BY 4.0) as shipped in the `geonamescache` wheel.

    pip download geonamescache==3.0.2 --no-deps -d /tmp/gnc
    unzip /tmp/gnc/geonamescache-*.whl -d /tmp/gnc/whl
    python scripts/build_places.py /tmp/gnc/whl/geonamescache/data/cities500.json

Writes trips/data/places_na.tsv.gz with one place per line:
    name, region, country, lat, lon, population, timezone
"""

import gzip
import json
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "trips" / "data" / "places_na.tsv.gz"

# GeoNames admin1 codes -> postal abbreviations. US codes are already USPS codes.
CANADA = {
    "01": "AB", "02": "BC", "03": "MB", "04": "NB", "05": "NL", "07": "NS", "08": "ON",
    "09": "PE", "10": "QC", "11": "SK", "12": "YT", "13": "NT", "14": "NU",
}
MEXICO = {
    "01": "AGS", "02": "BC", "03": "BCS", "04": "CAMP", "05": "CHIS", "06": "CHIH",
    "07": "COAH", "08": "COL", "09": "CDMX", "10": "DGO", "11": "GTO", "12": "GRO",
    "13": "HGO", "14": "JAL", "15": "MEX", "16": "MICH", "17": "MOR", "18": "NAY",
    "19": "NL", "20": "OAX", "21": "PUE", "22": "QRO", "23": "QROO", "24": "SLP",
    "25": "SIN", "26": "SON", "27": "TAB", "28": "TAMPS", "29": "TLAX", "30": "VER",
    "31": "YUC", "32": "ZAC",
}
MIN_POPULATION = {"US": 500, "CA": 500, "MX": 1000}


def region_for(place: dict) -> str | None:
    country, code = place["countrycode"], place["admin1code"]
    if country == "US":
        return code if len(code) == 2 and code.isalpha() else None
    if country == "CA":
        return CANADA.get(code)
    if country == "MX":
        return MEXICO.get(code)
    return None


def main(source: str) -> None:
    raw = json.loads(Path(source).read_text(encoding="utf-8"))
    places = raw.values() if isinstance(raw, dict) else raw
    rows = []
    for place in places:
        country = place["countrycode"]
        if country not in MIN_POPULATION or place["population"] < MIN_POPULATION[country]:
            continue
        region = region_for(place)
        if not region:
            continue
        name = place["name"].replace("\t", " ").strip()
        rows.append(
            (
                name,
                region,
                country,
                f"{place['latitude']:.5f}",
                f"{place['longitude']:.5f}",
                str(place["population"]),
                place["timezone"],
            )
        )
    # Larger places first so ties in search resolve toward well-known towns.
    rows.sort(key=lambda r: (-int(r[5]), r[0]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", compresslevel=9) as fh:
        fh.write("# GeoNames cities500 subset (US, CA, MX). CC BY 4.0, https://www.geonames.org\n")
        for row in rows:
            fh.write("\t".join(row) + "\n")
    print(f"wrote {len(rows)} places to {OUTPUT} ({OUTPUT.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
