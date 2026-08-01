# btText – Benutzerhandbuch

btText ist eine Windows-Anwendung zum Verwalten und schnellen Einfügen von häufig verwendeten Texten. Diese Texte werden in einer SQLite-Datenbank als **Textbausteine** gespeichert. Kategorien, die Suche, Tastenkürzel und optionale Hotstrings helfen dabei, den passenden Text schnell zu finden.

Die Anleitung richtet sich an Endnutzer der kompilierten Windows-Version. Für die Ausführung aus dem Quellcode gelten andere Voraussetzungen; sie wird hier nicht beschrieben.

# Inhalt

[TOC]

## Voraussetzungen

- Windows 11 (X64)
- eine btText-Installationsdatei oder das portable ZIP-Archiv

Die vorgefertigten Pakete enthalten die benötigte Laufzeit. Python muss nicht installiert werden.

## Installation

### Installierbare Version

1. Starten Sie `btText-<Version>-setup-windows.exe`.
2. Wählen Sie bei Bedarf die Sprache des Installationsprogramms.
3. Aktivieren Sie optional die Erstellung einer Desktopverknüpfung.
4. Schließen Sie die Installation ab und starten Sie btText über das Startmenü oder die ggf. erstellte Desktopverknüpfung.

Die Installation gilt nur für den aktuellen Windows-Benutzer und benötigt keine Administratorrechte. Die Programmdateien liegen normalerweise unter:

```text
%LOCALAPPDATA%\Programs\btText
```

Einstellungen und die Standarddatenbank werden getrennt von den Programmdateien gespeichert:

```text
%APPDATA%\btText\settings.ini
%APPDATA%\btText\data.db
```

### Portable Version

1. Entpacken Sie `btText-<Version>-portable-windows.zip` in einen eigenen, beschreibbaren Ordner.
2. Starten Sie `btText.exe` aus dem entpackten btText-Ordner.

Die portable Version speichert `settings.ini` und die Standarddatenbank `data.db` imselben Ordner, in welchem sich die Datei  `btText.exe` befindet. Verschieben oder sichern Sie immer den gesamten Ordner, wenn Sie die portable Version auf einen anderen Datenträger übertragen.

Verwenden Sie keinen geschützten Ordner wie `C:\Program Files`, weil btText anderenfalls nicht in der Lage ist, Einstellungen zu speichern und somit nicht korrekt funktionieren kann.

### Erster Start und Datenbank

Beim ersten Start fragt btText, ob eine neue Datenbank erstellt oder eine vorhandene Datenbank geöffnet werden soll.

