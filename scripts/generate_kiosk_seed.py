"""Generates seeds/raw_kiosk_sales.csv -- the deliberately messy "new
channel" table for the tutorial's grounding-under-ambiguity exercise.

Story: jaffle_shop pilots a kiosk at the Downtown store (store_id=1).
Wired up fast by whoever was free, sourced from a different POS vendor's
daily export -- nobody's gone back to reconcile it with the rest of the
model yet. Two deliberate collisions with the existing model:
  - order_total here is a DAILY total across all kiosk sales, not one
    order's total -- same column name as orders.order_total, different
    grain entirely.
  - store_id is a real FK to stg_stores, but (deliberately, see
    schema.yml) no `relationships` test declares it -- same
    undocumented-real-relationship pattern already found organically in
    order_items/products.

Uses the `faker` library directly rather than dbt Labs' own jafgen
(https://github.com/dbt-labs/jaffle-shop-generator, Apache-2.0) --
jafgen's schema is fixed (customers/orders/products/supplies/stores/
tweets) and doesn't support adding a new channel/table without deeper
changes not worth it for ~20 rows. See README.md's Attribution section
for the full credit to dbt Labs' jaffle-shop, jaffle-shop-data, and
jaffle-shop-generator projects that the rest of this repo is built on.

Usage: python3 scripts/generate_kiosk_seed.py
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

KIOSK_ID = 1
STORE_ID = 1  # Downtown, per seeds/raw_stores.csv
START_DATE = date(2022, 6, 1)
N_DAYS = 21


def generate_rows() -> list[dict]:
    rows = []
    for i in range(N_DAYS):
        sale_date = START_DATE + timedelta(days=i)
        items_sold = random.randint(8, 55)
        # Daily total loosely tracks items sold, not a fixed per-item price --
        # a real POS export wouldn't be a clean multiple, so don't fake one.
        order_total = round(items_sold * random.uniform(3.20, 5.75), 2)
        rows.append(dict(
            kiosk_id=KIOSK_ID,
            store_id=STORE_ID,
            sale_date=sale_date.isoformat(),
            order_total=order_total,
            items_sold=items_sold,
        ))
    return rows


def main():
    rows = generate_rows()
    out_path = Path("seeds/raw_kiosk_sales.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["kiosk_id", "store_id", "sale_date", "order_total", "items_sold"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {out_path} -- {len(rows)} rows, {START_DATE} to {rows[-1]['sale_date']}")


if __name__ == "__main__":
    main()
