# ProcWorks – Werbe-Website (procworks.de)

Eigenständige, statische Landingpage für die Domain **procworks.de**.
Kein Build-Schritt, keine Abhängigkeiten – reines HTML/CSS im dunklen
ProcWorks-Look.

## Dateien

| Datei         | Zweck                                              |
| ------------- | -------------------------------------------------- |
| `index.html`  | Single-Page-Landingpage                            |
| `styles.css`  | Styles (Palette identisch zur App in `web/`)       |
| `robots.txt`  | Indexierung erlauben, Verweis auf die Sitemap      |
| `sitemap.xml` | Sitemap für Suchmaschinen (Search Console/Bing)    |
| `og-image.png`| Vorschaubild (1200×630) für Social-/Link-Vorschauen|
| `og-image.svg`| Quelle des Vorschaubilds (nicht hochladen nötig)   |
| `Caddyfile`   | Reverse-Proxy/Webserver mit automatischem TLS      |
| `Dockerfile`  | Container-Image (Caddy) zum Ausliefern             |

> Für die Auffindbarkeit bei Webhosting **`index.html`, `styles.css`,
> `robots.txt`, `sitemap.xml` und `og-image.png`** ins Wurzelverzeichnis
> hochladen.

## Lokale Vorschau

Einfach `index.html` im Browser öffnen, oder mit einem statischen Server:

```sh
cd site
python3 -m http.server 8080
# http://localhost:8080
```

## Deployment unter procworks.de

Voraussetzung: Die DNS-A/AAAA-Records von `procworks.de` und
`www.procworks.de` zeigen auf den Server.

```sh
# Image bauen
docker build -t procworks-site ./site

# Container starten (Caddy holt das TLS-Zertifikat automatisch via Let's Encrypt)
docker run -d --name procworks-site \
  -p 80:80 -p 443:443 \
  -v caddy_data:/data \
  procworks-site
```

Das Volume `caddy_data` persistiert die ausgestellten Zertifikate.
