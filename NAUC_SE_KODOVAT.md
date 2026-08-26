# Jak se učit programovat na Piticko Botovi

Tento návod je určený přímo pro tento projekt. Neuč se jen kopírováním kódu:
u každé změny si nejdřív řekni, **co má udělat**, **kde jsou data** a
**jak ji ověříš**.

## 1. Jak je projekt rozdělený

| Složka nebo soubor | K čemu slouží |
| --- | --- |
| `bot.py` | Spustí Discord bota a automaticky načte moduly ze složky `cogs`. |
| `cogs/` | Funkce bota: slash příkazy, tlačítka, reakce a Discord události. |
| `utils/database.py` | Společné rozhraní pro práci s databází. |
| `utils/db/` | Konkrétní databázové dotazy pro jednotlivé moduly. |
| `utils/db/migrations.py` | Tabulky databáze. Novou tabulku přidávej pro PostgreSQL i SQLite. |
| `dashboard/` | Webový dashboard a jeho HTML šablony. |
| `tests/` | Automatické testy důležitých částí. |
| `.env` | Tajné hodnoty, například token bota. Tento soubor nikdy neposílej na GitHub. |

## 1.1 Úplné základy Pythonu

Program je jen velmi přesný návod pro počítač. Počítač neodhadne, co jsi
„asi myslel“, proto je lepší psát jednoduchý kód po malých krocích.

### Proměnné

Proměnná je pojmenovaná krabička na hodnotu:

```python
jmeno = "Piticko"
pocet_clenu = 120
bot_bezi = True
```

- Text v uvozovkách je `str` (string).
- Celé číslo je `int`.
- `True` a `False` jsou logické hodnoty (`bool`).
- Název proměnné piš anglicky, malými písmeny a s podtržítkem:
  `channel_id`, `member_count`, `is_enabled`.

```python
pozdrav = "Ahoj " + jmeno
zprava = f"Na serveru je {pocet_clenu} členů."
```

`f"..."` je pohodlný způsob, jak vložit proměnnou do textu.

### Seznamy a slovníky

Seznam obsahuje více hodnot v pořadí:

```python
barvy = ["červená", "modrá", "zelená"]
prvni_barva = barvy[0]
```

Číslování začíná od nuly. `barvy[0]` je tedy `"červená"`.

Slovník spojuje název s hodnotou:

```python
nastaveni = {
    "enabled": True,
    "channel_id": 123456789,
}

if nastaveni["enabled"]:
    print("Modul je zapnutý")
```

V tomto projektu se nastavení modulu často vrací právě jako slovník.

### Podmínky

Podmínka rozhoduje, kterou větev programu použít:

```python
if pocet_clenu >= 100:
    print("Velký server")
else:
    print("Menší server")
```

Pozor na dvojtečku `:` a odsazení. Co je odsazené čtyřmi mezerami, patří do
podmínky. Bez správného odsazení Python kód nespustí nebo udělá něco jiného,
než čekáš.

Užitečné porovnání:

| Zápis | Význam |
| --- | --- |
| `==` | je stejné jako |
| `!=` | není stejné jako |
| `>` / `<` | je větší / menší než |
| `>=` / `<=` | je větší nebo rovno / menší nebo rovno |
| `and` | platí obě podmínky |
| `or` | platí alespoň jedna podmínka |
| `not` | obrátí hodnotu |

### Funkce

Funkce je pojmenovaný kus programu, který můžeš použít opakovaně:

```python
def pozdrav_uzivatele(jmeno: str) -> str:
    return f"Ahoj, {jmeno}!"

text = pozdrav_uzivatele("Petr")
```

- `def` začíná běžnou funkci.
- `jmeno` je vstup funkce.
- `return` vrátí výsledek.
- `: str` a `-> str` jsou nápovědy typu. Začátečník je nemusí umět, ale
  pomáhají poznat, co funkce očekává a vrací.

### Smyčky

Smyčka provede stejný postup pro každou položku:

```python
role = ["YouTube", "Slevy", "Linux"]

for nazev_role in role:
    print(nazev_role)
```

Ve tvém botovi se takto projdou například role z reakčního panelu nebo
uložené návrhy z databáze.

### Importy

Import připojí kód z jiného souboru nebo knihovny:

```python
import discord
from config import EMBED_COLOR
```

