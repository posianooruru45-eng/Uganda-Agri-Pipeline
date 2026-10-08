# src/01_collect.py
import requests, json, datetime, pathlib, hashlib, csv

RAW = pathlib.Path("data/raw")
RAW.mkdir(parents=True, exist_ok=True)
STAMP = datetime.date.today().isoformat()


def save_raw(content_bytes, name, ext="json"):
    path = RAW / f"{name}_{STAMP}.{ext}"
    path.write_bytes(content_bytes)
    print(f"Saved {path} ({len(content_bytes)} bytes)")
    return path


def fetch_worldbank():
    url = "https://api.worldbank.org/v2/country/UGA/indicator/AG.PRD.CROP.XD"
    resp = requests.get(url, params={"format": "json", "per_page": 1000}, timeout=30)
    resp.raise_for_status()
    save_raw(resp.content, "worldbank_crop_index")


def fetch_weather(lat, lon, start, end, place_name):
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": "precipitation_sum,temperature_2m_mean",
        "timezone": "Africa/Kampala",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    save_raw(resp.content, f"weather_{place_name}")


def fetch_wfp_prices(csv_url):
    resp = requests.get(csv_url, timeout=60, headers={"User-Agent": "Mozilla/5.0 (capstone-data-fetch/1.0)"})
    resp.raise_for_status()
    save_raw(resp.content, "wfp_food_prices", ext="csv")


def fetch_owid():
    # "cereal-yield" chart: cereal yield (kg per hectare) by country and year
    url = "https://ourworldindata.org/grapher/cereal-yield.csv"
    params = {
        "country": "UGA",
        "time": "2015..2024",
        "csvType": "filtered",
    }
    resp = requests.get(url, params=params, timeout=30, headers={"User-Agent": "capstone-data-fetch/1.0"})
    resp.raise_for_status()
    save_raw(resp.content, "owid_uganda_cereal_yield", ext="csv")


def run_source(fetch_fn, name, *args, **kwargs):
    """Run one source's fetch function; log failure instead of crashing the whole script."""
    try:
        fetch_fn(*args, **kwargs)
        return True
    except requests.exceptions.RequestException as e:
        print(f"[FAILED] {name}: {e}")
        return False


def checksum_all_raw():
    manifest_path = RAW / "manifest.csv"
    write_header = not manifest_path.exists() or manifest_path.stat().st_size == 0
    with open(manifest_path, "a", newline="") as mf:
        w = csv.DictWriter(mf, fieldnames=["file", "sha256", "size_bytes", "date"])
        if write_header:
            w.writeheader()
        for f in sorted(RAW.glob("*")):
            if f.name == "manifest.csv":
                continue
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            w.writerow({"file": f.name, "sha256": h, "size_bytes": f.stat().st_size, "date": STAMP})
    print("Checksums logged to manifest.csv")


if __name__ == "__main__":
    results = {
        "worldbank": run_source(fetch_worldbank, "worldbank"),
        "weather": run_source(fetch_weather, "weather", 0.3476, 32.5825, "2018-01-01", "2024-12-31", "kampala"),
        "owid": run_source(fetch_owid, "owid"),
        "wfp": run_source(
            fetch_wfp_prices,
            "wfp",
            "https://data.humdata.org/dataset/883929b1-521e-4834-97f5-0ccc2df75b89/resource/e082d683-cad5-4dcd-bf54-db76ae254d33/download/wfp_food_prices_uga.csv",
        ),
    }
    checksum_all_raw()
    print("\nSummary:", results)