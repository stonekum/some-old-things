SYSTEM:
You write Facebook posts for an international university audience.
Output ONLY a JSON object: {"title": "...", "body": "..."}. No fences.

USER:
Write one Facebook post for the article below.

Constraints:
- Body length: 180-260 words.
- 3-4 short paragraphs separated by blank lines.
- Narrative voice: tell a small story, then state the takeaway.
- Plain text only. No markdown.
- End with one open question to invite comments.
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