První řádek zpřístupní knihovnu Discordu. Druhý načte konkrétní hodnotu z
`config.py`. Když vidíš chybu `ModuleNotFoundError`, Python danou knihovnu
nezná nebo není nainstalovaná ve virtuálním prostředí.

### Třídy a `self`

Třída seskupuje kód, který spolu souvisí. Discord modul je například třída:

```python
class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
```

`self` znamená „tento konkrétní modul“. Díky `self.bot` mají příkazy přístup
k běžícímu botovi. Zatím si stačí zapamatovat: u metod uvnitř třídy je `self`
první parametr a neodstraňuje se.

### `async` a `await`

Discord komunikuje přes internet. Zatímco bot čeká na odpověď Discordu, nesmí
zastavit všechny ostatní příkazy. Proto se u Discord operací používá:

```python
async def muj_prikaz(self, interaction: discord.Interaction):
    await interaction.response.send_message("Hotovo")
```

Praktické pravidlo: když voláš Discord nebo síťovou operaci a příklad v
projektu před ní má `await`, nech tam `await` také. Funkce, ve které používáš
`await`, musí začínat `async def`.

### Chyby jsou normální

Chyba není důkaz, že na programování nemáš. Je to informace, kde program
narazil. Čti traceback zdola nahoru:

1. Poslední řádek říká typ chyby a důvod.
2. Řádek nad ním ukazuje soubor a číslo řádku.
3. Oprav pouze příčinu, nezkoušej naslepo mazat části kódu.

Příklady:

- `SyntaxError` — překlep, chybí dvojtečka, závorka nebo odsazení.
- `NameError` — používáš název, který nebyl vytvořen.
- `AttributeError` — objekt nemá vlastnost nebo metodu, kterou voláš.
- `KeyError` — slovník nemá požadovaný klíč.
- `discord.Forbidden` — bot nemá oprávnění k dané akci.

Když chybu posíláš k řešení, pošli celý traceback jako text a nikdy do něj
nevkládej tajné klíče nebo obsah `.env`.

## 2. Bezpečný postup při každé změně

1. Vytvoř malou změnu, ne deset funkcí najednou.
2. Ulož soubory.
3. Zkontroluj Python syntaxi.
4. Otestuj funkci na svém testovacím Discord serveru.
5. Až potom změnu commitni a pošli na GitHub.
6. Nakonec aktualizuj VPS a zkontroluj log.

Nikdy nedávej do zprávy, commitu ani na screenshot:

- `TOKEN`,
- `DATABASE_URL`,
- `DISCORD_CLIENT_SECRET`,
- obsah `.env`,
- soukromý SSH klíč bez přípony `.pub`.

## 3. První vlastní slash příkaz

Otevři `cogs/general.py`. V této třídě už jsou příkazy jako `/ping` a
`/status`.

Příklad jednoduchého příkazu:

```python
@app_commands.command(name="ahoj", description="Pozdraví uživatele.")
async def ahoj(self, interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Ahoj {interaction.user.mention}! 👋"
    )
```

### Co znamenají jednotlivé části

- `@app_commands.command(...)` říká Discordu, že jde o slash příkaz.
- `name="ahoj"` je název příkazu: `/ahoj`.
- `description=...` se zobrazí uživatelům v Discordu.
- `async def` vytváří asynchronní funkci. Discord operace mohou chvíli trvat,
  proto se používá `async` a `await`.
- `self` odkazuje na modul (`Cog`), ve kterém příkaz je.
- `interaction` obsahuje uživatele, kanál a server, kde byl příkaz použit.
- `interaction.response.send_message(...)` odešle odpověď.

V metodách uvnitř `class General` musí být každý řádek odsazený **čtyřmi
mezerami**. Python používá odsazení místo složených závorek.

## 4. Cvičení: `/serverinfo`

Zkus do `cogs/general.py` přidat příkaz, který ukáže název serveru, počet
členů a počet kanálů.

```python
@app_commands.command(
    name="serverinfo",
    description="Zobrazí základní informace o serveru.",
)
async def serverinfo(self, interaction: discord.Interaction):
    guild = interaction.guild

    if guild is None:
        await interaction.response.send_message(
            "❌ Tento příkaz funguje pouze na Discord serveru.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title=f"🏠 {guild.name}",
        description="Základní informace o serveru.",
        color=EMBED_COLOR,
    )
    embed.add_field(name="Členů", value=str(guild.member_count))
    embed.add_field(name="Kanálů", value=str(len(guild.channels)))
    embed.add_field(name="Vlastník", value=f"<@{guild.owner_id}>")

    await interaction.response.send_message(embed=embed)
```

