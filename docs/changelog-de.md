# Änderungsprotokoll für btText

## [Unveröffentlicht] 

- Hinzugefügt: Der Dialog **Variable einfügen** zeigt jetzt, sofern möglich, eine Vorschau der aktuell ausgewählten Variable an.

- Hinzugefügt: Es existiert nun eine Einstellung, um einen Sound bei der Erweiterung eines Hotstrings abzuspielen.

- Geändert: Der Installer verwendet nun NSIS, ein Upgrade ist problemlos möglich.

- Behoben: Ist die Sprache auf den Systemstandard festgelegt, werden Sprachabhängige Variablen, etwa Datum und Uhrzeit, in der aktuell eingestellten Sprache des Betriebssystems ausgegeben, auch wenn noch keine passende btText-Übersetzung existiert.

## [v1.1] 10.08.2026

- Hinzugefügt: Neues Variablensystem, um bestimmte Werte, wie Datum, Uhrzeit oder interaktiv abgefragte Werte, beim Einfügen von Textbausteinen automatisch auszufüllen. Weitere Informationen sind im Benutzerhandbuch nachzuschlagen.

- Hinzugefügt: Der Name der aktiven Datenbank wird jetzt in der Titelleiste angezeigt.

- Hinzugefügt: Der vollständige Pfad der aktiven Datenbank kann jetzt im Datei-Explorer angezeigt, kopiert und geöffnet werden.

- Hinzugefügt: Einstellung des Installationsprogramms, um btText nach der Anmeldung automatisch zu starten.

- Geändert: Die Suche berücksichtigt nun auch Hotstrings.

- Behoben: Hotstring-Erweiterung bei nicht verfügbaren Zwischenablageformaten ist nun möglich.

- Behoben: Hotstring-Erweiterungen und andere temporäre Einfügevorgänge werden jetzt zuverlässig daran gehindert, im Windows-Zwischenablageverlauf gespeichert oder über die Cloud-Zwischenablage synchronisiert zu werden. Die Datenschutzeinstellungen der Zwischenablage gelten nur, wenn Textbausteine explizit über das Kontextmenü oder Strg+Umschalt+C kopiert werden.

- Behoben: Wenn die Liste der Textbausteine nach dem Ändern einer Kategorie fokussiert wird, erhält der erste Listeneintrag jetzt korrekt den Fokus.

- Behoben: Das Installationsprogramm kann btText jetzt für ein Upgrade schließen.

## [v1.0] 02.08.2026

Erste Version
