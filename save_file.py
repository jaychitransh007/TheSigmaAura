import pandas as pd
from stores.json_files.json_to_dataframe import load_store_products_flat


filenames = [
    "andamen",
    "bunaai",
    "dashanddot",
    "houseoffett",
    "ikkivi",
    "kalki",
    "kharakapas",
    "lovepangolin",
    "powerlook",
    "saltattire",
    "suta",
    "thebearhouse",
    "thehouseofrare",
]


# nicobar', '

for fn in filenames:
    filename = f"{fn}.json"
    print(filename)
    df = load_store_products_flat(file_name=filename, stores_dir="stores/json_files")
    df["store"] = fn
    df["price"] = df["variants__1__price"].astype("float64")
    df = df[df["price"] >= 2000].reset_index(drop=True)
    df["description"] = (
        "title: "
        + df["title"]
        + "product_type: "
        + df["product_type"]
        + "body_html: "
        + df["body_html"]
    )
    df = df.loc[
        :,
        [
            "id",
            "title",
            "description",
            "store",
            "price",
            "images__0__src",
            "images__1__src",
            "handle",
        ],
    ]
    print(df.columns)
    csv_file = f"stores/processed_csv_files/{fn}_processed.csv"
    df.to_csv(csv_file)