Než kód uložíš, zkus si odpovědět:

1. Proč se kontroluje `guild is None`?
2. Proč je `guild.member_count` převedeno pomocí `str(...)`?
3. Co se změní, když u `send_message` použiješ `ephemeral=True`?

## 5. Embedy

Embed je zpráva v rámečku. Typicky má název, popis, barvu a pole.

```python
embed = discord.Embed(
    title="📢 Důležité oznámení",
    description="Text, který má být přehledný.",
    color=EMBED_COLOR,
)
embed.add_field(name="Kdy", value="Dnes večer", inline=True)
embed.add_field(name="Kde", value="#oznámení", inline=True)
embed.set_footer(text="Piticko Bot")
```

Omezení Discordu jsou důležitá: název má maximálně 256 znaků, popis 4096 a
celý embed 6000 znaků. Dlouhé texty vždy zkracuj.

## 6. Oprávnění

Příkaz pro správce chraň dekorátorem:

```python
@app_commands.checks.has_permissions(manage_guild=True)
```

To neznamená, že bot automaticky má všechna oprávnění. Před akcí vždy ověř:

- zda bot vidí kanál,
- zda do něj může psát,
- zda je role bota výš než role, kterou chce přidat,
- zda akce není nebezpečná.

Například role s oprávněním administrátora se nikdy nemá rozdávat tlačítkem
nebo reakcí.

## 7. Databáze

Data, která musí přežít restart bota, nepatří jen do proměnné v Pythonu.
Ulož je do databáze.

Správný postup pro nový modul:

1. Přidej tabulky do `utils/db/migrations.py` pro PostgreSQL i SQLite.
2. Vytvoř soubor například `utils/db/moje_funkce.py` s SQL dotazy.
3. Přidej metody do `utils/database.py`.
4. Použij je v `cogs/moje_funkce.py`.
5. Napiš test do `tests/`.

Nápovědou jsou moduly `utils/db/reaction_roles.py` a
`utils/db/suggestions.py`.

## 8. Dashboard

Dashboard má tři hlavní části:

- `dashboard/templates/server.html` — co uživatel vidí.
- `dashboard/app.py` — URL stránky a ukládání formulářů.
- `dashboard/storage.py` — načtení uloženého nastavení pro zobrazení.

Když přidáváš nastavení modulu, potřebuješ zpravidla změnit všechny tři
soubory. Formulář sám o sobě nic neuloží, dokud pro něj nevytvoříš `POST`
route v `dashboard/app.py`.

## 9. Test před commitem

V PowerShellu ve složce projektu můžeš ověřit změněné Python soubory:

```powershell
python -m compileall cogs\general.py
git diff --check
git status
```

Pokud projekt používá virtuální prostředí, aktivuj ho před spuštěním testů.
Necommituj soubory, kterým nerozumíš, ani změny, které jsi netestoval.

## 10. Nasazení na VPS

Nejdřív proveď commit a push z počítače. Pak se připoj na VPS:

```powershell
ssh -i "$env:USERPROFILE\.ssh\piticko_vps_ed25519" debian@57.131.140.115
```

Na VPS aktualizuj projekt a restartuj služby:

```bash
cd ~/piticko-bot
git pull
sudo systemctl restart piticko-bot piticko-dashboard
sudo systemctl status piticko-bot piticko-dashboard --no-pager
```

Log bota zobrazíš takto:

```bash
sudo journalctl -u piticko-bot -f
```

Ukončíš ho klávesami `Ctrl + C`. Služba bota tím neskončí, ukončí se pouze
živé zobrazování logu.

## 11. Další cvičení

Zkus postupně vytvořit:

1. `/kostka` — pošle náhodné číslo 1 až 6.
2. `/avatar` — zobrazí avatar uživatele, který příkaz použil.
3. `/pravidla` — odešle předpřipravený embed s pravidly.
4. `/navrh info` — ukáže stav konkrétního návrhu.

U každého příkazu nejdřív napiš obyčejnou větu: „Po použití příkazu se má
stát…“ Teprve potom začni psát kód.
