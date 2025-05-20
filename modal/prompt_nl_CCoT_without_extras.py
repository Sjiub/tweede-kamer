prompt = """
ZEER BELANGRIJK - UITVOERREGELS:
- Genereer EXACT EEN JSON object.
- GEEN extra tekst voor of na de JSON.
- GEEN codemarkeringen (```).
- GEEN herhaling van dezelfde analyse.
- GEEN denkproces of uitleg buiten JSON.
- ALLE getallen moeten werkelijke waarden zijn (geen expressies).
- ALLE velden moeten de juiste komma's hebben.
- Gebruik dubbele aanhalingstekens voor strings.
- Bereken samenvattende waarden voordat je ze in de JSON opneemt.

INHOUDSREGELS:
- Focus op UNIEKE gevallen (niet meerdere keren dezelfde verklaring).

TAAK 1:
REDENEERSTAPPEN (volg deze altijd voordat je een aanval labelt):
1. Definitie van een uitspraak: Een stelling verwijst naar de uiting of beurt van één spreker binnen het debat, meestal één paragraaf of bijdrage per keer. Analyseer elke uitspraak afzonderlijk en combineer niet meerdere uitspraken van verschillende sprekers.
2. Identificeer het belangrijkste argument of de belangrijkste bewering in de uitspraak.
3. Controleer of de reactie ingaat op dat argument, of in plaats daarvan de focus verlegt naar de persoon of groep die het argument maakt.
4. Als het gericht is op de persoon of groep, beoordeel dan of de aanval het argument probeert te ondermijnen door te focussen op eigenschappen, karakter, motieven, acties in het verleden of affiliaties.
5. Denk na over de toon en retorische stijl van de uitspraak:
   - Gebruikte de spreker sarcasme, spot of retorische overdrijving om de persoon in diskrediet te brengen in plaats van te reageren op zijn argument?
   - Heeft de spreker een impliciete aanval gedaan op de geloofwaardigheid, ernst of motieven van de spreker, bijvoorbeeld door middel van toon, insinuaties of gecodeerde taal?
   - Zo ja, en het is duidelijk de bedoeling om de spreker persoonlijk in diskrediet te brengen in plaats van in te gaan op het argument, label het dan als een impliciete ad hominem.
6. Geef een confidence interval (0,0 is het laagst en 1,0 het hoogst) op basis van de duidelijkheid, context en intentie van de aanval.

Voorbeelden van ad hominem aanvallen:
- "Minister Janssen is of te lui of te onwetend om het laatste economische rapport te lezen, hoe kunnen we zijn voorstellen dan serieus nemen?"
- "Het is fascinerend dat iemand die met moeite een enkel ministerie leidde, zich nu gekwalificeerd voelt om ons de les te lezen over nationale hervormingen."
- "Oh, natuurlijk, want als we aan klimaatexpertise denken, denken we allemaal aan minister De Vries, die ooit CO₂ verwarde met koolmonoxide."
- "Hoe kunnen we minister Bakker's standpunt over volkshuisvesting vertrouwen als zijn eigen vastgoedinvesteringen profiteren van deregulering?"

Wat is GEEN ad hominem aanval:
- Kritiek op beleid of argumenten op basis van logica of bewijs 
 Voorbeeld: "Dit beleid zal niet werken - er is geen budget om het te ondersteunen."
- Verwijzingen naar acties of banden uit het verleden wanneer deze direct relevant zijn 
 Voorbeeld: "Hij stemde tegen de hervorming van de gezondheidszorg in 2020, en nu komt hij op zijn schreden terug."
- Mild sarcasme of emotionele toon zonder persoonlijke targeting 
 Voorbeeld: "Dat is een interessante bewering - hoewel niet erg overtuigend."
- Oneens zonder persoonlijke belediging 
 Voorbeeld: "Ik ben het sterk oneens met haar voorstel. Het gaat voorbij aan de data."

Geef voor elke ad hominem aanval ook:
- "local_topic": het onderwerp waarover gediscussieerd wordt op het moment van de aanval.
- "target": de persoon of groep waar de ad hominem op gericht is.
- "explicitness": "explicit" (expliciet) of "implicit" (impliciet), afhankelijk van hoe direct de aanval is.

Volg deze conventies bij het invullen van de JSON velden:
- explanation: "string (korte toelichting inclusief de context van de uitwisseling/het moment)".
- target: Gebruik de naam of politieke groep die wordt aangevallen - geen vage termen zoals “ze”.
- local_topic: Wees specifiek over het onderwerp waarover gediscussieerd wordt (bijv. “subsidies voor kinderopvang”, niet alleen “welzijn”).

Geef het volgende JSON-formaat terug:
{{
  "found_fallacy": [
    {{
      "quote": "string (exacte quote)",
      "explanation": "string (korte verantwoording)",
      "confidence": float,
      "local_topic": "string",
      "target": "string",
      "explicitness": "string ('explicit' or 'implicit')"
    }}
  ],
  "summary": {{
    "count": integer,
    "average_confidence": float,
    "highest_confidence": float,
    "lowest_confidence": float
  }}
}}

Als er geen ad-hominem aanvallen met hoge betrouwbaarheid zijn gevonden:
{{
  "found_fallacy": [],
  "summary": {{
    "count": 0,
    "average_confidence": 0.0,
    "highest_confidence": 0.0,
    "lowest_confidence": 0.0
  }}
}}

Tekst om te analyseren:
{text}"""
