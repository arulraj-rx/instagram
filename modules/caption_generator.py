import logging
import os
import re

from groq import Groq


class CaptionGenerator:
    def __init__(self, config):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.logger = logging.getLogger(__name__)
        self.fixed_tag = str(config.get("fixed_hashtag", "#whystaystill")).strip()
        self.caption_limit = int(config.get("caption_limit", 2200))
        self.threads_caption_limit = int(
            config.get("threads_caption_limit", self.caption_limit)
        )

    def generate(self, filename, media_type, platform="instagram"):
        clean_name = self._clean_name(filename)
        platform = str(platform).strip().lower()

        if platform == "threads":
            return self._generate_threads_caption(clean_name, media_type)
        return self._generate_instagram_caption(clean_name, media_type)

    def _generate_instagram_caption(self, clean_name, media_type):
        system_instruction = (
            "You write Instagram captions from filenames. "
            "Write in 3 short sections with a blank linespace between sections. "
            "Use emojis based on the emotion of the post. "
            "Use around 10 to 15 emojis naturally, and never exceed 40 emojis total. "
            "End with 5 to 7 relevant hashtags on the final line. "
            "Do not add quotation marks. "
            f"Do not add the fixed hashtag {self.fixed_tag}; it will be appended separately."
        )

        if media_type == "video":
            user_prompt = (
                f"Create an Instagram Reel caption for '{clean_name}'. "
                "Keep it catchy, emotional, and natural. Max 90 words."
            )
        else:
            user_prompt = (
                f"Create an Instagram photo caption for '{clean_name}'. "
                "Keep it warm, engaging, and natural. Max 70 words."
            )

        try:
            completion = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.8,
                max_tokens=500,
            )
            raw_caption = completion.choices[0].message.content.strip()
            normalized = self._normalize_multiline_caption(raw_caption)
            return self._finalize_instagram_caption(normalized, clean_name)
        except Exception as error:
            self.logger.error(f"AI generation failed: {error}")
            fallback = self._normalize_multiline_caption(clean_name)
            return self._finalize_instagram_caption(fallback, clean_name)

    def _generate_threads_caption(self, clean_name, media_type):
        system_instruction = (
            "You write Threads captions from filenames. "
            "Write in 3 or 4 short lines or short paragraphs with blank linespace between them. "
            "Use emojis that fit the post. "
            "Use around 5 to 10 emojis naturally, and never exceed 40 emojis total. "
            "End with exactly 1 relevant hashtag on the final line. "
            "Do not use the fixed hashtag from Instagram. "
            "Do not add quotation marks. "
            "Make it feel human, reflective, and suited for Threads."
        )

        if media_type == "video":
            user_prompt = (
                f"Create a Threads caption for the video '{clean_name}'. "
                "Keep it thoughtful and scroll-stopping. Max 80 words."
            )
        else:
            user_prompt = (
                f"Create a Threads caption for the image '{clean_name}'. "
                "Keep it thoughtful and warm. Max 65 words."
            )

        try:
            completion = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.85,
                max_tokens=400,
            )
            raw_caption = completion.choices[0].message.content.strip()
            normalized = self._normalize_multiline_caption(raw_caption)
            return self._finalize_threads_caption(normalized, clean_name)
        except Exception as error:
            self.logger.error(f"Threads AI generation failed: {error}")
            fallback = self._normalize_multiline_caption(clean_name)
            return self._finalize_threads_caption(fallback, clean_name)

    def _clean_name(self, filename):
        return os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").strip()

    def _normalize_multiline_caption(self, caption):
        text = str(caption).replace('"', "").replace("'", "")
        lines = [self._clean_line(line) for line in text.splitlines()]

        cleaned = []
        previous_blank = False
        for line in lines:
            if not line:
                if not previous_blank and cleaned:
                    cleaned.append("")
                previous_blank = True
                continue
            cleaned.append(line)
            previous_blank = False

        return "\n".join(cleaned).strip()

    def _clean_line(self, line):
        return " ".join(str(line).split()).strip()

    def _append_fixed_hashtag(self, caption):
        if not self.fixed_tag:
            return caption[: self.caption_limit].strip()

        combined = f"{caption}\n\n{self.fixed_tag}".strip()
        return combined[: self.caption_limit].strip()

    def _finalize_instagram_caption(self, caption, clean_name):
        body, tags = self._split_body_and_hashtags(caption)
        tags = self._ensure_hashtag_count(tags, clean_name, minimum=5, maximum=7)
        joined_tags = " ".join(tags)
        combined = f"{body}\n\n{joined_tags}".strip() if joined_tags else body.strip()
        return self._append_fixed_hashtag(combined)

    def _finalize_threads_caption(self, caption, clean_name):
        body, tags = self._split_body_and_hashtags(caption)
        tags = self._ensure_hashtag_count(tags, clean_name, minimum=1, maximum=1)
        joined_tags = " ".join(tags[:1])
        return f"{body}\n\n{joined_tags}".strip() if joined_tags else body.strip()

    def _split_body_and_hashtags(self, caption):
        lines = caption.splitlines()
        body_lines = []
        tag_parts = []

        for line in lines:
            hashtags = self._extract_hashtags(line)
            cleaned_line = self._remove_hashtags_from_line(line).strip()
            if cleaned_line:
                body_lines.append(cleaned_line)
            if hashtags:
                tag_parts.extend(hashtags)

        body = self._normalize_multiline_caption("\n".join(body_lines))
        return body, self._dedupe_hashtags(tag_parts)

    def _extract_hashtags(self, text):
        return re.findall(r"#([A-Za-z0-9_]+)", str(text))

    def _remove_hashtags_from_line(self, text):
        return re.sub(r"(?:^|\s)#[A-Za-z0-9_]+", "", str(text)).strip()

    def _dedupe_hashtags(self, tags):
        deduped = []
        seen = set()
        for tag in tags:
            normalized = self._normalize_hashtag(tag)
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(f"#{normalized}")
        return deduped

    def _ensure_hashtag_count(self, tags, clean_name, minimum, maximum):
        deduped = self._dedupe_hashtags(tags)
        fallback_tags = self._build_fallback_hashtags(clean_name)

        for tag in fallback_tags:
            if len(deduped) >= minimum:
                break
            lowered = tag.lower()
            if lowered not in {item.lower() for item in deduped}:
                deduped.append(tag)

        if len(deduped) < minimum:
            generic_tags = ["#love", "#life", "#quotes", "#motivation", "#feelings", "#thoughts", "#reels"]
            for tag in generic_tags:
                if len(deduped) >= minimum:
                    break
                if tag.lower() not in {item.lower() for item in deduped}:
                    deduped.append(tag)

        return deduped[:maximum]

    def _build_fallback_hashtags(self, clean_name):
        words = []
        for raw_word in clean_name.split():
            normalized = self._normalize_hashtag(raw_word)
            if normalized and len(normalized) > 2:
                words.append(f"#{normalized}")

        return self._dedupe_hashtags(words)

    def _normalize_hashtag(self, value):
        cleaned = re.sub(r"[^A-Za-z0-9_]", "", str(value).lstrip("#"))
        return cleaned[:30]
