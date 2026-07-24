# Brokes Bot v2

Discord YouTube notifier připravený pro Wispbytehosting.

## Funkce

- Pouze slash příkazy
- `/ping`, `/status`, `/help`
- `/youtube add`, `/youtube remove`, `/youtube list`, `/youtube check`, `/youtube test`
- YouTube RSS notifikace
- SQLite ochrana proti duplicitám
- Profesionální embedy s tlačítkem
- Logování do konzole i souboru
- `.env` konfigurace
- Kick stream oznámení přes oficiální Kick API a správu v dashboardu
- PC poradna pro návrhy sestav, upgrady a diagnostiku s privátními požadavky

## Instalace lokálně

```bash
pip install -r requirements.txt
```

Zkopíruj `.env.example` na `.env` a vlož token:

```env
TOKEN=tvuj_discord_bot_token
KICK_CLIENT_ID=tvuj_kick_client_id
KICK_CLIENT_SECRET=tvuj_kick_client_secret
```

Kick údaje získáš po vytvoření aplikace na [Kick Dev](https://dev.kick.com/).

Spuštění:

```bash
python bot.py
```

## Wispbytehosting

1. Nahraj celý obsah složky na hosting.
2. Nastav startup command:

```bash
python bot.py
```

3. Nainstaluj knihovny:

```bash
pip install -r requirements.txt
```

4. Vytvoř soubor `.env` s tokenem.

## Rychlejší slash příkazy

V `config.py` můžeš vložit ID svého Discord serveru:

```python
GUILD_ID = 123456789012345678
```

Pak se slash příkazy synchronizují okamžitě jen na tomto serveru.

Pokud necháš:

```python
GUILD_ID = 0
```

příkazy budou globální, ale mohou se objevit později.

## Použití

Přidání YouTube kanálu:

```text
/youtube add url:https://www.youtube.com/@MrBeast channel:#youtube
```

Seznam:

```text
/youtube list
```

Ruční kontrola:

```text
/youtube check
```

Test embedu:

```text
/youtube test channel:#youtube
```

Odebrání:

```text
/youtube remove channel_id:UCxxxxxxxxxxxxxxxxxxxx
```

## Poznámky

- Bot používá RSS, takže nepotřebuje YouTube API klíč.
- Při přidání kanálu se poslední video uloží jako již zpracované, aby bot neposlal starou notifikaci.
- Nová videa se kontrolují podle `YOUTUBE_CHECK_INTERVAL_SECONDS` v `config.py`.
