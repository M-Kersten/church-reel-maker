"""A Sunday morning as it actually runs, for testing the structural pass.

Not a real recording: a plausible one, written so every part of a Dutch protestant service
appears in the order and roughly the proportion it usually does.
"""

# (part it should be recognised as, seconds it lasts, what is said)
SERVICE: list[tuple[str, float, list[str]]] = [
    ("welkom", 70, [
        "Goedemorgen allemaal, hartelijk welkom in de Nieuwe Kerk.",
        "Fijn dat jullie er zijn, ook de mensen die vanochtend meekijken.",
        "We beginnen deze dienst in de naam van de Vader, de Zoon en de Heilige Geest.",
        "Wat goed om elkaar weer te zien op deze zondagochtend.",
    ]),
    ("zang", 600, [
        "We zingen samen Opwekking 733, de zegen van de Heer.",
        "Laten we staan en meezingen met de band.",
        "En we gaan verder met lied 302, het refrein zingen we twee keer.",
        "We sluiten dit blok af met psalm 84.",
    ]),
    ("gebed", 110, [
        "Laten we bidden.",
        "Hemelse Vader, dank U wel dat wij hier mogen zijn vanmorgen.",
        "Wij bidden voor iedereen die vandaag niet kon komen, voor de zieken in ons midden.",
        "Heer, ontferm U over deze stad. Amen.",
    ]),
    ("lezing", 150, [
        "De Bijbellezing van vandaag komt uit Mattheüs, hoofdstuk 11.",
        "We lezen vers 28 tot en met 30.",
        "Kom naar mij, jullie die vermoeid zijn en onder lasten gebukt gaan, dan zal ik jullie rust geven.",
        "Neem mijn juk op je en leer van mij, want ik ben zachtmoedig en nederig van hart.",
        "Tot zover de lezing, het woord van de Heer.",
    ]),
    ("zang", 420, [
        "Voor de preek zingen we nog Opwekking 599.",
        "De band speelt het voorspel, we zingen zittend mee.",
    ]),
    ("preek", 1620, [
        "Vandaag wil ik met jullie praten over rust.",
        "Want soms denken we dat we alles zelf moeten kunnen.",
        "We rennen van de ene verplichting naar de andere en we vergeten dat we het niet alleen hoeven te dragen.",
        "God vraagt niet dat je perfect bent. Hij vraagt of je bij hem wilt komen zoals je bent.",
        "Met je twijfels, met je vragen, met alles wat je meedraagt.",
        "Misschien herken je dat gevoel van nooit klaar zijn.",
        "Ik sprak vorige week een vrouw die al jaren voor haar zieke moeder zorgt.",
        "Ze zei: ik ben zo moe, maar ik durf niet te stoppen.",
        "En ik zei tegen haar: je mag rusten. Rust is geen zwakte, rust is vertrouwen.",
        "Vertrouwen dat de wereld doorgaat als jij even stilstaat.",
        "Je bent bang dat alles instort als jij loslaat.",
        "Maar wat als loslaten juist de plek is waar het kan gaan werken?",
        "Wat als je handen open moeten om iets nieuws te kunnen ontvangen?",
        "Denk eens aan hoe vaak je nee hebt gezegd tegen rust deze week.",
        "De vraag is niet of je het druk hebt. De vraag is waar je je rust vandaan haalt.",
        "Jezus zegt: kom naar mij, en ik zal jullie rust geven.",
        "Dat is geen belofte voor later. Dat is een uitnodiging voor vandaag.",
        "Wat betekent dat op een maandagochtend, als de week weer begint?",
        "Het betekent dat je niet alleen begint. Dat je gedragen wordt.",
        "Ik wil afsluiten met dit: je hoeft dit niet alleen te dragen.",
        "Wat er ook speelt in je leven, je mag het neerleggen.",
        "Niet omdat het niet belangrijk is, maar omdat je gedragen wordt.",
    ]),
    ("mededelingen", 160, [
        "Dan nu een paar mededelingen.",
        "De collecte van vandaag is bestemd voor het diaconaal werk in de wijk.",
        "Na de dienst is er koffie en thee in de grote zaal, van harte welkom.",
        "Volgende week zondag is er geen dienst in dit gebouw, we zijn dan te gast bij de gemeente aan de overkant.",
        "De aanvangstijd is dan 10 uur. Je kunt je opgeven voor het gemeenteweekend via de website.",
    ]),
    ("zang", 400, [
        "We sluiten af met lied 416, we zingen het staande.",
        "Het orgel speelt het voorspel.",
        "En als slotlied zingen we gezang 456.",
    ]),
    ("zegen", 60, [
        "Ontvang dan nu de zegen van de Heer.",
        "De genade van onze Heer Jezus Christus zij met jullie allen.",
        "Ga heen in vrede. Amen. Wel thuis allemaal.",
    ]),
]


def transcript_segments():
    """Turn the script into timed segments, with a silent gap during the singing."""
    from backend.models import Segment

    segments = []
    now = 0.0
    for part, seconds, lines in SERVICE:
        per = seconds / max(1, len(lines))
        for line in lines:
            spoken = min(per * 0.6, 8.0)
            segments.append(Segment(start=round(now, 2), end=round(now + spoken, 2), text=line))
            # Singing leaves long stretches with nothing said; speech does not.
            now += per if part != "zang" else per
        now += 1.0
    return segments


def expected_parts():
    """What each segment should be labelled, in the same order."""
    out = []
    for part, _seconds, lines in SERVICE:
        out.extend([part] * len(lines))
    return out
