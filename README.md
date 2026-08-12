<h1>Oneplay Server</h1>

Oneplay Server slouží jako alternativa k IPTV Web Serveru pro Oneplay. Lze ho používat buď jako doplněk v Kodi i samostatně.

<a href="https://www.xbmc-kodi.cz/prispevek-oneplay-server">Vlákno na fóru XBMC-Kodi.cz</a><br><br>

<b><u>Kodi</u></b>

Nainstalujte doplněk a v jeho nastavení vyplňte přihlašovací údaje, deviceid (libovolný alfanumerický řetězec) a IP adresu nebo jméno serveru. Po uložení nastavení restartujte Kodi nebo zakažte a povolte doplněk.

<b><u>Samostatný skript</u></b>

Oneplay Server pro své fungování vyžaduje python moduly bottle a websocket. Nainstaluje buď jako balíček OS nebo pomocí pip3 (pip3 install &lt;module&gt;)

Rozbalte zip, zkopírujte config.txt.sample na config.txt a v něm vyplňte jméno, heslo, deviceid a IP adresu nebo jméno serveru. Server spusťte z adresáře service.oneplay.server spuštěním python3 server.py.<br>
Pokud chcete Oneplay Server spustit na linuxu se systemd jako službu, jako root/přes sudo:
- upravte a zkopírujte <code>scripts/oneplay_server.service</code> do <code>/etc/systemd/system/oneplay_server.service</code> (cesty User, venv, WorkingDirectory)
- <b>ne</b> používejte <code>ExecStartPre</code> s mazáním <code>session.txt</code> / <code>channels.txt</code> – po každém restartu služby to způsobí nový login a při TVH scanu nestabilní start
- <code>systemctl daemon-reload && systemctl enable oneplay_server && systemctl start oneplay_server</code>

V <code>config.txt</code> držte <code>debug</code> na <b>0</b> v produkci – při <code>debug=1</code> se do journalu logují celé JSON odpovědi API a server se při TVH scanu výrazně zpomalí.

<b><u>Checklist po deploy / změně playlistu</u></b>

<ol>
<li><code>sudo systemctl restart oneplay_server</code></li>
<li>V TVHeadendu: Force scan IPTV sítě nebo reload playlistu</li>
<li><code>sudo ./scripts/fix_tvh_channel_services.sh</code> – nebo <code>make tvh-fix</code></li>
<li><code>sudo systemctl restart tvheadend</code> – nebo <code>make tvh-restart</code> (ruční fix + restart + ověření)</li>
<li>Po instalaci auto-fix (<code>make install-tvh-autofix</code>) fix po startu TVH proběhne automaticky</li>
<li><code>bash scripts/test_nova_hd.sh</code> a <code>bash scripts/test_tvheadend_pipe.sh</code></li>
</ol>

<b><u>TVheadend</u></b>

Pro použití Oneplay Serveru v TVheadendu je potřeba mít nainstalovaný ffmpeg (na stroji s TVH). Pro načtení EPG přes External XMLTV grabber pak ještě socat.

V config.txt zkontrolujte nastavení cesta_ffmpeg (viz config.txt.sample), v případě Kodi pak analogické položky v nastavení.

Při vytváření IPTV sítě v TVheadendu použijte adresu playlistu:

http://&lt;adresa nebo jméno serveru&gt;:&lt;port (defaultně 8082)&gt;/playlist/tvheadend

např. http://127.0.0.1:8082/playlist/tvheadend

Playlist vrací řádky <code>pipe://</code> s ffmpeg, který stahuje HLS z endpointu <code>/play/</code> a převádí ho na MPEG-TS pro TVHeadend. OnePlay server musí být z TVH dosažitelný na portu z config.txt (typicky 8082); pokud běží na stejném stroji jako TVH, stačí <code>127.0.0.1</code>.

<b>Stream do TVHeadendu (oprava v1.5.6):</b> OnePlay API vrací více HLS variant (<code>hls-clear</code>, <code>hls-aes</code>). Server musí vybrat nešifrovaný <code>hls-clear</code> a ffmpeg musí posílat User-Agent <code>OnePlayServer</code> – CDN vrací 403 pro výchozí UA ffmpeg. Po změně playlistu vždy spusťte <code>fix_tvh_channel_services.sh</code> (viz Skripty).

