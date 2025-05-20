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
Bepaal voor elke uitspraak of deze een ad hominem aanval bevat en geef een confidence score (0,0 is het laagst en 1,0 het hoogst) op basis van de duidelijkheid, context en intentie van de aanval.

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
