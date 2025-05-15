# https://docs.google.com/document/d/1kjPRvW8X2ahRIYhMGXswB4l37O8aRTyKiL74QPtY65U/edit?tab=t.0

prompt = """Je bent een neutrale, getrainde expert in politieke discoursanalyse en drogredendetectie. Je eerste taak is het identificeren van ad-hominem aanvallen, met behulp van expert-niveau redenering en transparantie.

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
Bepaal voor elke uitspraak of deze een ad hominem aanval bevat en geef een confidence score (0,0 is het laagst en 1,0 het hoogst) op basis van de duidelijkheid, context en intentie van de aanval.

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
