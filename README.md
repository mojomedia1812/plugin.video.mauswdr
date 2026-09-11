# MausWDR

Kodi-Addon fuer Videos auf wdrmaus.de.

Entwickler: m0j01812

## Funktionen

- listet Sachgeschichten, Lachgeschichten, Mausspots und Lieder
- bietet die gewuenschten ALLE-/NEU-/Kategorie-Menues an
- bietet eine Jahresansicht ueber alle vier Bereiche
- loest pro Detailseite den WDR-On-Demand-JSONP-Endpunkt auf
- spielt den HLS-Stream in Kodi ab
- enthaelt Icon, Fanart, mehrsprachige Addon-Beschreibung und Disclaimer

## Installation

Die aktuelle ZIP-Datei kann in Kodi ueber `Add-ons > Aus ZIP-Datei installieren` installiert werden.

Release:
https://github.com/mojomedia1812/plugin.video.mauswdr/releases/latest

Alternativ kann der Ordner `plugin.video.mauswdr` direkt als Addon-Verzeichnis genutzt werden.

## Entwicklung

Parser-Tests ausfuehren:

```bash
python -m unittest discover -s tests
```

## Quelle

Die Listen stammen von:
https://www.wdrmaus.de/filme/sachgeschichten/index.php5?filter=alle
https://www.wdrmaus.de/filme/lachgeschichten/index.php5?filter=alle
https://www.wdrmaus.de/filme/mausspots/index.php5?filter=alle
https://www.wdrmaus.de/filme/lieder/index.php5?filter=alle

Die Detailseiten enthalten ein `data-extension-ard`-Attribut, das auf einen WDR-On-Demand-Endpunkt verweist. Dieser liefert die eigentliche HLS-URL.
