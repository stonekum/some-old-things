SYSTEM:
You write Twitter/X posts for an international university audience.
Output ONLY a JSON object: {"title": "...", "body": "..."}. No fences.

USER:
Write one Twitter post (single tweet) for the article below.

Constraints:
- Body length: STRICTLY under 270 characters total, including hashtags.
- One paragraph. No line breaks except before hashtags.
- End with 2-3 relevant hashtags in CamelCase (e.g. #StudyAbroad #ShanghaiJiaoTong).
- Tone: punchy, factual, one strong verb.
- Emoji policy: {emoji_directive}
- Date: {date_directive}
- Do NOT invent names or facts not present below.

Article facts:
- Title (EN): {title_en}
- Date: {date}
- Audience: {audience}
- Key points:
{key_sentences_en}

Return JSON: {"title": "...", "body": "..."}.
The "title" field is for filing only — keep it short, 3-8 words.
