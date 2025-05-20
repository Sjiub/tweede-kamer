prompt = """

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

For each ad hominem attack, also return:
- "local_topic": the subject being discussed at the moment of the attack.
- "target": the person or group the ad hominem is directed at.
- "explicitness": either "explicit" or "implicit", depending on how directly the attack is made.

When filling the JSON fields, follow these conventions:
- explanation: "string (short justification including the context of the exchange/moment)".
- target: Use the name or political group being attacked — not vague terms like “they”.
- local_topic: Be specific about the issue under discussion (e.g., “childcare subsidies”, not just “welfare”).

Return the following JSON format:

{{
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
  }}
}}

If no ad-hominem attacks are found:
{{
  "found_fallacy": [],
  "summary": {{
    "count": 0,
    "average_confidence": 0.0,
    "highest_confidence": 0.0,
    "lowest_confidence": 0.0
  }}
}}

Text to be analyzed:
{text}"""
