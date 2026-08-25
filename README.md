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
- PC poradna pro sestavy, upgrady a diagnostiku v soukromých kanálech nebo veřejném fóru
- Dobrovolná podpora provozu přes `/podpora` a externí platební stránku
- Herní nabídky: hry zdarma, DLC, víkendy zdarma a výrazné slevy s filtry obchodů
- Reakční role: členové si bezpečné role sami přidají nebo odeberou reakcí pod panelem

## Instalace lokálně

```bash
pip install -r requirements.txt
```

Zkopíruj `.env.example` na `.env` a vlož token:

```env
TOKEN=tvuj_discord_bot_token
KICK_CLIENT_ID=tvuj_kick_client_id
KICK_CLIENT_SECRET=tvuj_kick_client_secret
SUPPORT_URL=https://tvoje-verejna-stranka.example/podpora
```

Kick údaje získáš po vytvoření aplikace na [Kick Dev](https://dev.kick.com/).

## Přidání bota přes dashboard

Pokud je v `.env` nastavené `DISCORD_CLIENT_ID`, dashboard zobrazí tlačítko
**Přidat bota**. Otevře výhradně oficiální Discord OAuth2 instalační okno se
scopy `bot` a `applications.commands`. Odkaz neobsahuje token bota ani
`DISCORD_CLIENT_SECRET` a nevyžaduje oprávnění Administrátor.

Pro přihlášení do dashboardu jsou navíc nutné `DISCORD_CLIENT_SECRET` a
`DASHBOARD_REDIRECT_URI`, která musí přesně odpovídat Redirect URL nastavené v
Discord Developer Portal.

## Veřejné kolo štěstí

Příkaz `/kolo` pošle odkaz na veřejnou stránku kola pro aktuální Discord
server. Každý může zatočit opakovaně bez přihlášení, bodů, účtů nebo limitu.
Správce serveru upravuje název, popis, barvy, výseče a jejich váhy v dashboardu.
Kolo je jen losovač: výsledek nepřidává Discord role, peníze ani reálné odměny.

Pro odkaz z příkazu nastav v `.env` veřejnou adresu dashboardu:

```env
DASHBOARD_PUBLIC_URL=https://tvoje-domena.example
```

Kolo Discord OAuth2 nepotřebuje. Pro celý dashboard je však HTTPS i tak
silně doporučené, zejména pokud používáš přihlašování správců přes Discord.

## Reakční role

V dashboardu v modulu **Reakční role** nastav kanál, text panelu a dvojice
Unicode emoji + role. Potom na Discordu použij:

```text
/reakcnirole panel
```

Bot přidá reakce k nové zprávě. Přidání reakce dá členovi odpovídající roli;
odebrání reakce mu ji odebere. Po změně nastavení vždy vytvoř nový panel.
Role musí být pod botem a nesmí obsahovat administrativní nebo moderační
oprávnění.

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

## Monitoring dostupnosti bota

Dashboard poskytuje minimalistický endpoint pro externí monitoring:

```text
GET /health/bot
```

- HTTP `200` znamená, že bot odeslal čerstvý heartbeat.
- HTTP `503` znamená, že heartbeat chybí, je starší než 150 sekund nebo není dostupná databáze.

Endpoint nezobrazuje tokeny, logy ani údaje o VPS. Je určený například pro
UptimeRobot nebo jinou službu, která upozorní správce na nedostupnost.

## Automatická záloha PostgreSQL databáze na VPS

Skript `scripts/backup_neon.py` načte `DATABASE_URL` ze souboru `.env`, vytvoří
komprimovanou PostgreSQL zálohu a standardně uchovává posledních 14 dní.
Připojovací údaje nevypisuje do logu.

Ruční kontrola:

```bash
cd ~/piticko-bot
source .venv/bin/activate
python scripts/backup_neon.py
```

Instalace každodenního timeru na VPS:

```bash
sudo cp deploy/systemd/piticko-backup.service /etc/systemd/system/
sudo cp deploy/systemd/piticko-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now piticko-backup.timer
```

Kontrola timeru a poslední zálohy:

```bash
systemctl list-timers piticko-backup.timer --no-pager
sudo systemctl status piticko-backup.service --no-pager
ls -lh backups/database
```

Volitelně lze v `.env` změnit uchování nebo cílovou složku:

```env
DATABASE_BACKUP_RETENTION_DAYS=14
DATABASE_BACKUP_DIR=/home/debian/piticko-bot/backups/database
BACKUP_ALERT_WEBHOOK_URL=https://discord.com/api/webhooks/ID/TAJNY_TOKEN
BACKUP_RCLONE_REMOTE=gdrive:Piticko-Bot-Backups/database
```

`BACKUP_ALERT_WEBHOOK_URL` je volitelný Discord webhook. Skript na něj odešle
zprávu pouze při selhání zálohy. URL je tajná a nesmí se commitnout ani zveřejnit.
Po nastavení lze upozornění bezpečně ověřit bez poškození zálohy:

```bash
python scripts/backup_neon.py --test-alert
```

`BACKUP_RCLONE_REMOTE` je volitelný rclone cíl pro druhou kopii zálohy. Skript
po vytvoření lokální zálohy nahraje nový soubor na Google Drive. Na vzdáleném
úložišti maže pouze soubory `piticko-db-*.dump` starší než nastavená doba
uchování. Systemd služba běží jako uživatel `debian`, proto musí být remote
uložený v jeho `~/.config/rclone/rclone.conf`.

## Použití

Herní nabídky se nastavují v dashboardu nebo příkazem:

```text
/hry nastavit kanal:#herni-nabidky hry_zdarma:ano vikendy:ano dlc:ano slevy:ano minimalni_sleva:60
/hry seznam
/hry role typ:Hry zdarma role:@Hry zdarma
/hry panel kanal:#role
```

`/hry seznam` ukáže aktuální nabídky podle filtrů serveru. Zdroje jsou
GamerPower pro hry zdarma a CheapShark pro slevy; ceny ze CheapShark jsou v USD.

Správce může v dashboardu nebo přes `/hry role` nastavit dobrovolné odběrové
role pro hry zdarma, víkendy, DLC a slevy. Příkaz `/hry panel` odešle tlačítka,
kterými si členové roli sami přidají či odeberou. Bot odmítá role nad sebou a
role s administrativními či moderačními oprávněními.

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

## Návrhy komunity

V dashboardu vyber kanál a zapni modul **Návrhy**. Členové pak použijí
`/navrh poslat` (nebo tlačítko z `/navrh panel`) a odešlou nápad pomocí
formuláře. Komunita hlasuje tlačítky 👍 a 👎. Správce mění stav příkazem
`/navrh stav` na **Zvažujeme**, **Přijato**, **Zamítnuto** nebo **Hotovo**.

- Bot používá RSS, takže nepotřebuje YouTube API klíč.
- Při přidání kanálu se poslední video uloží jako již zpracované, aby bot neposlal starou notifikaci.
- Nová videa se kontrolují podle `YOUTUBE_CHECK_INTERVAL_SECONDS` v `config.py`.