- **Neue Datenbank erstellen** öffnet einen Speicherdialog. Werden in diesem Dialog keine Änderungen vorgenommen, wird eine Datenbank mit dem Namen `data.db` im Standardverzeichnis gespeichert. Installierte Version: `%APPDATA%\btText\`. Portable Version: Neben der Datei `btText.exe`.
- **Vorhandene Datenbank öffnen** öffnet eine bereits vorhandene btText-Datenbank.
- **Abbrechen** beendet die Auswahl. Ohne Datenbank kann btText nicht arbeiten.

Die gewählte Datenbank wird für die folgenden Starts gespeichert. Eine Datei im aktiven Datenordner wird als relativer Name gespeichert; Datenbanken in anderen Ordnern bleiben als absoluter Pfad erhalten.

Nach der Datenbankauswahl läuft btText im Hintergrund weiter. Das Hauptfenster wird beim Start nicht automatisch angezeigt. Stattdessen finden Sie btText über sein Symbol im Windows-Infobereich. So bleibt das Programm jederzeit verfügbar, ohne dauerhaft Platz auf dem Bildschirm oder in der Taskleiste zu beanspruchen.

### Portable und installierte Version wechseln

btText verschiebt oder löscht portable Daten nicht automatisch. Um eine portable Datenbank mit der installierten Version weiterzuverwenden, gibt es zwei Wege:

- Starten Sie die installierte Version, wählen Sie **Datenbank wechseln** und öffnen Sie die portable `data.db`. Die Datei bleibt an ihrem bisherigen Ort.
- Kopieren Sie die portable `data.db` vor dem ersten Start der installierten Version nach `%APPDATA%\btText\data.db`.

Erstellen Sie vor dem Kopieren oder Verschieben eine Sicherung. Überschreiben Sie keine Datenbank, deren Inhalt noch benötigt wird.

## Grundlegende Verwendung

btText ist als ständig verfügbares Hintergrundprogramm gedacht. Nach dem Start läuft es im Windows-Infobereich und wartet darauf, dass Sie einen Textbaustein benötigen. Das Hauptfenster öffnen Sie entweder mit der globalen Tastenkombination oder durch Anklicken des btText-Symbols im Infobereich.

So fügen Sie einen Textbaustein in ein anderes Programm ein:

1. Setzen Sie die Schreibmarke im Zielprogramm an die Stelle, an der der Text erscheinen soll.
2. Drücken Sie die globale btText-Tastenkombination – standardmäßig `Strg`+`Umschalt`+`Alt`+`T` – oder klicken Sie auf das btText-Symbol im Infobereich.
3. Wählen Sie im Hauptfenster die gewünschte Kategorie und anschließend den Textbaustein aus.
4. Drücken Sie `Eingabe` oder wählen Sie im Kontextmenü **Textbaustein einfügen**.

btText blendet daraufhin sein Hauptfenster aus, kehrt zum zuvor aktiven Programm zurück und fügt den Text an der dortigen Schreibmarke ein. Anschließend läuft btText weiterhin im Hintergrund und steht sofort für den nächsten Textbaustein zur Verfügung.

## Hauptfenster

Das Hauptfenster besteht aus zwei Bereichen:

- **Kategorien**: In dieser Baumansicht können Sie Kategorieen oder Unterkategorien auswählen.
- **Textbausteine**: In dieser Liste werden die Textbausteine der jeweils ausgewählten Kategorie angezeigt.

Die Liste zeigt unter anderem Name, Gewichtung und eine Inhaltsvorschau. Eine höhere Gewichtung ordnet einen Textbaustein in Such- und Listenansichten weiter oben ein. Dies dient lediglich zur Beeinflussung der Sortierreihenfolge, nicht zur  Bewertung des Textes selbst.

Die Statusleiste weist auf die wichtigsten Standardaktionen hin oder gibt Rückmeldungen bei bestimmten Schritten, etwa dem Kopieren eines Textbausteins oder einer Kategorie.

### Kategorien verwalten

Kategorien können verschachtelt werden. Öffnen Sie das Kontextmenü im Bereich **Kategorien** und verwenden Sie:

- **Neue Hauptkategorie** für eine Kategorie auf oberster Ebene;
- **Neue Unterkategorie** für eine Unterkategorie der Auswahl;
- **Umbenennen** oder `F2`, um die Auswahl umzubenennen;
- **Löschen** oder `Entf`, um die Kategorie einschließlich ihrer Unterkategorien und Textbausteine zu löschen.

Das Löschen einer Kategorie ist eine irreversible  Datenänderung. Alle in der Kategorie gespeicherten Textbausteine werden entgültig gelöscht, dies gilt ebenfalls für eventuell vorhandene Unterkategorien. Prüfen Sie daher immer sorgfältig den Bestätigungsdialog.

### Textbausteine anlegen und bearbeiten

Wählen Sie im Kategorienbaum eine Kategorie und öffnen Sie im Kontextmenü der Textbausteinliste **Neuer Textbaustein**. Füllen Sie anschließend die Felder aus:

- **Name**: Bezeichnung des Textbausteins; innerhalb einer Kategorie muss sie eindeutig sein.
- **Kategorie**: Zielkategorie des Textbausteins. Hier ist bereits die aktuell gewählte Kategorie vorbelegt.
- **Gewichtung**: Priorität für die Sortierung und Suche ("niedrig", "mittel", "hoch". Standard: "niedrig").
- **Hotstring**: optionales Kürzel für die automatische Erweiterung.
- **Inhalt**: der Text, der eingefügt werden soll.

Mit **Speichern** übernehmen Sie die Änderungen. Der Name und der Inhalt dürfen nicht leer sein. Ein Hotstring darf keine Leerzeichen enthalten und muss in der gesamten Datenbank eindeutig sein.

Zum Bearbeiten markieren Sie einen einzelnen Textbaustein und wählen im Kontextmenü **Textbaustein bearbeiten** oder drücken `F2`.

### Text einfügen oder kopieren

Öffnen Sie btText mit der globalen Tastenkombination oder über das Symbol im Infobereich und markieren Sie einen Textbaustein. Anschließend können Sie:

- `Eingabe` drücken oder im Kontextmenü **Textbaustein einfügen** wählen, um ihn in das zuvor aktive Windows-Fenster einzufügen;
- wählen Sie **Text in die Zwischenablage kopieren** oder drücken Sie `Strg`+`Umschalt`+`C`, um nur den Inhalt zu kopieren.

Beim Einfügen merkt sich btText das zuvor aktive Fenster, blendet sein eigenes Fenster aus und verwendet die Windows-Zwischenablage. Nach dem Vorgang wird der vorherige Inhalt der Zwischenablage wiederhergestellt, soweit dies möglich ist. btText wird dabei nicht beendet, sondern läuft im Hintergrund weiter und bleibt über Tastenkombination und Infobereich verfügbar. Das Zielprogramm muss ein normales Texteingabefeld bereitstellen. Ist kein gültiges vorheriges Fenster vorhanden oder kann es nicht aktiviert werden, zeigt btText einen Fehler an.

### Suchen

Drücken Sie `F3` oder wählen Sie **Bearbeiten > Suchen**. Geben Sie einen Suchbegriff ein, um Textbausteine zu finden. Die Ergebnisse zeigen Name, Kategorie, Gewichtung und eine Inhaltsvorschau.

Wählen Sie ein Ergebnis und **Textbaustein anzeigen**, um btText zur passenden Kategorie zu navigieren und den Textbaustein zu markieren.

### Kopieren, Ausschneiden und Einfügen

Kategorien und Textbausteine können intern kopiert oder verschoben werden:

1. Markieren Sie eine oder mehrere Kategorien bzw. Textbausteine.
2. Wählen Sie **Kopieren** (`Strg`+`C`) oder **Ausschneiden** (`Strg`+`X`).
3. Wählen Sie das Ziel.
4. Wählen Sie **Hier einfügen** bzw. **In Kategorie einfügen** (`Strg`+`V`).

Mit `Strg`+`Umschalt`+`V` können Sie eine Kategorie auf oberster Ebene einfügen. Ein Textbaustein muss immer in einer Kategorie eingefügt werden. Beim Kopieren bleibt das Original erhalten; beim Ausschneiden wird es nach erfolgreichem Einfügen verschoben.

In der Textbausteinliste können Sie mit `Strg`+`A` alle sichtbaren Einträge auswählen. Mehrfachauswahl ist für Kopieren, Ausschneiden und Löschen möglich.

## Menüs und Tastenkürzel

Die Tastenkürzel werden in der deutschen Oberfläche als `Strg`, `Umschalt`, `Alt` und `Win` angezeigt. Die Bezeichnungen können je nach gewählter Oberflächensprache abweichen.

### Menü „Datei“

- **Datenbank wechseln**: Für den nächsten Start eine andere vorhandene Datenbank öffnen oder eine neue Datenbank anlegen.
- **Schließen**: Das Hauptfenster ausblenden. btText bleibt im Infobereich aktiv.
- **Beenden**: btText vollständig schließen.

### Menü „Bearbeiten“

- **Suchen** (`F3`): Textbausteine durchsuchen.
- **Einstellungen** (`Strg`+`,`): Sprache, Darstellung, Zwischenablage, Hotstrings und globale Tastenkombination konfigurieren.

### Menü „Hilfe“

- **Benutzerhandbuch anzeigen** (`F1`): Dieses Benutzerhandbuch im Standardbrowser öffnen.
- **Über btText**: Version, Autor und Lizenz anzeigen.

### Kontextmenüs

Mit der rechten Maustaste oder dem Kontextmenübefehl der Tastatur öffnen Sie kontextabhängige Befehle für Kategorien und Textbausteine. Diese Menüs enthalten unter anderem neue Einträge, Einfügen, Kopieren, Ausschneiden, Umbenennen, Bearbeiten und Löschen.

## Hotstrings

Ein Hotstring ist ein Kürzel, das automatisch durch den Inhalt eines Textbausteins ersetzt wird. Beispiel:

```text
Hotstring: ;addr
Inhalt:   Musterstraße 12, 12345 Musterstadt
```

Wenn Sie in einem anderen Windows-Programm `;addr` und anschließend ein Leerzeichen, `Eingabe`, `Tab` oder ein Satzzeichen tippen, ersetzt btText das Kürzel durch den gespeicherten Inhalt.

### Hotstrings einrichten

1. Öffnen Sie den Textbaustein mit `F2` oder legen Sie einen neuen an.
2. Tragen Sie im Feld **Hotstring** ein Kürzel ohne Leerzeichen ein.
3. Speichern Sie den Textbaustein.

Hotstrings werden nach Änderungen automatisch neu geladen. Sie sind Groß-/Kleinschreibung-sensitiv: Verwenden Sie das Kürzel in genau der gespeicherten Schreibweise.

btText überwacht die Tastatur nur, wenn Hotstrings in den Einstellungen aktiviert sind, was standardmäßig der Fall ist. Die Eingabe wird beim Wechsel in ein anderes Vordergrundfenster neu begonnen. Mit der Rücktaste kann ein Teil des bisher eingegebenen Kürzels korrigiert werden.

## Einstellungen

### Allgemein

- **Sprache**: Ändert die Sprache der Benutzeroberfläche. Die Änderung wird erst nach einem Neustart des Programms wirksam.
- **Kopierten Textbaustein im Windows-Zwischenablageverlauf speichern**: Ist diese Einstellung aktiviert, wird ein über btText kopierter Textbaustein im Windows-Zwischenablageverlauf gespeichert. Dies betrifft lediglich das Kopieren des Textbausteins über den Kontextmenüeintrag "Text in die Zwischenablage kopieren", bzw. die Tastenkombination "Strg+Umschalt+C".
- **Kopierte Textbausteine in der Windows-Cloud speichern**: Erlaubt die Synchronisierung kopierter Textbausteine über die Windows-Cloud-Zwischenablage. Dies betrifft lediglich das Kopieren des Textbausteins über den Kontextmenüeintrag "Text in die Zwischenablage kopieren", bzw. die Tastenkombination "Strg+Umschalt+C".

### Hotstrings

- **Hotstrings aktivieren**: Schaltet die automatische Überwachung ein oder aus.
- **Endezeichen nach der Erweiterung erhalten**: Gibt das auslösende Leerzeichen, `Eingabe`, `Tab` oder Satzzeichen nach dem eingefügten Text wieder aus. Deaktivieren Sie die Option, wenn das Endezeichen nicht übernommen werden soll.
- **Nach der Erweiterung eine Windows-Benachrichtigung anzeigen**: Zeigt nach erfolgreicher Erweiterung eine Benachrichtigung im Windows-Infobereich an.

### Design

- **Darstellung**: Legt das Farbschema von btText fest. Sie können die **Systemeinstellung**, **Hell** oder **Dunkel** auswählen. Die Änderung wird nach einem Neustart des Programms wirksam.

### Tastatur

Die globale Tastenkombination blendet das btText-Hauptfenster ein oder aus. Standardmäßig ist dies:

```text
Strg+Umschalt+Alt+T
```

Eine globale Tastenkombination muss mindestens eine Modifikatortaste (`Strg`, `Umschalt`, `Alt` oder die Windows-Taste) und genau eine weitere Taste enthalten. Wählen Sie **Neue Tastenkombination aufzeichnen**, drücken Sie die gewünschte Kombination und bestätigen Sie mit **Übernehmen** oder **OK**. `Esc` bricht die Aufzeichnung ab. Ist die Kombination bereits von einem anderen Programm belegt, behält btText die bisherige Kombination bei.

btText berücksichtigt Änderungen des aktiven Windows-Tastaturlayouts und registriert die globale Tastenkombination bei Bedarf neu. Nicht jede bereits von Windows oder einem anderen Programm belegte Kombination kann verwendet werden.

## Infobereich und Programmende

Nach dem Start läuft btText standardmäßig nur im Windows-Infobereich; das Hauptfenster bleibt zunächst ausgeblendet. Klicken Sie auf das btText-Symbol oder drücken Sie die globale Tastenkombination, um das Hauptfenster anzuzeigen. Das Kontextmenü des Symbols enthält:

- **Textbausteine anzeigen**: Hauptfenster öffnen und fokussieren;
- **Beenden**: btText vollständig schließen.

**Schließen** im Menü des Hauptfensters blendet nur das Fenster aus. Das Programm, die globale Tastenkombination und aktivierte Hotstrings bleiben im Hintergrund verfügbar. Der Menüeintrag **Beenden** beendet btText hingegen vollständig und entfernt das Symbol aus dem Infobereich.

## Daten, Sicherungen und Deinstallation

Die wichtigste Datei ist die SQLite-Datenbank `data.db`. Sichern Sie sie bei Bedarf, während btText geschlossen ist. Eine ausgewählte Datenbank in einem anderen Ordner wird bei der Deinstallation nicht gelöscht.

### Installierte Version deinstallieren

Deinstallieren Sie btText über **Windows > Installierte Apps** oder den Deinstallationsbefehl im Startmenü. Die Programmdateien und Verknüpfungen werden entfernt. Danach bietet der Deinstaller optional an, den Ordner `%APPDATA%\btText` mit Einstellungen und Standarddatenbank zu löschen.

Das löschen der Daten  ist standardmäßig nicht aktiviert und kann nicht rückgängig gemacht werden. Sichern Sie ggf. `data.db`, bevor Sie der Löschung zustimmen. Falls sich die Datenbank an einem anderen Speicherort befindet, wird sie nicht entfernt.

### Portable Version entfernen

Beenden Sie btText und löschen Sie den entpackten Programmordner. Dadurch werden auch eine darin liegende `settings.ini` und `data.db` gelöscht. Sichern Sie die Datenbank vorher, wenn sie noch benötigt wird.

## Barrierefreie Bedienung

btText verwendet native Windows-Steuerelemente, beschriftete Bereiche und Tastaturkürzel. Die wichtigsten Bedienungen sind ohne Maus möglich:

- `Tab` und `Umschalt`+`Tab` wechseln zwischen den Steuerelementen;
- Pfeiltasten bewegen die Auswahl in Kategoriebaum und Textbausteinliste;
- `F2` bearbeitet die aktuelle Auswahl;
- `Entf` löscht die aktuelle Auswahl nach Bestätigung;
- `F3` öffnet die Suche;
- `Eingabe` fügt den ausgewählten Textbaustein ein.

## Fehlerbehebung

### btText startet nicht, weil es bereits ausgeführt wird

Pro Benutzer kann nur eine btText-Instanz aktiv sein. Prüfen Sie den Infobereich und beenden Sie die bereits laufende Instanz oder verwenden Sie den Menüpunkt `Beenden`im Menü `Datei` des Hauptfensters.

### Ein Hotstring wird nicht erweitert

Prüfen Sie:

1. ob in den Einstellungen **Hotstrings aktivieren** eingeschaltet ist;
2. ob das Kürzel exakt einschließlich Groß-/Kleinschreibung eingegeben wurde;
3. ob danach ein Leerzeichen, `Eingabe`, `Tab` oder ein Satzzeichen folgt;
4. ob dem Kürzel tatsächlich ein Textbaustein zugeordnet ist;
5. ob das Zielprogramm ein aktives Texteingabefeld besitzt.

### Das globale Tastenkürzel funktioniert nicht

Wählen Sie in **Einstellungen > Tastatur** eine andere Kombination. Eine bereits belegte Kombination kann nicht registriert werden. Nach dem Ändern des Tastaturlayouts kann Windows eine kurze Neuregistrierung benötigen.

### Die Datenbank lässt sich nicht öffnen

Stellen Sie sicher, dass die Datei existiert, nicht von einem anderen Prozess gesperrt ist und eine gültige btText-Datenbank-Struktur aufweist. Verwenden Sie **Datenbank wechseln**, um eine andere Datei auszuwählen. Eine Datenbank aus einer neueren btText-Version kann von einer älteren Version möglicherweise nicht geöffnet werden.

### Ein Text wird im falschen Fenster eingefügt

Markieren Sie den Textbaustein in btText erst dann, wenn das gewünschte Zielprogramm aktiv ist, oder verwenden Sie das globale Fensterkürzel, um btText zu öffnen und den Fokus anschließend gezielt zurückzugeben. Das Zielprogramm muss während des Einfügevorgangs aktiviert werden können.
