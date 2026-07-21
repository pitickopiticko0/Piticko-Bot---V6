"""Databázové operace produktového modulu MakejPC."""

from typing import Any, Optional


def product_exists(database: Any, product_code: str) -> bool:
    with database.connect() as conn:
        return conn.execute(
            "SELECT product_code FROM makejpc_products WHERE product_code = ?",
            (product_code,),
        ).fetchone() is not None


def count_products(database: Any) -> int:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM makejpc_products"
        ).fetchone()
        return int(row["c"])


def add_product(
    database: Any,
    product_code: str,
    name: str,
    price: Optional[str],
    availability: Optional[str],
    product_url: str,
    image_url: Optional[str],
    announced: bool = False,
) -> None:
    now = database.now()
    with database.connect() as conn:
        conn.execute("""
            INSERT INTO makejpc_products (
                product_code, name, price, availability, product_url,
                image_url, announced, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product_code,
            name,
            price,
            availability,
            product_url,
            image_url,
            int(announced),
            now,
            now,
        ))
        conn.commit()


def update_product(
    database: Any,
    product_code: str,
    name: str,
    price: Optional[str],
    availability: Optional[str],
    product_url: str,
    image_url: Optional[str],
) -> None:
    with database.connect() as conn:
        conn.execute("""
            UPDATE makejpc_products
            SET name = ?,
                price = ?,
                availability = ?,
                product_url = ?,
                image_url = ?,
                updated_at = ?
            WHERE product_code = ?
        """, (
            name,
            price,
            availability,
            product_url,
            image_url,
            database.now(),
            product_code,
        ))
        conn.commit()


def get_products(database: Any):
    with database.connect() as conn:
        return conn.execute("""
            SELECT *
            FROM makejpc_products
            ORDER BY created_at DESC
        """).fetchall()
