# Piticko Bot v0.9.0 – Giveaway

Nové soubory:

- `cogs/giveaway.py`
- `services/giveaway_service.py`
- `ui/__init__.py`
- `ui/giveaway_views.py`

Bot načítá `cogs/giveaway.py` automaticky, takže `bot.py` není potřeba měnit.
Databázové tabulky se vytvoří automaticky při startu.

## Příkazy

- `/giveaway create`
- `/giveaway end`
- `/giveaway reroll`
- `/giveaway delete`
- `/giveaway list`
- `/giveaway info`

## Nasazení

```bash
git add cogs/giveaway.py services/giveaway_service.py ui GIVEAWAY_INSTALL.md
git commit -m "feat(giveaway): add complete giveaway system"
git push
```

Potom restartuj bota.