Počet IPTV adaptérů a <code>max_streams</code> v TVH nastavte podle limitu souběžných streamů vaší OnePlay licence – běžný účet povoluje typicky <b>3</b> streamy najednou; vyšší počty (např. u korporátní licence) jsou výjimka a je nutné je sladit s limitem od operátora. Doporučujeme také <code>max_timeout</code> 60 s. Po <b>Force scan</b> sítě spusťte opravu mapování kanálů (viz sekce Skripty).

U EPG je jednou z variant využití External XMLTV grabberu. Nejprve ho je potřeba v TVheadendu povolit (Program/Channels - EPG Grabber modules). V adresáři scripts je připravený skript epg.sh, který stáhne EPG z Oneplay Server a obsah pošle External XMLTV grabberu. Zkontrolujte v něm cestu xmltv.sock (vytvoří se po povolení grabberu) a URL Oneplay Serveru.

<b><u>Porty</u></b>

<table>
<tr><th>Port</th><th>Kde</th><th>Účel</th></tr>
<tr><td>8082</td><td>OnePlay server</td><td>Playlist, EPG, webové rozhraní, <code>/play/</code> pro ffmpeg</td></tr>
<tr><td>9981</td><td>TVHeadend</td><td>HTTP playlisty a streamy pro klienty (Android boxy, IPTV přehrávače)</td></tr>
<tr><td>9982</td><td>TVHeadend</td><td>HTSP (volitelné, pokud klienti nepoužívají HTTP)</td></tr>
</table>

OnePlay port 8082 stačí lokálně na stroji s TVH (<code>127.0.0.1:8082</code>), do klientské sítě ho publikovat nemusíte. Klienti potřebují dosáhnout na TVHeadend na portu 9981.

<b><u>Skripty</u></b>

V adresáři <code>scripts/</code> jsou pomocné nástroje pro provoz s TVHeadendem:

<ul>
<li><b>fix_tvh_channel_services.sh</b> – po Force scan v TVH opraví mapování kanál → služba (nová UUID služeb). Idempotentní, lze spouštět opakovaně.<br>
<code>sudo ./scripts/fix_tvh_channel_services.sh</code> – výchozí síť Oneplay, pak Oneplay1<br>
<code>sudo ./scripts/fix_tvh_channel_services.sh Oneplay1</code> – konkrétní síť (název nebo UUID)<br>
<code>sudo env TVH_CONF=/home/hts/conf ./scripts/fix_tvh_channel_services.sh</code> – vlastní cesta ke konfiguraci TVH</li>
<li><b>test_nova_hd.sh</b> – ověří, že OnePlay server vrací živý HLS stream (Nova HD)</li>
<li><b>tvh_auto_fix.sh</b> – automatický fix mapování po startu TVHeadend (systemd ExecStartPost)<br>
<code>sudo make install-tvh-autofix</code> – instalace drop-in do <code>tvheadend.service.d</code><br>
Log: <code>journalctl -t oneplay-tvh-auto-fix</code></li>
<li><b>verify_tvh_nova.sh</b> – ověří Nova HD přes TVH port 9981 s opakováním</li>
<li><b>check_health.sh</b> – ověří <code>/health</code> s opakováním po restartu serveru</li>
<li><b>Makefile</b> – <code>make install-tvh-autofix</code>, <code>make tvh-restart</code>, <code>make verify</code>, <code>make verify-tvh</code> (viz <code>make help</code>)</li>
</ul>

Po opravě mapování kanálů doporučujeme restart TVH; s auto-fix instalací se mapování opraví samo po každém startu TVHeadend.

<b><u>URL</u></b>

Playlist je dustupný na http://<adresa nebo jméno serveru>:<port (defaultně 8082)>/playlist, např. http://127.0.0.1:8082/playlist

Playlist s jednou skupinou (atribut <code>group-title</code> v M3U): http://127.0.0.1:8082/playlist/group/NázevSkupiny

EPG lze pak stáhnout z http://<adresa nebo jméno serveru>:<port (defaultně 8082)>/epg, např. http://127.0.0.1:8082/epg

Health check (monitoring): http://127.0.0.1:8082/health – JSON s poli <code>status</code> (<code>ok</code> / <code>degraded</code> / <code>error</code>), <code>version</code>, <code>api_version</code>, <code>session_cached</code>, <code>channels_cached</code>, <code>login_backoff</code> (sekundy do dalšího login pokusu). Endpoint nevolá login – čte jen cache ze souborů.

