Dashboard cleanup v1

- Globalni /youtube a /welcome uz se nepouzivaji.
- /youtube presmeruje na prvni dostupny server: /guild/<guild_id>/youtube.
- /welcome presmeruje na prvni dostupny server: /guild/<guild_id>/welcome.
- Leve menu ukazuje YouTube/Welcome jen po vyberu konkretniho serveru.
- Hlavni dashboard slouzi jako vyber serveru.

Muzes smazat:
- dashboard/templates/youtube.html
- dashboard/templates/welcome.html
