# Piticko Bot – návod pro VPS

Tento návod slouží pro správu VPS s Debianem, na kterém běží Piticko Bot,
webový dashboard, lokální PostgreSQL databáze a automatické zálohy.

## Přihlášení na VPS

1. Otevři ve Windows **PowerShell**.
2. Vlož tento příkaz:

```powershell
ssh -i "$env:USERPROFILE\.ssh\piticko_vps_ed25519" debian@57.131.140.115
```

3. Napiš heslo k SSH klíči (*passphrase*).

> Toto není heslo k Discordu, GitHubu ani OVH účtu. Při psaní se v terminálu
> nezobrazují znaky hesla – je to normální.

Po úspěšném přihlášení uvidíš přibližně:

```text
debian@vps-93ccb780:~$
```

Odhlášení z VPS:

```bash
exit
```

## Rychlá kontrola bota

```bash
sudo systemctl status piticko-bot --no-pager
```

Správný stav je:

```text
Active: active (running)
```

Pokud bot neběží, spusť nebo restartuj ho:

```bash
sudo systemctl restart piticko-bot
sudo systemctl status piticko-bot --no-pager
```

## Logy bota

Posledních 100 řádků logu:

```bash
sudo journalctl -u piticko-bot -n 100 --no-pager
```

Živé logy – nové zprávy se ukazují průběžně:

```bash
sudo journalctl -u piticko-bot -f
```

Živé logy ukončíš klávesami **Ctrl + C**. Tím bot nevypneš, jen přestaneš
sledovat výpis.

## Aktualizace bota z GitHubu

Toto použij po každém commitu a pushi na GitHub:

```bash
cd ~/piticko-bot
git pull
sudo systemctl restart piticko-bot
sudo systemctl status piticko-bot --no-pager
```

Pokud poslední příkaz ukáže `active (running)`, aktualizace proběhla správně.

## Aktualizace dashboardu

Pokud se změnily soubory v `dashboard/`, po běžné aktualizaci bota spusť také:

```bash
sudo systemctl restart piticko-dashboard
sudo systemctl status piticko-dashboard --no-pager
```

Logy dashboardu:

```bash
sudo journalctl -u piticko-dashboard -n 100 --no-pager
```

## Změna proměnných v `.env`

Soubor `.env` obsahuje tajné údaje, například token bota a připojení k databázi.
Nikdy jej neposílej do Discordu, na GitHub ani do screenshotu.

Otevření souboru:

```bash
cd ~/piticko-bot
nano .env
```

Uložení v editoru Nano:

1. `Ctrl + O`
2. `Enter`
3. `Ctrl + X`

Po změně `.env` restartuj službu, která proměnnou používá:

```bash
sudo systemctl restart piticko-bot
sudo systemctl restart piticko-dashboard
```

Nemusíš restartovat obě služby, pokud jsi měnil proměnnou používanou jen jednou
z nich. Když si nejsi jistý, restart obou je bezpečný.

## Kontrola automatických záloh databáze

Další plánovaná záloha:

```bash
systemctl list-timers piticko-backup.timer --no-pager
```

Lokální zálohy na VPS:

```bash
ls -lh ~/piticko-bot/backups/database
```

Zálohy na Google Drive:

```bash
rclone lsl gdrive:Piticko-Bot-Backups/database
```

Ruční spuštění zálohy:

```bash
sudo systemctl start piticko-backup.service
sudo systemctl status piticko-backup.service --no-pager
```

Po úspěchu uvidíš `status=0/SUCCESS` nebo zprávu o vytvořené záloze.

## Aktualizace systému Debian

Nejdřív pouze zkontroluj dostupné aktualizace:

```bash
sudo apt update
apt list --upgradable
```

Pokud jsou aktualizace k dispozici, nainstaluj je:

```bash
sudo apt upgrade
```

Když se instalace zeptá na potvrzení, napiš `y` a stiskni Enter.

Po větší aktualizaci, hlavně jádra Linuxu, může být nutný restart VPS:

```bash
sudo reboot
```

SSH spojení se tím ukončí. Počkej přibližně jednu až dvě minuty a znovu se
přihlas. Bot i dashboard se mají spustit samy.

## Doporučená kontrola

| Jak často | Co udělat |
| --- | --- |
| Po každé změně kódu | `git pull` a restartovat upravenou službu. |
| Jednou týdně | Ověřit stav bota příkazem `sudo systemctl status piticko-bot --no-pager`. |
| Jednou za 1–2 týdny | Zkontrolovat systémové aktualizace pomocí `sudo apt update`. |
| Jednou měsíčně | Ověřit, že se zálohy objevují na Google Drive. |

## Nejdůležitější příkazy

```bash
# Stav bota
sudo systemctl status piticko-bot --no-pager

# Restart bota
sudo systemctl restart piticko-bot

# Živé logy bota
sudo journalctl -u piticko-bot -f

# Aktualizace kódu z GitHubu
cd ~/piticko-bot && git pull

# Stav dashboardu
sudo systemctl status piticko-dashboard --no-pager

# Kontrola dalších záloh
systemctl list-timers piticko-backup.timer --no-pager
```
