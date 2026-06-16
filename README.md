<h1>Oneplay Server</h1>

Oneplay Server slouží jako alternativa k IPTV Web Serveru pro Oneplay. Lze ho používat buď jako doplněk v Kodi i samostatně.

<a href="https://www.xbmc-kodi.cz/prispevek-oneplay-server">Vlákno na fóru XBMC-Kodi.cz</a><br><br>

<b><u>Kodi</u></b>

Nainstalujte doplněk a v jeho nastavení vyplňte přihlašovací údaje, deviceid (libovolný alfanumerický řetězec) a IP adresu nebo jméno serveru. Po uložení nastavení restartujte Kodi nebo zakažte a povolte doplněk.

<b><u>Samostatný skript</u></b>

Oneplay Server pro své fungování vyžaduje python moduly bottle a websocket. Nainstaluje buď jako balíček OS nebo pomocí pip3 (pip3 install &lt;module&gt;)

Rozbalte zip, zkopírujte config.txt.sample na config.txt a v něm vyplňte jméno, heslo, deviceid a IP adresu nebo jméno serveru. Server spusťte z adresáře service.oneplay.server spuštěním python3 server.py.<br>
Pokud chcete Oneplay Server spustit na linuxu se systemd jako službu, jako root/přes sudo:
- zkopírujte z adresáře scripts soubor oneplay_server.service do /etc/systemd/system/
- systemctl daemon-reload
- systemctl enable oneplay_server
- systemctl start oneplay_server


<b><u>TVheadend</u></b>

Pro použití Oneplay Serveru v TVheadendu je potřeba mít nainstalovaný ffmpeg (na stroji s TVH). Pro načtení EPG přes External XMLTV grabber pak ještě socat.

V config.txt zkontrolujte nastavení cesta_ffmpeg (viz config.txt.sample), v případě Kodi pak analogické položky v nastavení.

Při vytváření IPTV sítě v TVheadendu použijte adresu playlistu:

http://&lt;adresa nebo jméno serveru&gt;:&lt;port (defaultně 8082)&gt;/playlist/tvheadend

např. http://127.0.0.1:8082/playlist/tvheadend

Playlist vrací řádky <code>pipe://</code> s ffmpeg, který stahuje HLS z endpointu <code>/play/</code> a převádí ho na MPEG-TS pro TVHeadend. OnePlay server musí být z TVH dosažitelný na portu z config.txt (typicky 8082); pokud běží na stejném stroji jako TVH, stačí <code>127.0.0.1</code>.

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
<li><b>test_tvheadend_pipe.sh</b> – ověří, že <code>pipe://</code> z playlistu produkuje MPEG-TS data</li>
</ul>

Po opravě mapování kanálů doporučujeme: <code>sudo systemctl restart tvheadend</code>

<b><u>URL</u></b>

Playlist je dustupný na http://<adresa nebo jméno serveru>:<port (defaultně 8082)>/playlist, např. http://127.0.0.1:8082/playlist

EPG lze pak stáhnout z http://<adresa nebo jméno serveru>:<port (defaultně 8082)>/epg, např. http://127.0.0.1:8082/epg

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
