# Piticko Bot – MakejPC Product Tracker

## 1. Zkopíruj soubory

Zkopíruj obsah balíčku do kořene projektu:

```text
cogs/products.py
services/products/__init__.py
services/products/base.py
services/products/makejpc.py
utils/database.py
```

`utils/database.py` v balíčku je upravená verze souboru, který jsi poslal.
Před přepsáním si udělej jeho zálohu.

## 2. Requirements

Do `requirements.txt` přidej:

```text
beautifulsoup4>=4.12.3
```

`httpx` už v projektu máš.

## 3. Proměnné prostředí

Na NobleHostu nebo v lokálním `.env` nastav:

```env
MAKEJPC_FORUM_CHANNEL_ID=ID_FORUM_KANALU
MAKEJPC_CHECK_INTERVAL_MINUTES=15
MAKEJPC_FIRST_RUN_MODE=seed
MAKEJPC_MENTION_ROLE_ID=0
```

ID kanálu získáš po zapnutí Discord Developer Mode:
pravé tlačítko na forum kanál → Kopírovat ID kanálu.

## 4. Oprávnění bota

V cílovém forum kanálu bot potřebuje:

- Zobrazit kanál
- Odesílat zprávy
- Vytvářet veřejná vlákna
- Odesílat zprávy ve vláknech
- Vkládat odkazy
- Připojovat soubory (doporučeno)

## 5. Načtení cogu

Pokud bot cogy načítá automaticky, nic dalšího není potřeba.

Při ručním načítání přidej do `setup_hook()` v `bot.py`:

```python
await self.load_extension("cogs.products")
```

Případně podle názvu instance:

```python
await bot.load_extension("cogs.products")
```

## 6. První spuštění

Výchozí režim `seed` pouze uloží současnou nabídku do databáze.
Do Discordu se potom budou posílat až nově přidané počítače.

Chceš-li odeslat i současné produkty, nastav před prvním spuštěním:

```env
MAKEJPC_FIRST_RUN_MODE=post_all
```

## 7. Test

Po restartu bota spusť na Discordu:

```text
/makejpc-kontrola
```

Příkaz vyžaduje oprávnění „Spravovat server“.

## Poznámka

Stránka MakejPC je Shoptet a její HTML se může v budoucnu změnit.
Když příkaz napíše, že parser nenašel žádné produkty, bude potřeba upravit
selektory v `services/products/makejpc.py`.
