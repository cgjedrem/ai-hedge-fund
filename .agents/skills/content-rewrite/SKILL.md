---
name: content-rewrite
description: 'Rewrite raw content (especially YouTube transcripts) into production-grade articles with source attribution, verification labels, added context, self-promotion flags, and key takeaways. Used for cleaning up YouTube transcripts, rough notes, or content tagged with the rewrite intent. Triggers on phrases like "rewrite this", "clean up transcript", "rewrite content", or when called by the extract-from-master-inbox workflow for rewrite-intent items or YouTube transcripts. Do not use for original creative writing, technical documentation, or code rewriting.'
---

# content-rewrite

## Purpose

Take raw, messy, or unstructured content — especially YouTube transcripts — and rewrite it into a production-grade article with:

1. **Source attribution** — URL, speaker, date, content type
2. **Structured prose** — headings, subheadings, paragraphs, not a transcript dump
3. **Verification labels** — `[Unverified]`, `[Partially Unverified]`, `[Sponsored Content]`, `[Self-Promotion]`
4. **Added context** — relevant research, studies, researchers, frameworks the original didn't mention
5. **Balanced analysis** — "What it Gets Right" / "What it Gets Wrong or Overstates" (when applicable)
6. **Key Takeaways** — distilled bullet list at the end

Preserves all factual content from the source. Does not fabricate content. Does not paraphrase or soften the speaker's claims — labels them instead.

## Input

- `content` — The raw text to rewrite (required)
- `source_url` — The original URL (required for YouTube content, optional otherwise)
- `speaker` — Speaker/author name (if known)
- `date` — Date of original content (if known)
- `content_type` — One of: `youtube_transcript`, `article`, `podcast_transcript`, `notes` (default: `youtube_transcript`)
- `preserve_frontmatter` — Boolean. If `true`, extract YAML frontmatter, rewrite only the body, then reassemble. Default: `false`

## Steps

1. If `preserve_frontmatter=true`:
   a. Split the content at `---` boundaries to extract YAML frontmatter
   b. Store the frontmatter block separately
   c. Set `body = content after second ---`
2. If `preserve_frontmatter=false`:
   a. Set `body = content`

3. Write the rewritten article following the **Output Format** below.

4. If `preserve_frontmatter=true`:
   a. Reassemble: `---\n{frontmatter}\n---\n\n{rewritten_article}`

5. Return the result.

## Output Format

Every rewritten article must include these sections in order:

### 1. Title

`# Title From the Video/Article`

If the original has no clear title, craft one that captures the central thesis.

### 2. Source Attribution Block

```
**Source:** [Title](URL) — Speaker Name
**Speaker:** Full name, credentials/context (if known)
**Article type:** Rewritten transcript with verification, added context, and editorial notes
**Date processed:** YYYY-MM-DD
```

### 3. Disclaimer (when applicable)

For health, financial, or advice content, add:

```
> **⚠️ Disclaimer:** [Brief note about the content type and that it's not professional advice.]
```

### 4. Sponsored / Self-Promotion Disclosure (when applicable)

If the original contains sponsored segments, affiliate links, or self-promotion:

```
> **Note on self-promotion:** The video promotes [items]. These are flagged throughout as [Self-Promotion].
```

### 5. Body — Structured Prose with Verification Labels

- Rewrite the transcript into **flowing prose** with clear headings (##) and subheadings (###)
- **Do NOT** produce a transcript dump, bullet-point summary, or outline
- **Preserve** all the speaker's ideas, arguments, and factual claims
- **Add context** the speaker didn't mention: relevant studies (cite author + year), frameworks, counterarguments, or historical background
- **Label claims** using the verification tags below

#### Verification Tags

| Tag | When to use |
|-----|-------------|
| `[Unverified]` | Claim cannot be confirmed from available sources, or the stated statistic/fact appears incorrect or misleading |
| `[Partially Unverified]` | Claim has some support but oversimplifies, overstates, or omits important nuance |
| `[Sponsored Content]` | Paid promotion or affiliate integration |
| `[Self-Promotion]` | Speaker's own products, courses, newsletters, communities |
| `[Context]` | Added background information not in the original (studies, researchers, frameworks) |

Place verification tags **inline** at the point of the claim, not in a footnote. Use blockquote format for longer annotations:

```
> **[Unverified]** Explanation of why this claim is unverified, with context.
```

### 6. "What It Gets Right" / "What It Gets Wrong or Overstates" (optional)

For longer or more substantive content, add these two sections after the body:

- **What it Gets Right** — 3-5 points where the speaker's framing aligns with established research or sound reasoning
- **What it Gets Wrong or Overstates** — 3-5 points where claims are overgeneralized, oversimplified, or contradicted by evidence

Omit these sections for purely informational or tutorial content with no substantive claims to evaluate.

### 7. Key Takeaways

End with a **Key Takeaways** section:

```
## Key Takeaways

1. [Point 1]
2. [Point 2]
...
```

Distill 7-10 takeaways that capture the most actionable or intellectually significant points.

## Output

```json
{
  "rewritten": "Full production-grade article markdown...",
  "word_count": 4500,
  "verification_labels": {
    "unverified": 3,
    "partially_unverified": 2,
    "sponsored_content": 1,
    "self_promotion": 2,
    "context_added": 8
  }
}
```

## Failure Modes

| Condition | Response |
|-----------|----------|
| Model returns empty or very short output | Return `{ "error": "rewrite produced no content" }` |
| Model timeout | Return `{ "error": "rewrite timed out" }` |
| Frontmatter parsing fails when preserve_frontmatter=true | Treat entire input as body, proceed with rewrite |
| No source URL provided for YouTube content | Proceed but omit the linked title; note `[Source URL not provided]` |

## Usage Patterns

- **YouTube transcript rewrite**: Called after `yt-dlp-extract` to convert raw VTT into production-grade articles with verification labels and added context
- **Rewrite-intent items**: Called by `extract-from-master-inbox` workflow task4 to clean up rough or transcript-style content
- **General purpose**: Any agent can call this skill to rewrite raw content into structured, verified articles

## Notes

- This skill uses the agent's default model. No model override is provided.
- The tone is **accessible but precise** — not academic jargon, but not casual either. Think: well-edited longform journalism.
- Original content is never discarded. If the rewrite fails, the original is preserved.
- When `preserve_frontmatter=true`, the frontmatter is kept exactly as-is — only the body is rewritten.
- **Never fabricate studies, researchers, or statistics.** If you cannot verify a claim, label it `[Unverified]`. If you add context, label it `[Context]`.
- **Never paraphrase or soften the speaker's claims.** If they say something bold or wrong, preserve it and label it.
- **Exclude pure self-promotion from the article body.** Flag it at the top and note it inline, but don't expand on sales pitches.
- **Key Takeaways are mandatory.** Every rewritten article ends with them.