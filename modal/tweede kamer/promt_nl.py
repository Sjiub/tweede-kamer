# https://docs.google.com/document/d/1kjPRvW8X2ahRIYhMGXswB4l37O8aRTyKiL74QPtY65U/edit?tab=t.0

prompt = """Jij bent een expert in het analyseren van politieke teksten. Analyseer de onderstaande tekst op ad-hominem aanvallen.

ZEER BELANGRIJK - UITVOERREGELS:
- Geef EXACT ÉÉN JSON object terug.
- GEEN extra tekst voor of na de JSON.
- GEEN code markers (```).
- GEEN herhaling van dezelfde analyse.
- GEEN uitleg buiten de JSON.

INHOUD REGELS:
- Rapporteer ALLEEN de duidelijkste gevallen (betrouwbaarheid ≥ 0,7).
- Rapporteer GEEN zwakke of twijfelachtige gevallen.
- Focus op UNIEKE gevallen (niet meerdere keren dezelfde verklaring).
- Maximaal 5 gevallen per analyse.

Definities van ad hominem aanvallen:
Ad hominem aanvallen zijn retorische strategieën die proberen een spreker in diskrediet te brengen of te ondermijnen door zich te richten op zijn persoonlijke eigenschappen, karakter, motieven of affiliaties - in plaats van in te gaan op de inhoud van hun argument. Deze aanvallen leiden de aandacht af van het onderwerp dat aan de orde is en hebben vaak als functie om de criticus te delegitimeren, waardoor de openbare beraadslaging wordt verzwakt.

Soorten zijn onder andere:
1. Tu Quoque (“jij ook”): Een criticus in diskrediet brengen door hem te beschuldigen van hypocrisie of wangedrag in het verleden.
2.Whataboutisme: Kritiek ombuigen door te wijzen op het stilzwijgen van de criticus over andere, vergelijkbare kwesties.
3. Bias attributie: De spreker beschuldigen van verborgen motieven of belangen, impliceren dat zijn argument ongeldig is.
4. Directe persoonlijke aanvallen: Beledigen of moreel veroordelen van het karakter of de competentie van de spreker.

Neem alleen uitspraken op met een duidelijke bedoeling om de spreker persoonlijk in diskrediet te brengen. Markeer geen zwakke, indirecte of contextueel dubbelzinnige opmerkingen.

Voorbeelden van ad hominem aanvallen:
- "Natuurlijk zou hij tegen dit beleid zijn - hij is in het buitenland opgeleid en begrijpt onze waarden niet."
- “Dit voorstel komt van een socialist, dus het is duidelijk gebrekkig.”
- “Je kunt haar standpunt over het klimaat niet vertrouwen - haar organisatie wordt gefinancierd door buitenlandse belangen.”

Wat is GEEN ad hominem aanval:
- Kritiek op beleid of argumenten gebaseerd op logica of bewijs
 Voorbeeld: “Dit beleid zal niet werken - er is geen budget om het te ondersteunen.”
- Verwijzingen naar acties of banden uit het verleden wanneer deze direct relevant zijn
 Voorbeeld: “Hij stemde tegen de hervorming van de gezondheidszorg in 2020, en nu komt hij op zijn schreden terug.”
- Mild sarcasme of emotionele toon zonder persoonlijke targeting
 Voorbeeld: “Dat is een interessante bewering - hoewel niet erg overtuigend.”
- Oneens zonder persoonlijke belediging
 Voorbeeld: "Ik ben het sterk oneens met haar voorstel. Het ziet de data over het hoofd.” 

Richtlijnen voor betrouwbaarheidsscores:
- 0.9 - 1.0: Onmiskenbare ad-hominem aanval met duidelijk bewijs.
- 0.7 - 0.9: Duidelijke ad-hominem aanval met goede context.
- &lt;0.7: NIET RAPPORTEREN.

Geef het volgende JSON-formaat terug:
{{
  "found_fallacy": [
    {{
      "quote": "string (exact quote)",
      "explanation": "string (short justification)",
      "confidence": "float (only ≥ 0.7)",
      "context": "string (relevant context)"
    }}
  ],
  "summary": {{
    "count": "integer",
    "average_confidence": "float",
    "highest_confidence": "float",
    "lowest_confidence": "float"
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

Te analyseren tekst:
{text}"""
