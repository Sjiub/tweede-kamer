prompt = """
VERY IMPORTANT - OUTPUT RULES:
- Return EXACTLY ONE JSON object.
- NO additional text before or after the JSON.
- NO code markers (```).
- Use double quotes for strings.

TASK:
When a person or political party is mentioned in a speech, extract and record the name along with the nature of the mention. Categorize the mention as one of the following:
- Neutral: The mention contains no clear positive or negative sentiment, presents factual information, or refers to someone in a purely procedural way.
- Agreeing: The mention expresses support, alignment, approval, or positive acknowledgment of the person/party's statements, positions, or actions.
- Disagreeing: The mention expresses opposition, criticism, rejection, or negative assessment of the person/party's statements, positions, or actions.

Only include mentions of:
- Members of the Tweede Kamer
- Ministers
- Staatssecretarissen
- Political parties represented in the Tweede Kamer

Exclude:
- Any speech where the speaker is "de voorzitter"
- Mentions of procedural figures such as "de voorzitter"
- Mentions made in speeches by non-political roles

Return the following JSON format:

{{
  "mentions": [
    {{
      "name": "string (resolved name of person or party)",
      "type": "string ('person' or 'party')",
      "quote": "string (exact quote from the speech)",
      "mention_category": "string ('neutral', 'agreeing', 'disagreeing')"
    }}
  ]
}}

If no relevant mentions are found:

{{
  "mentions": []
}}

Text to be analyzed:
{text}"""