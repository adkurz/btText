# Änderungsprotokoll für btText

## [Unveröffentlicht]

- Geändert: Große Textbausteinlisten werden jetzt schneller sortiert, indem die Sortierschlüssel für Gewicht und Name einmal pro Vorgang vorbereitet werden. Die bisherige Sortierreihenfolge, Auswahl und der Fokus bleiben erhalten.

- Geändert: Große Markdown-Textbausteine mit vielen Absätzen werden jetzt schneller in Form von reinem Text aufbereitet. Zeilenumbrüche und Einrückungen bleiben dabei erhalten.

- Geändert: Beim Kopieren, Verschieben oder Löschen mehrerer Textbausteine werden der Kategorienbaum und die Hotstrings jetzt nur einmal pro Vorgang aktualisiert. Wiederholte vollständige Neuladungen für jeden einzelnen Textbaustein entfallen.

- Behoben: Fehlerhafte oder nicht lesbare Einstellungen setzen die Datenbankauswahl und Datenschutzeinstellungen nicht mehr zurück. btText meldet den Fehler und beendet sich, ohne die Einstellungsdatei zu überschreiben.

- Behoben: Verzögerte Hotstring-Erweiterungen werden jetzt abgebrochen, wenn Sie weitertippen oder das Zieleingabefeld wechseln. Dadurch werden zwischenzeitlich eingegebener Text und Inhalte anderer Eingabefelder nicht mehr ersetzt.

- Behoben: Die Schaltflächen zum Kopieren des Pfads, Öffnen des Ordners und Schließen des Datenbankpfad-Dialogs werden jetzt ohne Überlappungen angeordnet.

- Behoben: Hotstrings behalten jetzt das ursprünglich eingegebene Satzzeichen bei, auch wenn Modifikatortasten während einer Variablenabfrage losgelassen werden. Beim Abbrechen der Abfrage wird ebenfalls das richtige Zeichen wiederhergestellt.

- Behoben: Eine beim Beenden eines Hotstrings mit Satzzeichen wie ? noch gedrückte Umschalttaste verändert die Einfügetastenkombination nicht mehr. Dadurch wird kein Steuerzeichen mehr anstelle des Textbausteins eingefügt.

- Behoben: Wenn das Einfügen eines Textbausteins oder eine Hotstring-Erweiterung fehlschlägt und sich der vorherige Zwischenablageinhalt nicht sofort wiederherstellen lässt, versucht btText die Wiederherstellung jetzt automatisch erneut. Neue Zwischenablageinhalte anderer Anwendungen bleiben dabei erhalten.

- Behoben: Datenbanken mit fehlenden Pflichtspalten werden jetzt beim Öffnen mit einer Fehlermeldung abgewiesen, die die fehlenden Spalten nennt. Dadurch scheitert btText nicht mehr beim Aufbau des Hauptfensters. Anschließend kann eine andere Datenbank ausgewählt werden.

- Behoben: Drag-and-drop akzeptiert jetzt nur aktive interne Verschiebevorgänge für Kategorien und Textbausteine. Aus anderen Anwendungen gezogener Text kann keine unbeabsichtigten Verschiebungen oder Fehler mehr auslösen.

- Behoben: Hotstrings mit mehr als 256 Zeichen werden beim Speichern jetzt mit einer verständlichen Fehlermeldung abgewiesen. Dadurch lassen sich keine Kürzel mehr speichern, die nicht erweitert werden können. Die Eingaben im Editor bleiben zur Korrektur erhalten.

## [v1.3.0] 25.10.2026

- Hinzugefügt: Textbausteine können nun optional mit einfachem Markdown formatiert werden. Beim Einfügen werden sie nicht nur als Reintext, sondern auch als HTML und RTF ausgegeben, sodass die Formatierung beibehalten wird, sofern sie vom Zielprogramm unterstützt wird. Dies ermöglicht einfache Formatierungen (Fettdruck, Kursivschrift usw.), Links und Zitate.

- Geändert: Update auf Python 3.15.

- Geändert: Update der Abhängigkeiten.

- Geändert: Auf UPX zur Kompression der Programmdateien wird zu Gunsten einer höheren Geschwindigkeit verzichtet.

- Behoben: Die Datenschutzeinstellungen für den Windows-Zwischenablageverlauf und die Cloud-Synchronisierung werden jetzt auch bei Fehlern beim Kopieren oder Einfügen eingehalten.

- Behoben: Prozentzeichen im Datenbankpfaden lösen keine unerwarteten Probleme mehr aus.

- Behoben: Bei aktivierten Hotstrings wurden Akzentzeichen wie ´ doppelt eingefügt, statt mit dem folgenden Buchstaben kombiniert zu werden (z. B. zu é).

- Behoben: Ein Timing-Fehler beim Einfügen von Textbausteinen konnte dazu führen, dass neue Zwischenablageinhalte anderer Anwendungen verloren gingen und durch ältere Inhalte ersetzt wurden.

- Behoben: Der Installer kann nun nicht mehr versehentlich portable Versionen von btText aktualisieren, was zu Datenverlust führen konnte.

## [v1.2.1] 23.08.2026

- Verbessert: Der Installer achtet nun darauf, das btText nicht in einen bereits vorhandenen Ordner installiert wird, welcher nicht btText selbst enthält. Neuinstallation und Aktualisierungen sind weiterhin problemlos möglich.

- Behoben: Hotstrings sind nun zuverlässiger bei verschiedenen Systemereignissen, beim Wechsel von Fenstern und im Zusammenhang mit Modifikatortasten (STRG, Alt, Umschalt).

- Behoben: Das Einfügen in andere Anwendungen prüft nun zuverlässig, ob das Fenster noch existiert.

- Behoben: Beim Ändern der globalen Tastenkombination wurde unter Umständen ein irreführender Fehler angezeigt.

## [v1.2] 22.08.2026

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
