# Pecka.TV pro Kodi

Neoficiální doplněk Kodi pro předplatitele [Pecka.TV](https://www.pecka.tv/) (platforma 4NET.TV).
Není nijak spojen s provozovatelem služby – pro použití je nutné vlastní aktivní předplatné.

## Funkce
- živé vysílání (HLS přes `inputstream.adaptive`, volitelně bez něj)
- archiv pořadů podle kanálu a dne
- **nahrávky** (nPVR) – přehrání, stav naplánovaných, mazání přes kontextové menu
- **plánování nahrávek** – *Program a nahrávání* (7 dní dopředu): kliknutím na pořad *Nahrát*
  nebo *Nahrávat všechny díly*; totéž v kontextovém menu u živého vysílání a v archivu;
  sériová nahrávání lze zrušit v *Nahrávky → Sériová nahrávání*
- export M3U + XMLTV pro **PVR IPTV Simple Client** (ručně i automaticky službou na pozadí)
- kontrola limitu souběžných streamů

## Požadavky
Kodi 21 Omega+ (Python 3), testováno na LibreELEC 12 / Raspberry Pi 4. Bez externích Python závislostí.

## Instalace
1. Stáhni `plugin.video.peckatv-<verze>.zip` z [Releases](https://github.com/arow44/peckatv-kodi/releases).
2. V Kodi povol *Nastavení → Systém → Doplňky → Neznámé zdroje*.
3. *Doplňky → Instalovat ze ZIP souboru* → vyber stažený zip.
4. V nastavení doplňku vyplň **session token** – hodnota `sessionLoginToken` z localStorage
   prohlížeče po přihlášení na `online.pecka.tv` (DevTools → Application → Local Storage).
   Přihlášení e-mailem/heslem je zatím neověřené.
5. Při prvním spuštění se Kodi automaticky spáruje jako nové zařízení „Kodi (<hostname>)“
   – na účtu musí být volné místo pro zařízení.

## TV a programový průvodce (PVR IPTV Simple Client)
Doplněk umí vygenerovat seznam kanálů (M3U) a program (XMLTV), ze kterých
**PVR IPTV Simple Client** udělá v Kodi plnohodnotnou sekci *TV* – průvodce, přepínání kanálů
a archiv přímo z průvodce.

1. **Export z doplňku** – *Pecka.TV → Nastavení → IPTV Simple*:
   - zapni *Automaticky generovat M3U a EPG* (obnova podle *Interval obnovy*, výchozí 12 h),
   - *Cílová složka*: doporučujeme viditelné místo, např. `/storage/peckatv/`
     (výchozí `special://profile/addon_data/…` leží ve skryté složce `.kodi`),
   - *EPG dní zpět / dopředu*: na Raspberry Pi drž rozsah menší (např. 2 / 2), průvodce se načte rychleji,
   - klikni na *Vygenerovat teď* a počkej na hlášku „Hotovo: N kanálů“.
2. **Instalace klienta** – *Doplňky → Instalovat z repozitáře → Klienti PVR → PVR IPTV Simple Client*.
3. **Nastavení klienta** – *Doplňky → Moje doplňky → Klienti PVR → PVR IPTV Simple Client → Nastavit*:
   - *Obecné*: Umístění **Místní cesta**, Cesta k M3U → `peckatv.m3u`
   - *EPG*: Umístění **Místní cesta**, Cesta k XMLTV → `peckatv.xml`
   - *Catchup*: **Povolit catchup** (odkazy na archiv už M3U obsahuje)
4. Restartuj Kodi. V hlavním menu (Estuary) se objeví **TV**; pokud ne, zapni ji v
   *Nastavení → Vzhled → Konfigurovat vzhled → Položky hlavního menu*.

**Průvodce je prázdný?**
- Vygeneruj soubory znovu (*Vygenerovat teď*) a zkontroluj, že `peckatv.xml` obsahuje pořady
  (`grep -c "<programme" peckatv.xml` přes SSH).
- Kodi si EPG ukládá do své databáze – po změně souborů dej
  *Nastavení → PVR a živá TV → Obecné → Vymazat data*.
- Nevidíš soubory při výběru cesty? Zapni *Nastavení → Média → Obecné → Zobrazit skryté soubory*,
  nebo změň cílovou složku exportu (viz výše).

## Stav
- Živé vysílání, archiv a EPG / IPTV Simple: funkční.
- Nahrávky a jejich plánování (0.2.0–0.3.0): podle API webové aplikace, ověřeno offline testem.
- Přihlášení e-mailem/heslem: zatím neověřeno.

## Řešení problémů
Log je v `/storage/.kodi/temp/kodi.log` (nebo síťová složka `\\LIBREELEC\Logfiles`):

```
grep peckatv /storage/.kodi/temp/kodi.log | tail -n 50
```

Neúspěšné požadavky na API se logují včetně endpointu a odpovědi serveru (bez tokenu).

## Vývoj
Offline test s mockovanými moduly Kodi a anonymizovanými odpověďmi API:

```
python test/run_test.py
```

Podrobnosti o API a nasazení jsou v [`CLAUDE.md`](CLAUDE.md).

## Licence
MIT