V <code>config.txt</code> lze nastavit cache živých stream URL (snížení zátěže API při TVH scanu):
<ul>
<li><code>stream_cache_ttl</code> – TTL v sekundách (default 45)</li>
<li><code>stream_cache_enabled</code> – 1 zapnuto, 0 vypnuto (default 1)</li>
</ul>
Cache se vyčistí při „Session reset“ na webu.

Na http://<adresa nebo jméno serveru>:<port (defaultně 8082)>, např. http://127.0.0.1:8082 je možné stiskem tlačítka vynutit načtení kanálů nebo vytvoření nové sessiony.

<b><u>Vývoj (větev develop)</u></b>

Tato větev vychází z upstream <a href="https://github.com/waladir/script.oneplay.server">waladir/script.oneplay.server</a> a obsahuje rozšíření pro provoz s TVHeadendem a vyšší spolehlivost.

Oproti upstream tagu <b>1.5.5</b> (waladir obsahuje jen opravu načítání účtů z <code>step.groups[].accounts</code>) přidává develop mimo jiné:

<ul>
<li>podporu starého i nového formátu výběru účtu (<code>helpers.collect_account_ids</code>)</li>
<li>ochranu proti opakovaným login pokusům (rate limit API, 300 s cooldown)</li>
<li>srozumitelnější logování chyb API místo Python tracebacku</li>
<li>vícevláknový HTTP server (<code>ThreadedWSGIServer</code>)</li>
<li>HTTP 303 redirect v <code>/play/</code> (kompatibilita s TVHeadend ffmpeg)</li>
<li>routing kanálů přes <code>/play_num/</code> při <code>pouzivat_cisla_kanalu</code></li>
<li>pytest testy (<code>tests/</code>, CI v <code>.github/workflows/tests.yml</code>)</li>
<li>provozní skripty pro TVHeadend (<code>scripts/fix_tvh_channel_services.sh</code> apod.)</li>
</ul>

<b>Testy</b> (vyžaduje <code>pip install -r requirements-dev.txt</code>):

<pre>python3 -m pytest</pre>

<b><u>Změny</u></b>
v1.5.8 (12.8.2026) – develop
- automatický tvh-fix po startu TVHeadend (systemd drop-in)
- verify_tvh_nova.sh s opakováním, Makefile install-tvh-autofix

v1.5.7 (12.8.2026) – develop
- health endpoint /health pro monitoring
- cache živých stream URL (stream_cache_ttl, stream_cache_enabled)
- oprava uložení disable kanálů (upstream fix)

v1.5.6 (12.8.2026) – develop
- oprava výběru hls-clear streamu pro TVHeadend (místo hls-aes)
- TVHeadend pipe:// s user_agent OnePlayServer (CDN 403 bez UA)
- automatická detekce verze OnePlay API
- playlist se skupinou kanálů (/playlist/group/&lt;name&gt;)
- zjednodušený ffmpeg příkaz v TVHeadend playlistu
- vylepšený test_tvheadend_pipe.sh

v1.5.5 (12.6.2026) – develop
- oprava loginu pro nové OnePlay API (step.groups[].accounts)
- srozumitelnější logování chyb místo Python tracebacku
- ochrana proti opakovaným login pokusům (rate limit API)
- vícevláknový web server (nezablokuje streamy při generování EPG)
- playlist TVHeadend přes pipe://ffmpeg a redirect v /play/
- skript fix_tvh_channel_services.sh pro opravu mapování kanálů po TVH rescanu
- testovací skripty test_nova_hd.sh, test_tvheadend_pipe.sh
- pytest suite pro login a helpers

v1.5.4 (11.6.2026)
- úprava verze API a aplikace

v1.5.3 (1.6.2026)
- přidaná možnost vyřazení kanálů z playlistu

v1.5.2 (31.5.2026)
- vypnutí zobrazení varování při přístupu s neroutovatelných/privátních rozsahů
- přidání možnosti nastavit whitelist klientských adres, pro který nebude vyžadována autentizace
- úprava poměru stran u ikon

v1.5.1 (18.4.2026)
- zpětné přehrávání v built-in přehrávači (od sedin2)
- basic autentizace (od sedin2)
- oprava spouštění streamu některých kanálů
- přetáčení u live streamů

v1.5.0 (11.4.2026)
- nová webová stránka (od sedlin2)
