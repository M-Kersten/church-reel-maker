# Hoe het kader de spreker volgt

Een camera achterin de kerk zet de voorganger in een klein deel van een breed beeld. Een
staand kader van 1080×1920 haalt daar hooguit een derde uit. Zet je dat kader vast in het
midden, dan loopt de spreker eruit zodra hij een stap zet; trek je het zo ver open dat hij
er altijd in valt, dan kijk je naar bewakingsbeelden.

Dit beschrijft wat er gebeurt tussen de gekozen fragmenten en een kader dat meebeweegt.

## 1. Kijken

`backend/vision.py` haalt drie beelden per seconde uit de clip en legt ze in een vierkant
van 640 bij 640, met zwarte randen erlangs. Twee modellen kijken ernaar.

YuNet zoekt gezichten. Klein model, 227 KB, kost acht milliseconden per beeld, en het geeft
precies wat je wilt kadreren: het hoofd. YOLOv10n zoekt personen. Dat kost er vijfendertig,
dus dat gebeurt bij elk derde beeld.

De twee beantwoorden verschillende vragen. Een lichaam zegt wie er op het podium staat, en
dat verandert langzaam. Een gezicht zegt waar het hoofd is, en dat verandert steeds. Draait
de spreker zich af, dan is het gezicht weg en draagt het lichaam het kader verder. Zijn ze
allebei weg, dan blijft de laatste positie tweeënhalve seconde staan en daarna geeft de app
toe dat er een gat is.

Wie er gevolgd wordt, wordt één keer bepaald: de persoon die het midden van het beeld
vasthoudt, groot genoeg en zeker genoeg. Daarna wordt diezelfde persoon elk beeld
teruggezocht, als het dichtstbijzijnde vakje dat niet te ver weg ligt om nog hem te kunnen
zijn. Een muzikant die achterlangs loopt neemt het kader dus niet over.

## 2. Stilstaan

`backend/tracking.py` maakt van die waarnemingen een positie per 1/12,5 seconde. Bijna
alles daaraan gaat over niet bewegen.

Afstanden zijn aandelen van de breedte van het kader zelf, met de rand op 0,5. Zo gedragen
dezelfde getallen zich hetzelfde bij een strak kader als bij een ruim kader.

**De dode zone** loopt tot 0,14. Binnen die zone gebeurt er niets. Een spreker die achter
een katheder staat en met zijn handen praat, geeft een beeld dat volledig stilstaat.

Daarbuiten schuift het kader terug, exponentieel, met een snelheidsplafond van 0,40
kaderbreedtes per seconde. Traag genoeg dat je de spreker ziet en niet de camera.

**De houdlijn** ligt op 0,34. Daar houdt kalm op interessant te zijn, want de spreker staat
op het punt het beeld uit te lopen. Het plafond gaat eraf en het kader haalt hem in met
1,10 kaderbreedtes per seconde.

Alleen x beweegt. Hoogte en zoom blijven staan waar de gebruiker ze zette. In een staand
kader uit een breed beeld zit boven en onder de spreker zelden iets dat het volgen waard is,
en verticale drift is het eerste wat als wiebelen leest.

## 3. Camerawissels

Sommige kerken hebben meerdere camera's. Zo'n wissel is geen beweging waar je doorheen kunt
glijden, want de ruimte zelf verandert. Het kader springt mee.

Een wissel wordt herkend aan hoeveel het beeld verandert ten opzichte van wat deze clip
normaal doet, niet aan een vast getal. Twee camera's in dezelfde zaal schelen veel minder
dan twee zalen, en een donkere kerk scheelt minder dan een lichte. In de gemeten opname lag
een echte wissel op 20,4 en het drukste gewone beeld op 3,7.

Springen gebeurt alleen als de spreker verder weg staat dan de dode zone. Terugsnijden naar
een camera die hem al in het midden had, blijft daardoor volkomen stil.

Direct na een wissel is er niemand meer die gevolgd wordt, dus dan wordt het personenmodel
meteen bevraagd in plaats van te wachten tot het weer aan de beurt is.

## 4. Renderen

`renderer.track_commands` leest het pad vijftig keer per seconde uit en schrijft een regel
op elk moment dat het kader op een andere pixel zou landen. Dat gaat als `sendcmd` naar een
`crop@track` filter in FFmpeg. Een spreker die stilstaat kost een handvol regels in plaats
van één per beeld.

Vijftig, terwijl het pad op 12,5 is opgeslagen: sendcmd zet een waarde en laat hem staan, en
bij een snelle pan zie je die stappen anders zitten.

`frontend/src/track.ts` leest hetzelfde pad op dezelfde manier, zodat de voorvertoning het
kader tekent waar de render het straks neerzet. `tests/mirror_cases.py` legt de twee naast
elkaar en laat de build vallen als ze uit elkaar lopen.

## 5. Wat je ervan ziet

Bij het verwerken van de gekozen fragmenten wordt elke clip doorgekeken, in een stap waar je
toch al staat te wachten. De clip opent dus met de spreker al gevolgd.

In het paneel **Beeldkader** staan twee knoppen naast elkaar. *Volg de spreker* laat het
gouden kader het pad lopen, *Zelf kaderen* geeft het terug aan jou. Eronder staat wat er
gevonden is: in hoeveel procent van de clip, en hoeveel camerawissels erin zaten.

Is er in minder dan 55% van de clip iemand gevonden, dan wordt het pad wel bewaard maar niet
aangezet. Je kunt het alsnog aanzetten en kijken.

Een clip die los is binnengekomen heeft nog geen pad. Daar staat een knop **Zoek de
spreker**, die er ongeveer tien seconden per minuut video over doet.

Wat er niet is: een tijdlijn met sleutelbeelden om zelf in te tekenen. Als het pad niet
klopt, is een statisch kader op de goede plek zetten in vijf seconden gedaan.

## Gemeten

Negentig seconden preek, 1280×720, één camera, twee keer gerenderd en daarna in de
afgemaakte staande video's gezocht naar het hoofd. Achtenzestig metingen per video:

| | statisch kader | volgend kader |
|---|---|---|
| hoofd in beeld | 68 van 68 | 68 van 68 |
| gemiddeld van het midden | 0,49 | 0,17 |
| tegen de rand aan | 15 keer | nooit |

Deze spreker blijft achter de katheder, dus hij valt ook statisch niet uit beeld. Waar hij
in het kader staat, scheelt wel: halverwege de rand tegenover ruim in het midden.

Het zoeken liep op zes keer realtime. De spreker werd in 100% van de metingen gevonden, het
kader stond op 93% van de stappen volkomen stil, en de grootste stap was 1% van de breedte.
Op een in elkaar gezette opname met een camerawissel erin sprong het kader binnen één beeld
mee.
