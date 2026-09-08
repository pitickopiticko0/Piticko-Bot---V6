# Piticko Bot — souhrn projektu

Aktualizováno: 5. 9. 2026

Piticko Bot je Discord bot pro komunitní server. Běží nepřetržitě na VPS společně s webovým dashboardem a databází PostgreSQL.

## Co bot umí

- Welcome zprávy pro nové členy, včetně embedu, soukromé zprávy a automatické role.
- Reakční role: člen si kliknutím vybere zájmové role a tím získá přístup k příslušným kanálům.
- AntiSpam, moderaci, warny, timeouty, kicky, bany a ModLogy.
- Tickety a PC poradnu.
- Návrhy komunity s hlasováním a stavem návrhu.
- Giveawaye, počítání oveček, kolo štěstí a PC build výzvy.
- YouTube, Twitch a Kick oznámení.
- Hry zdarma a slevy z vybraných obchodů; v dashboardu lze vybrat zdroje a minimální slevu.
- Sledování hotových PC sestav z MakejPC a SestavSiPočítač. Bot pro každou sestavu vytvoří a následně aktualizuje fórum vlákno.
- ABI Rank pro evidenci a schvalování herních ranků.
- Diagnostiku serveru a stav API.

## Dashboard

Dashboard je webová správa bota. Přihlašuješ se přes Discord OAuth a můžeš spravovat jen servery, na kterých máš oprávnění.

V dashboardu nastavíš kanály, role, texty zpráv, jednotlivé moduly a jejich zapnutí. Dashboard běží na vlastní adrese VPS za Nginxem a HTTPS.

## Plánovaná oznámení

V dashboardu je modul **Plánovaná oznámení**.

1. Vybereš textový kanál.
2. Napíšeš nadpis, text, barvu a datum s časem.
3. Bot oznámení uloží do databáze a po nastaveném čase ho pošle jako embed.
4. Oznámení lze před odesláním upravit nebo zrušit.

Čas se zadává v časové zóně nastavené pro server, běžně `Europe/Prague`. Bot kontroluje termíny každých 30 sekund. V plánovaných zprávách jsou záměrně vypnuté hromadné zmínky `@everyone` a role, aby se nedaly omylem pingnout všichni členové.

## Provoz na VPS

Na VPS běží tyto důležité služby:

- `piticko-bot` — samotný Discord bot.
- `piticko-dashboard` — webový dashboard.
- `piticko-backup.timer` — denní záloha databáze.
- PostgreSQL — databáze bota.
- Nginx — webový server a HTTPS proxy.

Stav bota ověříš příkazem:

```bash
sudo systemctl status piticko-bot --no-pager
```

Živý log bota zobrazíš takto:

```bash
sudo journalctl -u piticko-bot -f
```

Podrobný postup pro přihlášení, aktualizace, kontrolu služeb a záloh je v souboru [VPS_NAVOD.md](VPS_NAVOD.md).

## Zálohy

Databáze se zálohuje každý den do složky `backups/database` a kopíruje se na Google Drive přes `rclone`.

Kontrola posledních záloh na Google Drivu:

```bash
rclone lsl gdrive:Piticko-Bot-Backups/database
```

## Bezpečnost

Do GitHubu nikdy nepatří:

- obsah souboru `.env`,
- Discord token bota,
- `DASHBOARD_SECRET_KEY`,
- OAuth Client Secret,
- soukromý SSH klíč ani jeho heslo,
- přístupové tokeny Google Drive.

Samotný příkaz SSH, veřejná IP adresa VPS nebo prompt typu `debian@vps-...` nejsou tajné údaje. Soukromý klíč v souboru `.ssh` tajný je.

## Běžné nasazení změn

Po nahrání změn na GitHub se na VPS obvykle provede:

```bash
cd ~/piticko-bot
git pull
sudo systemctl restart piticko-bot piticko-dashboard
sudo systemctl status piticko-bot piticko-dashboard --no-pager
```

Pokud se měnil pouze bot, stačí restartovat `piticko-bot`. Pokud se měnil pouze dashboard, stačí restartovat `piticko-dashboard`.
