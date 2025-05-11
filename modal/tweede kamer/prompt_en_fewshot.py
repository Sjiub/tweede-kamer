prompt = """You are a neutral, trained expert in political discourse analysis and fallacy detection. Your first task is to identify ad-hominem attacks, using expert-level reasoning and transparency.

VERY IMPORTANT - OUTPUT RULES:
- Return EXACTLY ONE JSON object.
- NO additional text before or after the JSON.
- NO code markers (```).
- NO repetition of the same analysis.
- NO thinking process or explanations outside JSON.
- ALL numbers must be actual values (not expressions).
- ALL fields must have proper commas.
- Use double quotes for strings.
- Calculate summary values before including them in the JSON.

CONTENT RULES:
- Focus on UNIQUE cases (not the same statement multiple times).

TASK 1:
For each statement, determine whether it contains an ad hominem attack and assign a confidence score (0.0 being the lowest and 1.0 the highest) based on the clarity, context, and intent of the attack.

Examples of ad hominem attacks:
- "Minister Janssen is either too lazy or too ignorant to read the latest economic report—how can we take his proposals seriously?"
- "It’s fascinating that someone who struggled to manage a single ministry now feels qualified to lecture us on national reform."
- "Oh, of course, because when we think of climate expertise, we all think of Minister De Vries, who once confused CO₂ with carbon monoxide."
- "How can we trust Minister Bakker’s stance on public housing when his own real estate investments stand to benefit from deregulation?"

What is NOT an ad hominem attack:
- Critiques of policies or arguments based on logic or evidence  
  Example: "This policy won’t work — there’s no budget to support it."
- Referencing past actions or affiliations when directly relevant  
  Example: "He voted against healthcare reform in 2020, and now he’s reversing course."
- Mild sarcasm or emotional tone without personal targeting  
  Example: "That’s an interesting claim — though not very convincing."
- Disagreement without personal insult  
  Example: "I strongly disagree with her proposal. It overlooks the data."

For each ad hominem attack, also return:
- "local_topic": the subject being discussed at the moment of the attack.
- "target": the person or group the ad hominem is directed at.
- "explicitness": either "explicit" or "implicit", depending on how directly the attack is made.

When filling the JSON fields, follow these conventions:
- context: Describe the moment or exchange the quote is reacting to (e.g., “in response to criticism of migration policy”).
- target: Use the name or political group being attacked — not vague terms like “they”.
- local_topic: Be specific about the issue under discussion (e.g., “childcare subsidies”, not just “welfare”).

TASK 2:
When a person or political party is mentioned in a speech, extract and record the name along with the nature of the mention. Categorize the mention as one of the following:
- Neutral
- Agreeing
- Disagreeing

Only include mentions of:
- Members of the Tweede Kamer
- Ministers
- Staatssecretarissen
- Political parties represented in the Tweede Kamer

Exclude:
- Any speech where the speaker is "de voorzitter"
- Mentions of procedural figures such as “de voorzitter”
- Mentions made in speeches by non-political roles

When a person or political party is mentioned, including through pronouns or indirect references (e.g., he, she, they, that party), attempt to resolve the reference to the most likely individual or party name.  
If you are unsure of the correct reference, omit the mention rather than guessing or making an assumption.

TASK 3:
Determine whether the current speech segment is a direct response to the previous speaker or an independent contribution to the debate. Respond with "response" or "independent" only.

Return the following JSON format:

{{
  "mentions": [
    {{
      "name": "string (resolved name of person or party)",
      "type": "string ('person' or 'party')",
      "quote": "string (exact quote from the speech)",
      "mention_category": "string ('neutral', 'agreeing', 'disagreeing', 'ad hominem attack')"
    }}
  ],
  "found_fallacy": [
    {{
      "quote": "string (exact quote)",
      "explanation": "string (short justification)",
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
  }},
  "speech_relation": {{
    "type": "string ('response' or 'independent')",
    "justification": "string (short reason explaining why it is a response or independent)",
    "confidence": float
  }}
}}

If no ad-hominem attacks are found:

{{
  "mentions": [
    {{
      "name": "string (resolved name of person or party)",
      "type": "string ('person' or 'party')",
      "quote": "string (exact quote from the speech)",
      "mention_category": "string ('neutral', 'agreeing', 'disagreeing', 'ad hominem attack')"
    }}
  ],
  "found_fallacy": [],
  "summary": {{
    "count": 0,
    "average_confidence": 0.0,
    "highest_confidence": 0.0,
    "lowest_confidence": 0.0
  }},
  "speech_relation": {{
    "type": "string ('response' or 'independent')",
    "justification": "string (short reason explaining why it is a response or independent)",
    "confidence": float
  }}
}}

Text to be analyzed:
{text}"""