"""
XAUUSD M1 data pipeline.

Downloads free 1-minute XAUUSD bars from HistData.com (2015 -> present),
normalises the timezone, and writes two parquet files used by every other
script in this repo:

    m1.parquet     ~4.08M M1 bars, tz-aware America/New_York
    daily.parquet  ~3,006 trading-day OHLC bars (18:00 NY roll)

TIMEZONE NOTE (this matters more than anything else in the file)
---------------------------------------------------------------
HistData documents its ASCII export as "EST without daylight savings".
That is not what the file actually contains. Anchoring on two events whose
wall-clock time is fixed by definition -- Non-Farm Payrolls (08:30 America/
New_York) and the London PM gold fix (15:00 Europe/London) -- both land on
the same stamp in summer and winter. They can only do that if the stamps
are already New York local time *with* DST.

Getting this wrong shifts every summer observation by one hour and quietly
destroys any session-level result. `verify_timezone()` re-runs the check.
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
import zipfile

import numpy as np
import pandas as pd

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
BASE = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/xauusd"
POST = "https://www.histdata.com/get.php"


def _token(page_url: str, jar: str) -> str | None:
    """HistData gates the download behind a per-page token; fetch it."""
    html = subprocess.run(
        ["curl", "-sS", "-m", "60", "-c", jar, "-H", f"User-Agent: {UA}", page_url],
        capture_output=True, text=True,
    ).stdout
    match = re.search(r'id="tk" value="([^"]+)"', html)
    return match.group(1) if match else None


def download(out_dir: str = "raw", years=range(2015, 2026), current_year_months=None) -> None:
    """Full years come as one zip each; the in-progress year is served monthly."""
    os.makedirs(out_dir, exist_ok=True)
    jobs = [(y, "") for y in years]
    if current_year_months:
        year, months = current_year_months
        jobs += [(year, f"{mth:02d}") for mth in months]

    for year, month in jobs:
        dest = os.path.join(out_dir, f"xau_{year}{'_' + month if month else ''}.zip")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"  have {dest}")
            continue
        page = f"{BASE}/{year}" + (f"/{int(month)}" if month else "")
        jar = os.path.join(out_dir, f".jar_{year}")
        tok = _token(page, jar)
        if not tok:
            print(f"  no token for {year}{month} -- skipped")
            continue
        subprocess.run([
            "curl", "-sS", "-m", "300", "-b", jar, "-H", f"User-Agent: {UA}",
            "-H", f"Referer: {page}", "-X", "POST", POST,
            "--data", f"tk={tok}&date={year}&datemonth={year}{month}"
                      f"&platform=ASCII&timeframe=M1&fxpair=XAUUSD",
            "-o", dest,
        ], check=True)
        print(f"  {dest}  {os.path.getsize(dest):,} bytes")


def extract(raw_dir: str = "raw", out_dir: str = "ext") -> None:
    os.makedirs(out_dir, exist_ok=True)
    for path in sorted(glob.glob(os.path.join(raw_dir, "*.zip"))):
        if os.path.getsize(path) == 0:
            continue
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.endswith(".csv"):
                    zf.extract(name, out_dir)


def build(ext_dir: str = "ext") -> tuple[pd.DataFrame, pd.DataFrame]:
    files = sorted(glob.glob(os.path.join(ext_dir, "DAT_ASCII_XAUUSD_M1_*.csv")))
    if not files:
        raise FileNotFoundError(f"no extracted CSVs in {ext_dir}/ -- run download() and extract() first")

    m1 = pd.concat(
        [pd.read_csv(f, sep=";", header=None,
                     names=["ts", "open", "high", "low", "close", "vol"],
                     dtype={"ts": str}) for f in files],
        ignore_index=True,
    )
    m1["dt"] = pd.to_datetime(m1["ts"], format="%Y%m%d %H%M%S")
    m1 = (m1.drop(columns=["ts", "vol"])
             .sort_values("dt")
             .drop_duplicates("dt")
             .set_index("dt"))

    # See the module docstring: these stamps are New York local, DST included.
    m1.index = m1.index.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    m1 = m1[~m1.index.isna()]

    # Gold trades 18:00 -> 17:00 NY. Label each session by the day it closes on,
    # so "Friday" is the session that ends Friday 17:00 rather than the one that
    # starts Friday evening.
    m1["tday"] = (m1.index + pd.Timedelta(hours=6)).normalize().date

    grp = m1.groupby("tday")
    daily = pd.DataFrame({
        "open": grp["open"].first(),
        "high": grp["high"].max(),
        "low": grp["low"].min(),
        "close": grp["close"].last(),
        "bars": grp["close"].size(),
    })
    daily = daily[daily["bars"] > 400]        # drop holiday half-sessions
    daily.index = pd.to_datetime(daily.index)

    m1 = m1[m1["tday"].isin(set(daily.index.date))]
    m1.to_parquet("m1.parquet")
    daily.to_parquet("daily.parquet")
    return m1, daily


def verify_timezone(m1: pd.DataFrame) -> None:
    """NFP is always 08:30 New York. If the conversion is right it lands on the
    same minute in January and in July; if it drifts an hour, it is wrong."""
    rng = (m1["high"] - m1["low"]).rename("rng").to_frame()
    rng["dow"] = m1.index.dayofweek
    rng["dom"] = m1.index.day
    rng["month"] = m1.index.month
    rng["hm"] = m1.index.strftime("%H:%M")
    nfp = rng[(rng["dow"] == 4) & (rng["dom"] <= 7)]

    winter = nfp[nfp["month"].isin([1, 2, 12])].groupby("hm")["rng"].mean().idxmax()
    summer = nfp[nfp["month"].isin([5, 6, 7, 8, 9])].groupby("hm")["rng"].mean().idxmax()
    print(f"  NFP volatility peak -- winter {winter}, summer {summer}")
    if winter == summer == "08:30":
        print("  OK: stamps are New York local time with DST.")
    else:
        raise AssertionError(
            f"timezone check failed (winter {winter}, summer {summer}); expected 08:30 for both"
        )


if __name__ == "__main__":
    print("downloading...")
    download(current_year_months=(2026, range(1, 9)))
    print("extracting...")
    extract()
    print("building...")
    m1, daily = build()
    print(f"  {len(m1):,} M1 bars | {len(daily):,} sessions "
          f"| {daily.index[0].date()} -> {daily.index[-1].date()}")
    print("verifying timezone...")
    verify_timezone(m1)
