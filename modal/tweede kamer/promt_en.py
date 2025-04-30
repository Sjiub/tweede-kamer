# https://docs.google.com/document/d/1IcHzTx7dSVw-qFRPrcbjUpatWHQAXGY9fnlUh5phGUk/edit?tab=t.0

prompt = """You are an expert in analyzing political texts. Analyze the text below for ad-hominem attacks.

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
- Report ONLY the clearest cases (confidence ≥ 0.7).
- DO NOT report weak or questionable cases.
- Focus on UNIQUE cases (not the same statement multiple times).

Definitions of ad hominem attacks:
Ad hominem attacks are rhetorical strategies that attempt to discredit or undermine a speaker by targeting their personal traits, character, motives, or affiliations — rather than engaging with the substance of their argument. These attacks divert attention from the issue at hand and often function to delegitimize the critic, thereby weakening public deliberation.

Types include:
1. Tu Quoque (“you too”): Discrediting a critic by accusing them of hypocrisy or past wrongdoing.
2. Whataboutery: Redirecting criticism by pointing out the critic’s silence on other similar issues.
3. Bias Attribution: Accusing the speaker of hidden motives or interests, implying their argument is invalid.
4. Direct Personal Attacks: Insulting or morally condemning the speaker's character or competence.

Only include statements with a clear intent to personally discredit the speaker. Do not flag weak, indirect, or contextually ambiguous remarks.

Examples of ad hominem attacks:
- "Of course he would oppose this policy — he was educated abroad and doesn't understand our values."
- "This proposal comes from a socialist, so it’s obviously flawed."
- "You can’t trust her stance on climate — her organization is funded by foreign interests."

What is NOT an ad hominem attack:
- Critiques of policies or arguments based on logic or evidence  
  Example: "This policy won’t work — there’s no budget to support it."
- Referencing past actions or affiliations when directly relevant  
  Example: "He voted against healthcare reform in 2020, and now he’s reversing course."
- Mild sarcasm or emotional tone without personal targeting  
  Example: "That’s an interesting claim — though not very convincing."
- Disagreement without personal insult  
  Example: "I strongly disagree with her proposal. It overlooks the data."

Confidence Score Guidelines:
- 0.9 - 1.0: Unmistakable ad hominem attack with clear evidence.
- 0.7 - 0.9: Clear ad hominem attack with good context.
- <0.7: DO NOT REPORT.

For each ad hominem attack, also return:
- "overall_debate_topic": the central topic or main theme of the full debate (must be determined from the first speech and kept EXACTLY THE SAME for all speeches in this debate)
- "local_topic": the subject being discussed at the moment of the attack.
- "target": the person or group the ad hominem is directed at.
- "explicitness": either "explicit" or "implicit", depending on how directly the attack is made.

Return the following JSON format:
{{
  "found_fallacy": [
    {{
      "quote": "string (exact quote)",
      "explanation": "string (short justification)",
      "confidence": "float (only ≥ 0.7)",
      "context": "string (relevant context)",
      "overall_debate_topic": "string",
      "local_topic": "string",
      "target": "string",
      "explicitness": "string ('explicit' or 'implicit')"
    }}
  ],
  "summary": {{
    "count": "integer",
    "average_confidence": "float",
    "highest_confidence": "float",
    "lowest_confidence": "float"
  }}
}}

If no ad-hominem attacks with high confidence are found:
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
