# Pecka.TV pro Kodi

Neoficiální doplněk Kodi pro předplatitele [Pecka.TV](https://www.pecka.tv/) (platforma 4NET.TV).
Není nijak spojen s provozovatelem služby – pro použití je nutné vlastní aktivní předplatné.

## Funkce
- živé vysílání (HLS přes `inputstream.adaptive`, volitelně bez něj)
- archiv pořadů podle kanálu a dne
- export M3U + XMLTV pro **PVR IPTV Simple Client** (ručně i automaticky službou na pozadí)
- kontrola limitu souběžných streamů

## Požadavky
Kodi 21 Omega+ (Python 3), testováno na LibreELEC 12 / Raspberry Pi 4. Bez externích Python závislostí.

## Instalace
1. Stáhni repozitář a zabal složku `plugin.video.peckatv` do zipu
   (`zip -r plugin.video.peckatv.zip plugin.video.peckatv -x '*.pyc' '*__pycache__*'`).
2. V Kodi: *Doplňky → Instalovat ze ZIP souboru*.
3. V nastavení doplňku vyplň **session token** – hodnota `sessionLoginToken` z localStorage
   prohlížeče po přihlášení na `online.pecka.tv` (DevTools → Application → Local Storage).
   Přihlášení e-mailem/heslem je zatím neověřené.

## Stav
- Živé vysílání a EPG: funkční.
- Přehrávání archivu (`StartOffset`) a přihlášení heslem: zatím neověřeno.

## Vývoj
Offline test s mockovanými moduly Kodi a anonymizovanými odpověďmi API:

```
python test/run_test.py
```

Podrobnosti o API a nasazení jsou v [`CLAUDE.md`](CLAUDE.md).

## Licence
MIT
